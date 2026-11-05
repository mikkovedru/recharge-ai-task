"""Native Goal UI guards; synthetic accessibility objects, no user chat mutations."""
import os
from copy import deepcopy
from types import SimpleNamespace
import pytest

if os.environ.get("RECHARGE_AI_TASK_GUI_TESTS") != "1":
    pytest.skip("Requires Linux GTK/accessibility libraries", allow_module_level=True)

from recharge_ai_task import desktop_goal_ui as ui, goal_control
from recharge_ai_task.targets import Target

GOAL = {"threadId": "chosen", "status": "paused", "objective": "Fixture objective", "createdAt": 1, "tokenBudget": 200}
TARGET = Target("thread", "chosen", "Duplicate title", instance="/fixture")


class Node:
    def __init__(self, name, role="push button", children=(), action=None):
        self.name, self.role, self.children, self.action = name, role, list(children), action
    def getRoleName(self): return self.role
    def getState(self): return SimpleNamespace(contains=lambda state: True)
    def queryAction(self): return SimpleNamespace(doAction=self.action)
    def __iter__(self): return iter(self.children)


def fixture(monkeypatch):
    state = {"goal": deepcopy(GOAL), "id": "chosen", "clicked": 0, "restored": 0, "opened": []}
    def click(_):
        state["clicked"] += 1
        button.name = "Pause goal"
        state["goal"]["status"] = "active"
        return True
    button = Node("Resume goal", action=click)
    frame = Node("Frame", "frame", [button])
    class Clipboard:
        def restore(self): state["restored"] += 1
    class Goals:
        def __init__(self, home): assert home == "/fixture"
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def get(self, thread):
            assert thread == "chosen"
            return deepcopy(state["goal"])
    clock = [0]
    def now():
        clock[0] += .25
        return clock[0]
    monkeypatch.setattr(ui, "ClipboardSnapshot", Clipboard)
    monkeypatch.setattr(ui, "visible_frame", lambda pid: frame)
    monkeypatch.setattr(ui, "current_chat_id", lambda pid: state["id"])
    def show(target, pid):
        if state["id"] != target.id:
            raise RuntimeError("Wrong visible chat ID")
        state["opened"].append(["xdg-open", "codex://threads/" + target.id])
        return frame
    monkeypatch.setattr(ui, "show_chat", show)
    monkeypatch.setattr(ui, "time", SimpleNamespace(monotonic=now, sleep=lambda _: None))
    monkeypatch.setattr(ui.subprocess, "run", lambda args, **kwargs: state["opened"].append(args))
    monkeypatch.setattr(goal_control, "NativeGoals", Goals)
    return state, button, frame


def test_resume_uses_native_goal_button_and_no_prompt(monkeypatch):
    state, button, frame = fixture(monkeypatch)
    ui.resume_goal(TARGET, GOAL, 123)
    assert state["clicked"] == state["restored"] == 1
    assert state["goal"] == {**GOAL, "status": "active"}
    assert button.name == "Pause goal"
    assert state["opened"] == [["xdg-open", "codex://threads/chosen"]]


@pytest.mark.parametrize("problem", ["wrong-id", "changed-goal", "ambiguous-button", "missing-button"])
def test_identity_or_control_failure_never_activates_a_goal(monkeypatch, problem):
    state, button, frame = fixture(monkeypatch)
    if problem == "wrong-id": state["id"] = "other-chat-with-same-title"
    if problem == "changed-goal": state["goal"]["createdAt"] = 9
    if problem == "ambiguous-button": frame.children.append(Node("Resume goal"))
    if problem == "missing-button": button.name = "Other action"
    with pytest.raises(RuntimeError) as error:
        ui.resume_goal(TARGET, GOAL, 123)
    assert not state["clicked"] and state["restored"] == 1
    assert not getattr(error.value, "goal_clicked", False)


def test_chat_switch_before_click_never_activates_a_goal(monkeypatch):
    state, button, frame = fixture(monkeypatch)
    ids = iter(["other"])
    monkeypatch.setattr(ui, "current_chat_id", lambda _: next(ids))
    with pytest.raises(RuntimeError, match="changed"):
        ui.resume_goal(TARGET, GOAL, 123)
    assert not state["clicked"] and state["restored"] == 1


def test_unconfirmed_native_button_transition_is_uncertain(monkeypatch):
    state, button, frame = fixture(monkeypatch)
    def click(_):
        state["clicked"] += 1
        return True
    button.action = click
    with pytest.raises(RuntimeError, match="did not become active") as error:
        ui.resume_goal(TARGET, GOAL, 123)
    assert error.value.goal_clicked and state["clicked"] == state["restored"] == 1


