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


@pytest.fixture(autouse=True)
def isolated_accessibility_transport(monkeypatch):
    monkeypatch.setattr(ui, "_application_bus", None)
    monkeypatch.setattr(ui, "ApplicationBus", lambda **kwargs: SimpleNamespace(application=lambda _: None))


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
    monkeypatch.setattr(ui, "active_window", lambda pid: 1)
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
@pytest.mark.parametrize('failure', [None, 'not-submenu', 'rejected', 'not-expanded', 'missing-link'])
def test_copy_identity_never_sends_escape_to_active_goal(monkeypatch, menu_stays_open, failure):
    state = {'menu': False, 'submenu': False, 'clipboard': '', 'trigger_clicks': 0, 'pointer': [], 'copied': False}
    class Accessible(Node):
        def __init__(self, *args, showing=lambda: True, expanded=lambda: False, **kwargs):
            super().__init__(*args, **kwargs)
            self.showing, self.expanded = showing, expanded
        def getAttributes(self):
            return ['haspopup:menu'] if self.name == 'Copy' and self.role == 'menu item' and failure != 'not-submenu' else []
        def getState(self):
            return SimpleNamespace(contains=lambda flag: self.showing() if flag == ui.Atspi.StateType.SHOWING else self.expanded() if flag == ui.Atspi.StateType.EXPANDED else True)
        def queryComponent(self):
            return SimpleNamespace(getExtents=lambda _: SimpleNamespace(x=10,y=10,width=100,height=20))
    def toggle(_):
        state['menu'] = not state['menu']
        state['trigger_clicks'] += 1
        return True
    def copy_link(_):
        state['copied'] = True
        state['clipboard'] = 'codex://threads/chosen'
        state['menu'] = menu_stays_open
        return True
    row = Accessible('Chosen')
    trigger = Accessible('Chat actions', action=toggle, expanded=lambda: state['menu'])
    group = Accessible('Group', 'group', [row,trigger]);row.parent=group
    link = Accessible('Copy deeplink', 'menu item', action=copy_link, showing=lambda: state['menu'] and failure != 'missing-link')
    submenu = Accessible('Copy', 'menu', [link], showing=lambda: state['menu'] and state['submenu'])
    def open_submenu(_):
        assert failure != 'not-submenu', 'Activated an ordinary copy-content action'
        state['submenu'] = failure != 'not-expanded'
        return failure != 'rejected'
    copy = Accessible('Copy', 'menu item', action=open_submenu, showing=lambda: state['menu'])
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
    clock = [0]
    def now():
        clock[0] += .5
        return clock[0]
    monkeypatch.setattr(ui, 'time', SimpleNamespace(monotonic=now, sleep=lambda _: None))
    if failure:
        expected = {'not-submenu': 'Copy submenu', 'rejected': 'Copy submenu',
                    'not-expanded': 'Copy submenu was not available', 'missing-link': 'Copy deeplink'}[failure]
        with pytest.raises(RuntimeError, match=expected): ui.row_chat_id(123, row)
        assert not state['copied']
    else:
        assert ui.row_chat_id(123,row) == 'chosen' and state['copied']
    assert not state['menu']
    assert state['trigger_clicks'] == (2 if failure or menu_stays_open else 1)
    assert not state['pointer'], 'Native submenu navigation must not depend on pointer hover'


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


def test_missing_accessibility_bus_fails_before_clipboard_or_navigation(monkeypatch):
    def broken(**kwargs):raise ui.AccessibilityUnavailable('Advertised socket is missing; no Goal action sent')
    monkeypatch.setattr(ui,'ApplicationBus',broken)
    monkeypatch.setattr(ui,'ClipboardSnapshot',lambda:pytest.fail('Clipboard touched while transport was unavailable'))
    monkeypatch.setattr(ui.subprocess,'run',lambda *a,**k:pytest.fail('Opened a chat while transport was unavailable'))
    with pytest.raises(ui.AccessibilityUnavailable,match='Advertised socket is missing'):
        ui.resume_goal(TARGET,GOAL,123)


def test_bus_failure_is_not_misreported_as_wrong_chat_identity(monkeypatch):
    navigation_clock(monkeypatch)
    calls=[]
    def frame(_):
        calls.append(True)
        raise ui.AccessibilityUnavailable('Desktop accessibility connection is unavailable; no Goal action sent')
    monkeypatch.setattr(ui,'visible_frame',frame)
    with pytest.raises(ui.AccessibilityUnavailable) as error:ui.show_chat(TARGET,123)
    assert len(calls)==1 and 'Could not open the exact selected chat ID' not in str(error.value)


