"""Read-only goal metadata and live desktop status regression tests."""
import json
import socket
import sqlite3
import struct
import threading

import pytest

from recharge_ai_task import targets
from recharge_ai_task.codex_ipc import DesktopIPC


@pytest.mark.parametrize("state,label", [
    ({"type": "active", "activeFlags": []}, "Running"),
    ({"type": "active", "activeFlags": ["waitingOnApproval"]}, "Waiting for approval"),
    ({"type": "active", "activeFlags": ["waitingOnUserInput"]}, "Waiting for input"),
    ({"type": "active", "activeFlags": ["waitingOnApproval", "waitingOnUserInput"]}, "Waiting for approval / Waiting for input"),
    ({"type": "idle"}, "Idle"), ({"type": "systemError"}, "Error"),
    ({"type": "notLoaded"}, "Not loaded"), (None, "Unavailable"),
    ({"type": "future"}, "future"),
])
def test_task_labels(state, label):
    assert targets.task_status(state) == label


@pytest.mark.parametrize("state,label", [
    ("active", "Active"), ("paused", "Paused"), ("blocked", "Blocked"),
    ("usageLimited", "Stopped by quota"), ("usage_limited", "Stopped by quota"),
    ("budgetLimited", "Budget limited"), ("budget_limited", "Budget limited"),
    ("complete", "Complete"), (None, "Unavailable"), ("future", "future"),
])
def test_goal_labels(state, label):
    assert targets.goal_status(state) == label


def test_goal_database_read_only_and_schema_fallback(tmp_path):
    path = tmp_path / "goals_1.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE thread_goals(thread_id TEXT,status TEXT,objective TEXT)")
        db.execute("INSERT INTO thread_goals VALUES ('one','usage_limited','Private objective')")
    with sqlite3.connect(tmp_path / "goals_2.sqlite") as db:
        db.execute("CREATE TABLE unrelated(id TEXT)")
    before = path.read_bytes()
    assert targets._saved_goals(tmp_path) == {"one": "usage_limited"}
    assert path.read_bytes() == before


def test_goal_database_absent_and_corrupt_are_not_no_goal(tmp_path):
    assert targets._saved_goals(tmp_path) is None
    (tmp_path / "goals_1.sqlite").write_bytes(b"corrupt")
    with pytest.raises(sqlite3.DatabaseError):
        targets._saved_goals(tmp_path)


@pytest.mark.parametrize("snapshot_error", [False, True])
@pytest.mark.parametrize("cached_goal", [False, True])
def test_live_status_overrides_unloaded_metadata(monkeypatch, tmp_path, snapshot_error, cached_goal):
    from recharge_ai_task import codex_ipc
    (tmp_path / "ipc").mkdir()
    (tmp_path / "ipc/ipc.sock").touch()
    monkeypatch.setattr(targets, "discover_homes", lambda: {tmp_path})
    monkeypatch.setattr(targets, "discover_windows", lambda: [])
    monkeypatch.setattr(targets, "_saved_threads", lambda _: [
        {"id": "one", "status": {"type": "notLoaded"}},
        {"id": "two", "status": {"type": "notLoaded"}}])
    monkeypatch.setattr(targets, "_saved_goals", lambda _: {"one": "usage_limited"})
    # Ignore actual daemon sockets; only this synthetic profile is read.
    monkeypatch.setattr(targets.stat, "S_ISSOCK", lambda _: False)
    class Desktop:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def owner(self, thread):
            if thread == "two": raise RuntimeError("no-client-found")
            return "owner"
        def status_snapshot(self, thread, owner):
            if snapshot_error: raise TimeoutError("offline")
            return {"task": {"type": "active"}, "goal": "complete" if cached_goal else "paused", "goal_current": not cached_goal}
    monkeypatch.setattr(codex_ipc, "DesktopIPC", Desktop)
    inventory = targets.discover_targets()
    one, two = inventory.targets
    assert one.status == "Open in desktop"
    assert one.task_status == ("Unavailable" if snapshot_error else "Running")
    assert one.goal_status == "Stopped by quota"
    assert two.task_status == "Not loaded" and two.goal_status == "No goal"
    assert bool(inventory.warnings) == snapshot_error