def test_clipboard_restore_failure_after_activation_remains_uncertain(monkeypatch):
    state, button, frame = fixture(monkeypatch)
    class BrokenClipboard:
        def restore(self): raise RuntimeError("clipboard restoration failed")
    monkeypatch.setattr(ui, "ClipboardSnapshot", BrokenClipboard)
    with pytest.raises(RuntimeError, match="clipboard restoration") as error:
        ui.resume_goal(TARGET, GOAL, 123)
    assert error.value.goal_clicked and state["clicked"] == 1


@pytest.mark.parametrize('matching', [True, False])
def test_sidebar_fallback_verifies_duplicate_titles_before_opening(monkeypatch, matching):
    clock=[0]
    def now():
        clock[0]+=.1
        return clock[0]
    monkeypatch.setattr(ui,'time',SimpleNamespace(monotonic=now,sleep=lambda _:None))
    selected = ['other']
    clicked, verified = [], []
    wrong = Node('Duplicate title', action=lambda _: pytest.fail('Opened a different chat with the same title'))
    right = Node('Duplicate title')
    def open_row(_):
        clicked.append('chosen')
        selected[0] = 'chosen'
        return True
    right.action = open_row
    frame = Node('Frame', 'frame')
    monkeypatch.setattr(ui, 'visible_frame', lambda _: frame)
    monkeypatch.setattr(ui, 'current_chat_id', lambda _: selected[0])
    monkeypatch.setattr(ui, 'sidebar_rows', lambda _: [wrong, right] if matching else [wrong])
    def identity(pid, row):
        value = 'chosen' if row is right else 'other'
        verified.append(value)
        return value
    monkeypatch.setattr(ui, 'row_chat_id', identity)
    monkeypatch.setattr(ui, 'active_window', lambda _: 1)
    monkeypatch.setattr(ui.subprocess, 'run', lambda *a, **k: None)
    if matching:
        assert ui.show_chat(TARGET, 123) is frame
        assert verified == ['other', 'chosen'] and clicked == ['chosen']
    else:
        with pytest.raises(RuntimeError, match='exact selected chat ID'):
            ui.show_chat(TARGET, 123)
        assert not clicked


@pytest.mark.parametrize('menu_stays_open', [False, True])
def test_copy_identity_never_sends_escape_to_active_goal(monkeypatch, menu_stays_open):
    state = {'menu': False, 'clipboard': '', 'trigger_clicks': 0, 'pointer': []}
    class Accessible(Node):
        def __init__(self, *args, showing=lambda: True, expanded=lambda: False, **kwargs):
            super().__init__(*args, **kwargs)
            self.showing, self.expanded = showing, expanded
        def getAttributes(self):
            return ['haspopup:menu'] if self.name == 'Copy' and self.role == 'menu item' else []
        def getState(self):
            return SimpleNamespace(contains=lambda flag: self.showing() if flag == ui.Atspi.StateType.SHOWING else self.expanded() if flag == ui.Atspi.StateType.EXPANDED else True)
        def queryComponent(self):
            return SimpleNamespace(getExtents=lambda _: SimpleNamespace(x=10,y=10,width=100,height=20))
    def toggle(_):
        state['menu'] = not state['menu']
        state['trigger_clicks'] += 1
        return True
    def copy_link(_):
        state['clipboard'] = 'codex://threads/chosen'
        state['menu'] = menu_stays_open
        return True
    row = Accessible('Chosen')
    trigger = Accessible('Chat actions', action=toggle, expanded=lambda: state['menu'])
    group = Accessible('Group', 'group', [row,trigger]);row.parent=group
    link = Accessible('Copy deeplink', 'menu item', action=copy_link, showing=lambda: state['menu'])
    submenu = Accessible('Copy', 'menu', [link], showing=lambda: state['menu'])
    copy = Accessible('Copy', 'menu item', showing=lambda: state['menu'])
    menu = Accessible('Chat actions', 'menu', [copy,submenu], showing=lambda: state['menu'])
    frame = Accessible('Frame', 'frame', [group,menu])
    clipboard = SimpleNamespace(set_text=lambda text,*_: state.update(clipboard=text), wait_for_text=lambda: state['clipboard'])
    monkeypatch.setattr(ui, 'Gtk', SimpleNamespace(Clipboard=SimpleNamespace(get=lambda _: clipboard)))
    monkeypatch.setattr(ui, 'visible_frame', lambda _: frame)
    monkeypatch.setattr(ui, 'active_window', lambda _: 1)
    def pointer(args, **kwargs):
        assert args[:2] == ['xdotool','mousemove'], 'Keyboard cleanup could cancel the goal'
        state['pointer'].append(args)
    monkeypatch.setattr(ui.subprocess, 'run', pointer)
    assert ui.row_chat_id(123,row) == 'chosen'
    assert not state['menu']
    assert state['trigger_clicks'] == (2 if menu_stays_open else 1)


