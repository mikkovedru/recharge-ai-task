"""Shared desktop menu metadata for portable and Debian installations."""

COMMENT = "Continue OpenAI Codex, Anthropic Claude Code, Meta Muse Code, Google Gemini/Antigravity and OpenCode tasks after usage limits reset"
GENERIC_NAME = "AI task continuation"
KEYWORDS = ("AI", "Codex", "OpenAI", "Claude", "Anthropic", "Muse", "Meta", "FB", "Facebook", "Google", "Gemini", "Antigravity", "agy", "OpenCode", "quota", "rate limit", "token", "automation", "terminal", "restart", "reset", "5h", "weekly", "restriction", "programming", "developing", "code", "vibe coding")
# Keep exact old generated entries recognizable when search metadata changes.
PREVIOUS_SEARCH_METADATA = (('Continue OpenAI Codex, Anthropic Claude Code, Meta Muse Code and OpenCode tasks after usage limits reset',
  ('AI', 'Codex', 'OpenAI', 'Claude', 'Anthropic', 'Muse', 'Meta', 'FB', 'Facebook', 'OpenCode', 'quota',
   'rate limit', 'token', 'automation', 'terminal', 'restart', 'reset', '5h', 'weekly', 'restriction',
   'programming', 'developing', 'code', 'vibe coding')),
 ('Continue Codex, Claude Code, Muse Code and OpenCode tasks after usage limits reset',
  ('AI', 'Codex', 'OpenAI', 'Claude', 'Anthropic', 'Muse', 'Meta', 'OpenCode', 'quota', 'rate limit', 'token',
   'automation', 'terminal')))
HOMEPAGE = "https://github.com/mikkovedru/recharge-ai-task"


def desktop_entry(command, icon, *, name="Recharge AI-task", homepage=HOMEPAGE, installed=False, comment=COMMENT, keywords=KEYWORDS):
    """Render both launchers, keeping executable quoting with the caller."""
    fields = [
        "[Desktop Entry]", "Type=Application", "Version=1.0", f"Name={name}",
        f"GenericName={GENERIC_NAME}", f"Comment={comment}",
        f"Keywords={';'.join(keywords)};", f"Exec={command}", f"Icon={icon}",
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
