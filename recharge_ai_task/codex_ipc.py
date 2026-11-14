"""Bounded, versioned access to the running Codex desktop router.

This is a private desktop protocol, isolated here so incompatible releases
fail with an error rather than falling back to typing in another chat.
"""
from __future__ import annotations

import json
import os
import socket
import stat
import struct
import time
import uuid
from pathlib import Path


# Snapshot revision numbers can change when unrelated fields are added. Check
# the small status subset we consume instead of blocking on a revision bump.
TASK_STATUSES = frozenset({"active", "idle", "notLoaded", "systemError", "error"})
GOAL_STATUSES = frozenset({"active", "paused", "blocked", "usageLimited", "usage_limited",
    "budgetLimited", "budget_limited", "complete", "systemError", "error"})
_MISSING = object()


def _status_schema_error(version, field, expected, actual=_MISSING, *, show_value=False):
    revision = str(version) if type(version) is int else "missing" if version is _MISSING else "invalid"
    if actual is _MISSING:
        description = "missing"
    elif actual is None:
        description = "null"
    elif isinstance(actual, str):
        # Only status enums and revisions can disclose a bounded scalar. Other
        # strings might contain unrelated conversation data; report their type.
        description = "string"
        if show_value:
            description += " " + ascii(actual[:80]) + (" (truncated)" if len(actual) > 80 else "")
    elif type(actual) in {bool, int, float}:
        description = f"{type(actual).__name__} {actual!r}"
    elif isinstance(actual, list):
        description = f"list ({len(actual)} items)"
    elif isinstance(actual, dict):
        description = "object"
    else:
        description = type(actual).__name__
    return ValueError(f"Codex desktop status schema v{revision} is incompatible: {field} is {description}; "
        f"expected {expected}. Refresh chats/statuses and update Recharge AI-task if needed. "
        "If this persists, report this diagnostic and your Codex desktop version.")


def _snapshot_status_fields(state, version):
    runtime = state.get("threadRuntimeStatus")
    task = None
    if runtime is not None:
        path = "params.change.conversationState.threadRuntimeStatus"
        if not isinstance(runtime, dict):
            raise _status_schema_error(version, path, "an object or null", runtime)
        kind = runtime.get("type", _MISSING)
        if not isinstance(kind, str) or kind not in TASK_STATUSES:
            raise _status_schema_error(version, path + ".type", "one of " + ", ".join(sorted(TASK_STATUSES)), kind, show_value=True)
        flags = runtime.get("activeFlags")
        if flags is not None and not isinstance(flags, list):
            raise _status_schema_error(version, path + ".activeFlags", "a list of nonempty strings, null, or an omitted field", flags)
        for index, flag in enumerate(flags or []):
            if not isinstance(flag, str) or not flag.strip():
                raise _status_schema_error(version, f"{path}.activeFlags[{index}]", "a nonempty string", flag)
        task = {"type": runtime["type"]}
        if "activeFlags" in runtime:
            task["activeFlags"] = flags or []
    for name in ("threadGoal", "completedThreadGoal"):
        value = state.get(name)
        if value is None:
            continue
        path = "params.change.conversationState." + name
        if not isinstance(value, dict):
            raise _status_schema_error(version, path, "an object or null", value)
        status = value.get("status", _MISSING)
        if not isinstance(status, str) or status not in GOAL_STATUSES:
            raise _status_schema_error(version, path + ".status", "one of " + ", ".join(sorted(GOAL_STATUSES)), status, show_value=True)
    goal = state.get("threadGoal") or state.get("completedThreadGoal")
    # Do not retain conversation histories, prompts, objectives or new fields.
    return {"task": task,
        "goal": goal["status"] if goal is not None else None,
        "goal_available": "threadGoal" in state or "completedThreadGoal" in state,
        "goal_current": isinstance(state.get("threadGoal"), dict)}


class DeliveryUncertain(RuntimeError):
    """A request may have been accepted; do not automatically repeat it."""


