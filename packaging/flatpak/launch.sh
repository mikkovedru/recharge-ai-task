#!/bin/sh
# This launcher is for the standalone distribution, which uses native providers.
set -eu

binary=/app/libexec/recharge-ai-task
case ${1-} in
    --sandboxed)
        shift
        exec "$binary" "$@"
        ;;
    --install-desktop)
        printf '%s\n' 'Flatpak supplies the application menu entry.'
        exit 0
        ;;
    --uninstall)
        printf 'Remove this package with flatpak uninstall %s\n' "$FLATPAK_ID"
        exit 0
        ;;
esac

# Flatpak records the host path of this exact deployment in the instance metadata.
app_path=$(sed -n '/^\[Instance\]/,/^\[/s/^app-path=//p' /.flatpak-info)
case "$app_path" in
    /*) ;;
    *) printf '%s\n' 'The Recharge AI-task Flatpak deployment path is unavailable.' >&2; exit 1 ;;
esac
case "$PWD" in
    /|/app|/app/*) directory=$HOME ;;
    *) directory=$PWD ;;
esac

# The host session helper supplies the real desktop session environment. Forward
# explicit profile overrides and terminal type without copying sandbox paths.
set -- "$app_path/libexec/recharge-ai-task" "$@"
if [ -n "${RECHARGE_AI_TASK_CONFIG_DIR-}" ]; then
    set -- "--env=RECHARGE_AI_TASK_CONFIG_DIR=$RECHARGE_AI_TASK_CONFIG_DIR" "$@"
fi
if [ -n "${CODEX_HOME-}" ]; then
    set -- "--env=CODEX_HOME=$CODEX_HOME" "$@"
fi
if [ -n "${CLAUDE_CONFIG_DIR-}" ]; then
    set -- "--env=CLAUDE_CONFIG_DIR=$CLAUDE_CONFIG_DIR" "$@"
fi
if [ -n "${TERM-}" ]; then
    set -- "--env=TERM=$TERM" "$@"
fi
exec flatpak-spawn --host --directory="$directory" --env=RECHARGE_AI_TASK_FLATPAK_HOST=1 "$@"
