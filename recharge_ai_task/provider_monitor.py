"""Provider-scoped monitoring presentation; no quota fetches or delivery side effects."""
from datetime import datetime
from .config import PROVIDERS, PROVIDER_SHORT_NAMES, TERMINAL_PROVIDERS
from .delivery_policy import Usage, effective_limit
from .quota import quota_blocked, quota_windows
from .status_display import watch_check_summary, send_schedule_summary

NAMES = PROVIDER_SHORT_NAMES


def observations(runtime):
    runtime = runtime or {}
    progress = runtime.get('watch_progress') or {}
    if isinstance(progress.get('providers'), dict):
        return progress['providers']
    provider = (runtime.get('watch_settings') or {}).get('provider', 'codex')
    return {provider: progress} if runtime.get('desktop_watch') and provider in PROVIDERS else {}


def scoped_runtime(runtime, provider):
    if runtime is None:
        return None
    result = dict(runtime)
    progress = observations(runtime).get(provider)
    if progress is None:
        result.update(desktop_watch=False, watch_requested=False)
    result['watch_progress'] = progress or {}
    return result


def statistics(targets, config, usage):
    messages = goals = used_messages = used_goals = uncertain = 0
    for target in targets:
        allowed = {}
        prompt, goal = target.signal_actions()
        for action, enabled in (("prompt", prompt), ("goal", goal)):
            value = usage.get((target.key, action), Usage())
            if action == "prompt":
                used_messages += value.used
            else:
                used_goals += value.used
            uncertain += value.uncertain
            limit = effective_limit(target, action, config) if enabled else 0
            allowed[action] = enabled and (limit is None or value.used < limit)
        # The sender withholds a selected message when its Goal allowance is spent.
        messages += allowed["prompt"] and (not goal or allowed["goal"])
        goals += allowed["goal"]
    return dict(recipients=len(targets), messages=messages, goals=goals,
                used_messages=used_messages, used_goals=used_goals, uncertain=uncertain)


def provider_status(provider, *, targets, config, usage, quota=None, error='', notices='',
                    checked_at=None, runtime=None, installed=True, now=0, usage_error=''):
    if provider in TERMINAL_PROVIDERS:
        if provider == 'opencode':
            from .opencode import LIMITATION
        else:
            from .google_ai import limitation
            LIMITATION = limitation(provider)
        return dict(provider=provider, terminal_only=True, state='off', installed=installed,
                    enabled=False, monitored=False, selection='Wrapped interactive terminals only; no dashboard recipients.',
                    error='', notices=LIMITATION, command=f'recharge-ai-task run --provider {provider}')
    selected = [t for t in targets if t.provider == provider]
    try:
        counts = statistics(selected, config, usage)
    except (ValueError, TypeError) as exc:
        usage_error = str(exc)
        counts = dict(recipients=len(selected), messages=0, goals=0, used_messages=0, used_goals=0, uncertain=0)
    enabled = counts['messages'] + counts['goals'] > 0
    state = 'enabled' if enabled else 'off'
    if error:state = 'error' if enabled else 'warning'
    elif notices or usage_error or counts['uncertain']:state = 'warning'
    elif quota and (quota_blocked(quota) or any(w.used_percent >= 85 for w in quota_windows(quota))):state = 'warning'
    elif checked_at and now-checked_at>max(45,config.poll_seconds*2):state='warning'
    scoped = scoped_runtime(runtime, provider)
    check, check_detail = watch_check_summary(scoped, now)
    recovery, countdown, actions = send_schedule_summary(scoped, now, config.grace_seconds)
    if scoped and not scoped.get('desktop_watch') and not scoped.get('restarting'):
        check, check_detail = 'Not monitored', 'Start monitoring with a recipient from this provider selected.'
    if not installed and not selected:
        check, check_detail = 'Not detected', 'Install this provider or open a supported native app.'
    freshness = ('Updated ' + datetime.fromtimestamp(checked_at).astimezone().strftime('%H:%M:%S') +
                 f' · {max(0,int(now-checked_at))}s ago') if checked_at else 'No successful quota observation yet'
    if error and quota:freshness = 'Last known quota · current refresh failed · ' + freshness
    elif checked_at and now-checked_at>max(45,config.poll_seconds*2):freshness='Stale quota observation · '+freshness
    windows = []
    if quota:
        for window in quota_windows(quota):
            name = window.label or ('5-hour' if window.window_duration_mins==300 else 'Weekly' if window.window_duration_mins==10080 else f'{window.window_duration_mins}-minute')
            if window.resets_at:
                seconds=max(0,int(window.resets_at-now));days,remainder=divmod(seconds,86400);hours,remainder=divmod(remainder,3600);minutes,seconds=divmod(remainder,60)
                reset=datetime.fromtimestamp(window.resets_at).astimezone().strftime('%a %d %b %H:%M:%S')
                timing=f'resets {reset} ({str(days)+"d " if days else ""}{hours:02}:{minutes:02}:{seconds:02})'
            else:timing='window not started'
            windows.append((name, window.used_percent, timing))
    noun = "recipient" if counts["recipients"] == 1 else "recipients"
    details = f"{counts['recipients']} selected {noun} · {counts['messages']} message / {counts['goals']} Goal actions with allowance remaining"
    stats = f"Used: {counts['used_messages']} messages · {counts['used_goals']} Goal activations · {counts['uncertain']} unconfirmed"
    if usage_error:stats='Usage statistics unavailable: '+usage_error
    return dict(provider=provider, state=state, counts=counts, enabled=enabled,
        plan=quota.plan_type if quota else 'Unavailable', windows=windows,
        availability='Quota unavailable' if error or quota is None else 'Quota exhausted' if quota_blocked(quota) else 'Quota available',
        error=error, notices=notices, freshness=freshness, check=check, check_detail=check_detail,
        recovery=recovery, countdown=countdown, actions=actions, selection=details, stats=stats,
        monitored=bool(scoped and scoped.get('desktop_watch')), installed=installed)