INVALID_STATUS_STATES = {
    "runtime-list": {"threadRuntimeStatus": []},
    "runtime-missing-type": {"threadRuntimeStatus": {}},
    "runtime-type-list": {"threadRuntimeStatus": {"type": []}},
    "runtime-unknown-type": {"threadRuntimeStatus": {"type": "futureTask"}},
    "flags-string": {"threadRuntimeStatus": {"type": "active", "activeFlags": "waitingOnApproval"}},
    "flags-nested-list": {"threadRuntimeStatus": {"type": "active", "activeFlags": [["waitingOnApproval"]]}},
    "flags-empty-item": {"threadRuntimeStatus": {"type": "active", "activeFlags": [" "]}},
    "goal-list": {"threadGoal": []},
    "goal-missing-status": {"threadGoal": {}},
    "goal-status-list": {"threadGoal": {"status": []}},
    "goal-unknown-status": {"threadGoal": {"status": "futureGoal"}},
    "completed-goal-invalid": {"completedThreadGoal": {"status": "futureComplete"}},
}


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="Requires Unix sockets")
@pytest.mark.parametrize("version", [11, 12, 13, 99, 1000])
@pytest.mark.parametrize("variant", ["live", "quota-stopped", "complete", "no-goal", "wrong-version", "wrong-identity", "timeout", "oversize", *INVALID_STATUS_STATES])
def test_snapshot_is_pinned_read_only_and_always_detaches(tmp_path, variant, version):
    path = str(tmp_path / "ipc.sock")
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(path)
    listener.listen()
    received, errors = [], []
    def peer():
        try:
            with listener.accept()[0] as connection:
                connection.settimeout(2)
                def read(n):
                    data = b""
                    while len(data) < n:
                        chunk = connection.recv(n - len(data))
                        if not chunk: raise EOFError()
                        data += chunk
                    return data
                def recv():
                    value = json.loads(read(struct.unpack("<I", read(4))[0]))
                    received.append(value)
                    return value
                def send(value):
                    payload = json.dumps(value).encode()
                    frame = struct.pack("<I", len(payload)) + payload
                    connection.sendall(frame[:2])
                    connection.sendall(frame[2:])
                init = recv()
                send({"type": "response", "requestId": init["requestId"], "resultType": "success", "result": {"clientId": "observer"}})
                follow = recv()
                assert follow["params"]["following"] is True
                state = {"id": "chosen", "hostId": "local", "threadRuntimeStatus": {"type": "active"},
                         "threadGoal": {"status": "paused", "objective": "Secret", "futureGoalField": "Secret"},
                         "turns": [{"text": "Secret history"}], "futureStateField": {"private": "Secret"}}
                snapshot = {"type": "broadcast", "method": "thread-stream-state-changed", "version": version,
                            "sourceClientId": "owner", "params": {"hostId": "local", "conversationId": "chosen",
                            "futureEnvelopeField": "Secret",
                            "change": {"type": "snapshot", "conversationState": state, "futureChangeField": "Secret"}}}
                # Unrelated owner and conversation messages must never supply state.
                send({**snapshot, "sourceClientId": "other-owner", "version": 99})
                send({**snapshot, "params": {**snapshot["params"], "conversationId": "other-chat"}})
                if variant == "quota-stopped":
                    state["threadRuntimeStatus"] = {"type": "systemError"}
                    state["threadGoal"] = {"status": "usageLimited", "objective": "Secret"}
                elif variant == "complete":
                    state["threadGoal"] = None
                    state["completedThreadGoal"] = {"status": "complete"}
                elif variant == "no-goal": state["threadGoal"] = None
                elif variant == "wrong-version": snapshot["version"] = 0
                elif variant == "wrong-identity": state["id"] = "other-chat"
                elif variant in INVALID_STATUS_STATES: state.update(INVALID_STATUS_STATES[variant])
                if variant == "oversize": connection.sendall(struct.pack("<I", 65*1024*1024))
                elif variant != "timeout": send(snapshot)
                recv()  # The observer unsubscribes even when validation fails.
        except Exception as exc:
            errors.append(exc)
        finally:
            listener.close()
    worker = threading.Thread(target=peer, daemon=True)
    worker.start()
    with DesktopIPC(path, timeout=.5) as desktop:
        if variant in {"wrong-version", "wrong-identity", "timeout", "oversize"} or variant in INVALID_STATUS_STATES:
            match = "schema v0 is incompatible: version is int 0; expected a positive integer" if variant == "wrong-version" else None
            with pytest.raises((ValueError, TimeoutError), match=match) as error:
                desktop.status_snapshot("chosen", "owner")
            if variant in INVALID_STATUS_STATES:
                detail = str(error.value)
                assert f"schema v{version} is incompatible:" in detail
                assert "params.change.conversationState." in detail and "expected" in detail
                assert "Refresh chats/statuses" in detail and "report this diagnostic" in detail
                assert "Secret" not in detail
        else:
            value = desktop.status_snapshot("chosen", "owner")
            assert value == {"task": {"type": "systemError" if variant == "quota-stopped" else "active"}, "goal": {"live": "paused", "quota-stopped": "usageLimited", "complete": "complete", "no-goal": None}[variant], "goal_available": True, "goal_current": variant in {"live", "quota-stopped"}}
            assert "Secret" not in json.dumps(value)
    worker.join(3)
    assert not worker.is_alive() and not errors, errors
    assert [m["method"] for m in received] == ["initialize", "thread-stream-following-changed", "thread-stream-following-changed"]
    assert all(m["targetClientIds"] == ["owner"] for m in received[1:])
    assert received[-1]["params"] == {"hostId": "local", "conversationId": "chosen", "following": False}