def test_frame_reconnection_rechecks_the_same_active_pid(monkeypatch):
    active=[];closed=[];scoped=[]
    frame=Node('Frame','frame')
    frame.getState=lambda:SimpleNamespace(contains=lambda _:True)
    def failed(pid):
        scoped.append(pid)
        raise ui.AccessibilityUnavailable('connection closed')
    first=SimpleNamespace(application=failed,close=lambda:closed.append(True))
    second=SimpleNamespace(application=lambda pid:scoped.append(pid) or [frame])
    monkeypatch.setattr(ui,'_application_bus',first)
    monkeypatch.setattr(ui,'ApplicationBus',lambda **kwargs:second)
    monkeypatch.setattr(ui,'active_window',lambda pid:active.append(pid))
    monkeypatch.setattr(ui.time,'sleep',lambda _:None)
    assert ui.visible_frame(123) is frame
    assert active==scoped==[123,123] and closed==[True]


def test_focus_change_during_bus_retry_prevents_further_queries(monkeypatch):
    count=[0]
    first=SimpleNamespace(application=lambda _:(_ for _ in ()).throw(ui.AccessibilityUnavailable('closed')),close=lambda:None)
    monkeypatch.setattr(ui,'_application_bus',first)
    monkeypatch.setattr(ui,'ApplicationBus',lambda **kwargs:pytest.fail('Connected after another app gained focus'))
    def active(_):
        count[0]+=1
        if count[0]>1:raise RuntimeError('Another application has focus')
    monkeypatch.setattr(ui,'active_window',active)
    monkeypatch.setattr(ui.time,'sleep',lambda _:None)
    with pytest.raises(RuntimeError,match='Another application'):ui.visible_frame(123)


@pytest.mark.parametrize('failure', [ui.AccessibilityUnavailable, ui.AccessibilityTimeout])
def test_bus_failure_after_resume_stays_uncertain_and_is_not_replayed(monkeypatch, failure):
    state,button,frame=fixture(monkeypatch)
    def clicked(_):
        state['clicked']+=1
        raise failure('request failed; no Goal action sent')
    button.action=clicked
    with pytest.raises(RuntimeError,match='goal may already be running') as error:ui.resume_goal(TARGET,GOAL,123)
    assert state['clicked']==1 and error.value.goal_clicked
    assert 'no Goal action sent' not in str(error.value)


@pytest.mark.parametrize('entrypoint',['show_chat','resume_goal'])
def test_unregistered_codex_fails_before_clipboard_or_navigation(monkeypatch,entrypoint):
    pids=[]
    def application(pid):
        pids.append(pid)
        raise ui.AccessibilityUnavailable('Codex is not registered; fully quit and reopen Codex; no Goal action sent')
    monkeypatch.setattr(ui,'ApplicationBus',lambda **kwargs:SimpleNamespace(application=application,close=lambda:None))
    monkeypatch.setattr(ui,'ClipboardSnapshot',lambda:pytest.fail('Clipboard touched before registration'))
    monkeypatch.setattr(ui.subprocess,'run',lambda *a,**k:pytest.fail('Opened chat before registration'))
    with pytest.raises(ui.AccessibilityUnavailable,match='reopen Codex') as error:
        if entrypoint=='show_chat':ui.show_chat(TARGET,123)
        else:ui.resume_goal(TARGET,GOAL,123)
    assert pids==[123,123]
    assert 'exact selected chat ID' not in str(error.value)
    assert str(error.value).count('no Goal action sent')==1


def test_navigation_timeout_does_not_duplicate_no_action_suffix(monkeypatch):
    navigation_clock(monkeypatch)
    def frame(_):raise RuntimeError('Native sidebar unavailable; no Goal action sent')
    monkeypatch.setattr(ui,'visible_frame',frame)
    with pytest.raises(RuntimeError,match='exact selected chat ID') as error:
        ui.show_chat(TARGET,123)
    assert str(error.value).count('no Goal action sent')==1


def test_registration_preflight_reconnects_a_failed_transport_before_side_effects(monkeypatch):
    calls=[];closed=[]
    def stale(pid):
        calls.append(('old',pid))
        raise ui.AccessibilityUnavailable('connection closed')
    first=SimpleNamespace(application=stale,close=lambda:closed.append('old'))
    app=object()
    second=SimpleNamespace(application=lambda pid:calls.append(('new',pid)) or app)
    monkeypatch.setattr(ui,'_application_bus',first)
    monkeypatch.setattr(ui,'ApplicationBus',lambda **kwargs:second)
    monkeypatch.setattr(ui.time,'sleep',lambda _:None)
    assert ui.preflight_accessibility(123) is app
    assert calls==[('old',123),('new',123)] and closed==['old']


