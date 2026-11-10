"""Shared desktop menu metadata for portable and Debian installations."""

COMMENT = "Continue OpenAI Codex, Anthropic Claude Code, Meta Muse Code and OpenCode tasks after usage limits reset"
GENERIC_NAME = "AI task continuation"
KEYWORDS = ("AI", "Codex", "OpenAI", "Claude", "Anthropic", "Muse", "Meta", "FB", "Facebook", "OpenCode", "quota", "rate limit", "token", "automation", "terminal", "restart", "reset", "5h", "weekly", "restriction", "programming", "developing", "code", "vibe coding")
HOMEPAGE = "https://github.com/mikkovedru/recharge-ai-task"


def desktop_entry(command, icon, *, name="Recharge AI-task", homepage=HOMEPAGE, installed=False):
    """Render both launchers, keeping executable quoting with the caller."""
    fields = [
        "[Desktop Entry]", "Type=Application", "Version=1.0", f"Name={name}",
        f"GenericName={GENERIC_NAME}", f"Comment={COMMENT}",
        f"Keywords={';'.join(KEYWORDS)};", f"Exec={command}", f"Icon={icon}",
        "Terminal=false", "Categories=Utility;", "StartupNotify=false",
        "StartupWMClass=recharge-ai-task-tray",
    ]
    if installed:
        fields += ["Actions=Uninstall;Website;", "", "[Desktop Action Uninstall]",
                   "Name=Uninstall Recharge AI-task…", f"Exec={command} --uninstall",
                   "Icon=system-software-install"]
    else:
        fields += ["X-Recharge-AI-Task-Managed=true", "Actions=Website;"]
    fields += ["", "[Desktop Action Website]", "Name=Project on GitHub",
               f"Exec=xdg-open {homepage}", "Icon=web-browser", ""]
    return "\n".join(fields)