class DesktopIPC:
    def __init__(self, endpoint: str, timeout: float = 8):
        self.endpoint = endpoint
        self.timeout = timeout
        self.client_id = "initializing-client"
        self.socket = None

    def __enter__(self):
        info = Path(self.endpoint).stat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
            raise OSError("Codex IPC endpoint must be a socket owned by the current user")
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.settimeout(self.timeout)
        try:
            self.socket.connect(self.endpoint)
            response = self.request("initialize", {"clientType": "recharge-ai-task"})
            self.client_id = response["result"]["clientId"]
        except Exception:
            self.socket.close()
            raise
        return self

    def __exit__(self, *_):
        self.socket.close()

    def _read(self, size, deadline):
        data = bytearray()
        while len(data) < size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Codex desktop response timed out")
            self.socket.settimeout(remaining)
            chunk = self.socket.recv(size - len(data))
            if not chunk:
                raise ConnectionError("Codex desktop disconnected")
            data.extend(chunk)
        return bytes(data)

    def _write(self, message):
        payload = json.dumps(message).encode()
        self.socket.sendall(struct.pack("<I", len(payload)) + payload)

    def _message(self, deadline, max_size=16 * 1024 * 1024):
        size = struct.unpack("<I", self._read(4, deadline))[0]
        if not 0 < size <= max_size:
            raise ValueError("Invalid Codex IPC frame size")
        message = json.loads(self._read(size, deadline))
        if not isinstance(message, dict):
            raise ValueError("Invalid Codex IPC message")
        if message.get("type") == "client-discovery-request":
            # We only consume requests; never claim ownership of a chat.
            self._write(dict(type="client-discovery-response",
                requestId=message["requestId"], response={"canHandle": False}))
        return message

    def request(self, method, params, *, version=0, target_client=None):
        request_id = str(uuid.uuid4())
        request = dict(type="request", requestId=request_id,
                       sourceClientId=self.client_id, method=method, params=params,
                       version=version, timeoutMs=int(self.timeout * 1000))
        if target_client:
            request["targetClientId"] = target_client
        self._write(request)
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            message = self._message(deadline)
            if message.get("requestId") != request_id or message.get("type") != "response":
                continue
            if message.get("resultType") != "success":
                raise RuntimeError(message.get("error", "Codex IPC request failed"))
            return message
        raise TimeoutError("Codex desktop did not respond")

    def status_snapshot(self, thread_id, owner):
        """Observe the owner's current state, then detach. Never resume a chat.

        Accept additive changes at any positive revision. Validate the owner,
        chat identity and consumed fields; incompatible shapes fail visibly.
        """
        def follow(enabled):
            self._write(dict(type="broadcast", method="thread-stream-following-changed",
                version=1, sourceClientId=self.client_id, targetClientIds=[owner],
                params={"hostId": "local", "conversationId": thread_id, "following": enabled}))
        follow(True)
        deadline = time.monotonic() + self.timeout
        version = _MISSING
        try:
            while time.monotonic() < deadline:
                # Desktop snapshots include history; use a bounded larger frame.
                message = self._message(deadline, max_size=64 * 1024 * 1024)
                if (message.get("type") != "broadcast" or
                        message.get("method") != "thread-stream-state-changed" or
                        message.get("sourceClientId") != owner):
                    continue
                version = message.get("version", _MISSING)
                params = message.get("params", _MISSING)
                if not isinstance(params, dict):
                    raise _status_schema_error(version, "params", "an object", params)
                for field in ("conversationId", "hostId"):
                    value = params.get(field, _MISSING)
                    if not isinstance(value, str) or not value.strip():
                        raise _status_schema_error(version, "params." + field, "a nonempty string", value)
                if params.get("conversationId") != thread_id or params.get("hostId") != "local":
                    continue
                if type(version) is not int or version <= 0:
                    raise _status_schema_error(version, "version", "a positive integer", version, show_value=True)
                change = params.get("change", _MISSING)
                if not isinstance(change, dict):
                    raise _status_schema_error(version, "params.change", "an object", change)
                kind = change.get("type", _MISSING)
                if not isinstance(kind, str) or not kind.strip():
                    raise _status_schema_error(version, "params.change.type", "a nonempty change-type string", kind)
                if change.get("type") != "snapshot":
                    continue
                state = change.get("conversationState", _MISSING)
                if not isinstance(state, dict):
                    raise _status_schema_error(version, "params.change.conversationState", "an object", state)
                for field, expected in (("id", thread_id), ("hostId", "local")):
                    actual = state.get(field, _MISSING)
                    if actual != expected:
                        label = "the selected conversation ID" if field == "id" else "the local host ID"
                        raise _status_schema_error(version, "params.change.conversationState." + field, label, actual)
                return _snapshot_status_fields(state, version)
            raise TimeoutError("Codex desktop status timed out")
        except TimeoutError as exc:
            revision = str(version) if type(version) is int else "not observed"
            raise TimeoutError(f"Codex desktop status snapshot timed out (schema revision: {revision}); "
                "expected params.change.type=snapshot from the selected chat owner. "
                "Refresh chats/statuses and check that the chat is open in Codex desktop.") from exc
        finally:
            try:
                follow(False)
            except OSError:
                pass  # Disconnect also removes this observer from the owner.

    def owner(self, thread_id, host_id="local"):
        response = self.request("thread-owner-discovery",
            {"hostId": host_id, "conversationId": thread_id}, version=1)
        if response["result"].get("supportsUntrustedAppInput") is not True:
            raise RuntimeError("Desktop version does not support external chat input")
        return response["handledByClientId"]

    def send(self, thread_id, text, owner):
        return self._start_turn(thread_id, [{"type": "text", "text": text, "text_elements": []}], owner)

    def resume_goal(self, target, expected):
        from .desktop_goal import activate
        return activate(target, expected, self)

    def steer(self, thread_id, text, owner):
        message_id = str(uuid.uuid4())
        try:
            response = self.request("thread-follower-steer-turn", {
                "conversationId": thread_id,
                "clientUserMessageId": message_id,
                "input": [{"type": "text", "text": text, "text_elements": []}],
                "restoreMessage": {"id": message_id, "prompt": text, "cwd": None,
                    "context": {"workspaceRoots": [], "commentAttachments": []}},
            }, version=1, target_client=owner)
        except (OSError, TimeoutError, ConnectionError, ValueError, TypeError) as exc:
            raise DeliveryUncertain("Prompt steering was not confirmed; check this chat before retrying") from exc
        except RuntimeError as exc:
            if any(word in str(exc).lower() for word in ("timeout", "timed out", "disconnected", "connection-closed")):
                raise DeliveryUncertain("Prompt steering timed out or disconnected; check this chat before retrying") from exc
            raise
        if response.get("handledByClientId") != owner:
            raise DeliveryUncertain("Prompt response came from a different chat owner")
        envelope = response.get("result")
        result = envelope.get("result") if isinstance(envelope, dict) else None
        if not isinstance(result, dict) or not isinstance(result.get("turnId"), str) or not result["turnId"]:
            raise DeliveryUncertain("Codex did not acknowledge the prompt in the active turn")
        return result

    def _start_turn(self, thread_id, inputs, owner):
        # Request routing is pinned to the owner discovered for this exact ID.
        # No model, permissions or workspace overrides are sent.
        try:
            response = self.request("thread-follower-start-turn", {
                "conversationId": thread_id,
                "turnStart": {"request": {"threadId": thread_id,
                    "input": inputs,
                    "clientUserMessageId": str(uuid.uuid4())},
                    "context": {"inheritThreadSettings": True}},
            }, version=2, target_client=owner)
        except (OSError, TimeoutError, ConnectionError, ValueError, TypeError, AttributeError) as exc:
            raise DeliveryUncertain("Delivery was not confirmed; check the chat before retrying manually") from exc
        except RuntimeError as exc:
            if any(reason in str(exc).lower() for reason in ("timeout", "timed out", "disconnected", "connection-closed")):
                raise DeliveryUncertain("Desktop delivery timed out or disconnected; check the chat before retrying manually") from exc
            raise
        if response.get("handledByClientId") != owner:
            raise DeliveryUncertain("Codex response came from a different chat owner; check the chat before retrying")
        result = response.get("result")
        inner = result.get("result") if isinstance(result, dict) else None
        turn = inner.get("turn") if isinstance(inner, dict) else None
        if not isinstance(turn, dict) or not isinstance(turn.get("id"), str) or not turn["id"]:
            raise DeliveryUncertain("Desktop did not acknowledge a turn; check the chat before retrying")
        return result