@pytest.mark.parametrize("status", ["error", "systemError", "future"])
def test_error_goal_can_use_native_resume_button(monkeypatch, status):
    state, button, frame = fixture(monkeypatch)
    state["goal"]["status"] = status
    expected = deepcopy(state["goal"])
    ui.resume_goal(TARGET, expected, 123)
    assert state["clicked"] == 1 and state["goal"]["status"] == "active"


def navigation_clock(monkeypatch):
    clock=[0]
    def now():
        clock[0]+=.1
        return clock[0]
    monkeypatch.setattr(ui,'time',SimpleNamespace(monotonic=now,sleep=lambda _:None))
    monkeypatch.setattr(ui.subprocess,'run',lambda *a,**kw:None)
    monkeypatch.setattr(ui,'active_window',lambda _:1)


def test_deeplink_waits_for_target_id_not_just_visible_window(monkeypatch):
    navigation_clock(monkeypatch)
    frame=Node('Frame','frame')
    monkeypatch.setattr(ui,'visible_frame',lambda _:frame)
    ids=iter(['other','other','chosen'])
    monkeypatch.setattr(ui,'current_chat_id',lambda _:next(ids,'chosen'))
    monkeypatch.setattr(ui,'sidebar_rows',lambda _:[])
    assert ui.show_chat(TARGET,123) is frame


def test_collapsed_project_is_expanded_before_exact_id_candidate_open(monkeypatch):
    from dataclasses import replace
    navigation_clock(monkeypatch)
    state={'expanded':False,'selected':'other','clicked':[]}
    frame=Node('Frame','frame')
    def expand(_):
        state['expanded']=True
        return True
    project=Node('A project',action=expand)
    project.getState=lambda:SimpleNamespace(contains=lambda flag:state['expanded'] if flag==ui.Atspi.StateType.EXPANDED else True)
    chosen=Node('Duplicate title · Usage limited',children=[Node('Duplicate title','static')])
    def select(_):
        state['clicked'].append('chosen');state['selected']='chosen';return True
    chosen.action=select
    monkeypatch.setattr(ui,'visible_frame',lambda _:frame)
    monkeypatch.setattr(ui,'current_chat_id',lambda _:state['selected'])
    monkeypatch.setattr(ui,'sidebar_rows',lambda _:[project,chosen] if state['expanded'] else [project])
    monkeypatch.setattr(ui,'row_chat_id',lambda pid,row:'chosen' if row is chosen else pytest.fail('Project used as chat identity'))
    assert ui.show_chat(replace(TARGET,project_name='A project'),123) is frame
    assert state['expanded'] and state['clicked']==['chosen']


def test_stale_frame_and_accessible_row_are_requeried(monkeypatch):
    navigation_clock(monkeypatch)
    first,second=Node('Old frame','frame'),Node('New frame','frame')
    frames=iter([first,second,second,second])
    monkeypatch.setattr(ui,'visible_frame',lambda _:next(frames,second))
    selection=['other'];selected=Node('Duplicate title',action=lambda _:selection.__setitem__(0,'chosen') or True)
    stale=Node('Duplicate title')
    monkeypatch.setattr(ui,'current_chat_id',lambda _:selection[0])
    monkeypatch.setattr(ui,'sidebar_rows',lambda f:[stale] if f is first else [selected])
    def identity(pid,row):
        if row is stale:raise RuntimeError('Defunct accessibility row')
        return 'chosen'
    monkeypatch.setattr(ui,'row_chat_id',identity)
    assert ui.show_chat(TARGET,123) is second


def test_identity_check_failure_after_click_does_not_claim_no_goal_sent(monkeypatch):
    state, button, frame = fixture(monkeypatch)
    calls = [0]
    def identity(_):
        calls[0] += 1
        if calls[0] > 1:
            raise RuntimeError("Codex's native control was not available; no Goal action sent")
        return 'chosen'
    monkeypatch.setattr(ui,'current_chat_id',identity)
    with pytest.raises(RuntimeError,match='goal may already be running') as error:
        ui.resume_goal(TARGET,GOAL,123)
    assert error.value.goal_clicked and state['clicked']==1
    assert 'no Goal action sent' not in str(error.value)