@pytest.mark.parametrize("version", [None, True, False, 0, -1, "13", 13.0, [], {}])
def test_snapshot_requires_an_explicit_integer_version_and_detaches(version):
    desktop = DesktopIPC("unused", timeout=.5)
    sent = []
    desktop._write = sent.append
    desktop._message = lambda *a, **kw: {
        "type": "broadcast", "method": "thread-stream-state-changed",
        "version": version, "sourceClientId": "owner",
        "params": {"hostId": "local", "conversationId": "chosen"}}
    with pytest.raises(ValueError, match="version is .*; expected a positive integer"):
        desktop.status_snapshot("chosen", "owner")
    assert [value["params"]["following"] for value in sent] == [True, False]


@pytest.mark.parametrize("params,detail", [
    (None, "params"),
    ({}, "params.conversationId"),
    ({"conversationId": "chosen"}, "params.hostId"),
    ({"hostId": "local", "conversationId": "chosen", "change": []}, "params.change"),
    ({"hostId": "local", "conversationId": "chosen", "change": {}}, "params.change.type"),
])
def test_malformed_snapshot_envelopes_fail_visibly_and_detach(params, detail):
    desktop = DesktopIPC("unused", timeout=.5)
    sent = []
    desktop._write = sent.append
    desktop._message = lambda *a, **kw: {
        "type": "broadcast", "method": "thread-stream-state-changed",
        "version": 13, "sourceClientId": "owner", "params": params}
    with pytest.raises(ValueError, match=f"schema v13 is incompatible: {detail} is"):
        desktop.status_snapshot("chosen", "owner")
    assert [value["params"]["following"] for value in sent] == [True, False]


@pytest.mark.parametrize("fields,expected", [
    ({}, {"task": None, "goal": None, "goal_available": False, "goal_current": False}),
    ({"threadRuntimeStatus": None, "threadGoal": None, "completedThreadGoal": None},
        {"task": None, "goal": None, "goal_available": True, "goal_current": False}),
    ({"threadRuntimeStatus": {"type": "active", "activeFlags": None}},
        {"task": {"type": "active", "activeFlags": []}, "goal": None, "goal_available": False, "goal_current": False}),
    ({"threadRuntimeStatus": {"type": "active", "activeFlags": ["waitingOnApproval"], "new": "Secret"}},
        {"task": {"type": "active", "activeFlags": ["waitingOnApproval"]}, "goal": None, "goal_available": False, "goal_current": False}),
])
def test_future_snapshot_preserves_optional_null_fields_and_known_waiting_flags(fields, expected):
    desktop = DesktopIPC("unused", timeout=.5)
    sent = []
    desktop._write = sent.append
    desktop._message = lambda *a, **kw: {
        "type": "broadcast", "method": "thread-stream-state-changed",
        "version": 1000, "sourceClientId": "owner",
        "params": {"hostId": "local", "conversationId": "chosen",
            "change": {"type": "snapshot", "conversationState": {
                "id": "chosen", "hostId": "local", **fields}}}}
    assert desktop.status_snapshot("chosen", "owner") == expected
    assert [value["params"]["following"] for value in sent] == [True, False]