def test_focus_loss_after_chat_identity_check_never_presses_resume(monkeypatch):
    state, _, _ = fixture(monkeypatch)
    def lost(_): raise ui.FocusChanged('Another application has focus; no Goal action sent')
    monkeypatch.setattr(ui, 'active_window', lost)
    with pytest.raises(ui.FocusChanged) as error: ui.resume_goal(TARGET, GOAL, 123)
    assert state['clicked'] == 0 and state['restored'] == 1
    assert not error.value.goal_clicked


@pytest.mark.parametrize('control', ['visible sidebar row', 'sidebar Chat actions button',
    'Chat actions menu', 'Copy submenu', 'copied canonical chat ID'])
def test_native_wait_error_identifies_the_failed_control(monkeypatch, control):
    clock = iter([0, 1, 16])
    monkeypatch.setattr(ui, 'time', SimpleNamespace(monotonic=lambda: next(clock), sleep=lambda _: None))
    with pytest.raises(RuntimeError, match=control + ' was not available'):
        ui.wait_for(lambda: None, control=control)


def test_native_transport_uses_the_longer_request_deadline(monkeypatch):
    captured = []
    transport = object()
    monkeypatch.setattr(ui, 'ApplicationBus', lambda **kwargs: captured.append(kwargs) or transport)
    assert ui.accessibility_bus() is transport
    assert captured == [{'timeout_ms': 30000}]


def test_slow_control_can_appear_after_the_previous_three_second_wait(monkeypatch):
    clock = [0]
    monkeypatch.setattr(ui, 'time', SimpleNamespace(monotonic=lambda: clock[0], sleep=lambda delay: clock.__setitem__(0, clock[0] + delay)))
    assert ui.wait_for(lambda: 'ready' if clock[0] >= 8 else None) == 'ready'
    assert 8 <= clock[0] < 15


def test_request_timeout_is_not_reconnected_or_retried_as_navigation(monkeypatch):
    navigation_clock(monkeypatch)
    calls = []
    def slow(_):
        calls.append(True)
        raise ui.AccessibilityTimeout('GetChildren timed out; no Goal action sent')
    monkeypatch.setattr(ui, 'visible_frame', slow)
    with pytest.raises(ui.AccessibilityTimeout, match='GetChildren'):
        ui.show_chat(TARGET, 123)
    assert calls == [True]


def test_uri_dispatch_reacquires_verified_foreground_before_reading_identity(monkeypatch):
    navigation_clock(monkeypatch)
    order=[];frame=Node('Frame','frame')
    monkeypatch.setattr(ui,'focus_codex',lambda pid:order.append(('focus',pid)) or 1)
    monkeypatch.setattr(ui.subprocess,'run',lambda args,**kwargs:order.append(('dispatch',args[0])))
    monkeypatch.setattr(ui,'visible_frame',lambda pid:order.append(('frame',pid)) or frame)
    monkeypatch.setattr(ui,'current_chat_id',lambda pid:'chosen')
    assert ui.show_chat(TARGET,123) is frame
    assert order[:3]==[('focus',123),('dispatch','xdg-open'),('focus',123)]
    assert order[3][0]=='frame'


def test_later_focus_loss_reports_navigation_context_without_reacquiring(monkeypatch):
    navigation_clock(monkeypatch)
    focuses=[]
    monkeypatch.setattr(ui,'focus_codex',lambda pid:focuses.append(pid) or 1)
    def lost(_):raise ui.FocusChanged('Another application has focus; no Goal action sent')
    monkeypatch.setattr(ui,'visible_frame',lost)
    with pytest.raises(ui.FocusChanged,match=r'verifying chat chosen.*desktop PID 123.*Keep the intended Codex'):
        ui.show_chat(TARGET,123)
    assert focuses==[123,123]


def test_control_queries_do_not_walk_conversation_when_collection_is_available():
    class Frame(Node):
        def __iter__(self):pytest.fail('Traversed conversation instead of querying controls')
        def find_roles(self,roles):
            assert roles==('push button',)
            return [button]
    button=Node('Resume goal')
    assert list(ui.role_nodes(Frame('Frame','frame'),'push button'))==[button]


def test_control_queries_fall_back_when_collection_is_unavailable():
    class Frame(Node):
        def find_roles(self,roles):return None
    button=Node('Resume goal')
    assert list(ui.role_nodes(Frame('Frame','frame',[button]),'push button'))==[button]
