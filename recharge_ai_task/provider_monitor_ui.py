"""Framed provider tabs for quota availability, recovery schedules and statistics."""
from gi.repository import GLib, Gtk, Pango
from .provider_monitor import NAMES
from .provider_ui import ProviderNotice
from .status_display import status_colors


def update_selectable_markup(label, markup):
    """Refresh changing quota text without discarding a deliberate selection."""
    if label.get_label() == markup:
        return
    selected, start, end = label.get_selection_bounds()
    label.set_markup(markup)
    if selected:
        label.select_region(start, end)


class ProviderMonitor(Gtk.Notebook):
    def __init__(self, summary):
        super().__init__()
        self.set_scrollable(True)
        self.get_style_context().add_class('provider-monitor')
        self.compact_css=Gtk.CssProvider()
        self.compact_css.load_from_data(b'''
            notebook.provider-monitor > header > tabs > tab { padding: 4px 5px; min-width: 0; }
            .provider-tab-passive { background-color: alpha(@theme_fg_color, .07); border-radius: 3px; padding: 1px 3px; }
            .provider-tab-passive label { font-style: italic; }
        ''')
        self.get_style_context().add_provider_for_screen(self.get_screen(),self.compact_css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.connect('destroy',lambda *_:Gtk.StyleContext.remove_provider_for_screen(self.get_screen(),self.compact_css))
        self.set_hexpand(True)
        self.pages = {}
        self.tab_labels = {}
        self.tab_notices = {}
        self.tab_headers = {}
        self.selection_labels = []
        def register_labels(widget):
            if isinstance(widget, Gtk.Label) and widget.get_selectable():
                self.selection_labels.append(widget)
            elif isinstance(widget, Gtk.Container):
                for child in widget.get_children():
                    register_labels(child)
        register_labels(summary)
        self.append_page(self._scroll(summary), Gtk.Label(label='All'))
        for provider, caption in NAMES.items():
            body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5,margin=8)
            label=Gtk.Label(xalign=0,yalign=0,wrap=True,selectable=True)
            self.selection_labels.append(label)
            label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            label.set_width_chars(1)
            body.pack_start(label,False,False,0)
            tab=Gtk.Label(label=caption)
            header=Gtk.Box(spacing=3)
            notice=ProviderNotice()
            header.pack_start(tab,False,False,0)
            header.pack_start(notice,False,False,0)
            header.show_all()
            self.append_page(self._scroll(body),header)
            self.tab_notices[provider]=notice
            self.tab_headers[provider]=header
            self.pages[provider]=label
            self.tab_labels[provider]=tab
        self.connect('switch-page', self._clear_selection)

    def _clear_selection(self, *_):
        # GTK focuses selectable labels on page changes and selects their text.
        # Keep text copyable without letting that focus highlight the whole page.
        def clear():
            for label in self.selection_labels:
                label.select_region(0, 0)
            return False
        GLib.idle_add(clear)

    @staticmethod
    def _scroll(widget):
        scroll=Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(110)
        scroll.set_max_content_height(155)
        scroll.set_propagate_natural_height(True)
        scroll.add(widget)
        return scroll

    def update(self, statuses, poll_seconds):
        colors=status_colors(self)
        escape=GLib.markup_escape_text
        for provider, status in statuses.items():
            level=status['state']
            installed = status['installed']
            # Keep the pages readable, including their installation explanation.
            # Only the tab caption is passive when the provider is absent.
            self.tab_headers[provider].set_sensitive(installed)
            context = self.tab_headers[provider].get_style_context()
            if installed:
                context.remove_class('provider-tab-passive')
            else:
                context.add_class('provider-tab-passive')
            # A text marker also distinguishes absent providers without relying
            # on theme-dependent disabled colors or color perception.
            caption = NAMES[provider] + (' —' if not installed else '')
            if self.tab_labels[provider].get_text() != caption:
                self.tab_labels[provider].set_text(caption)
            title=escape(NAMES[provider])
            notice=self.tab_notices[provider]
            notice.update(level)
            if level in ('warning','error'):
                color=colors['warning' if level=='warning' else 'error']
                if getattr(notice, 'notice_color', None)!=color:
                    css=Gtk.CssProvider()
                    css.load_from_data(f"image {{ color: {color}; }}".encode())
                    if hasattr(notice, 'color_css'):
                        notice.icon.get_style_context().remove_provider(notice.color_css)
                    notice.icon.get_style_context().add_provider(css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
                    notice.color_css=css
                    notice.notice_color=color
            self.tab_labels[provider].get_accessible().set_name(NAMES[provider]+': '+(level if installed else 'not installed'))
            tooltip=status['selection']+'\n'+(status['error'] or status['notices'] or ('Monitoring on' if status['monitored'] else 'Monitoring off'))
            installation = status.get('installation', '')
            if installation:
                tooltip = installation + '\n' + tooltip
            if self.tab_headers[provider].get_tooltip_text()!=tooltip:
                self.tab_headers[provider].set_tooltip_text(tooltip)
            installation = escape(' · '.join(installation.splitlines()))
            if status.get('terminal_only'):
                lines=[f'<b>{title}</b> · Wrapped terminal' + (' · '+installation if installation else ''),
                       '<b>Start:</b> '+escape(status['command']),
                       escape(status['notices'])]
                if not installed:
                    lines.append('Install the provider CLI and sign in first.')
                update_selectable_markup(self.pages[provider], '\n'.join(lines))
                continue
            lines=[f'<b>{title}</b> · Plan: '+escape(status['plan']) + (' · '+installation if installation else ''),
                   escape(status['availability'])+' · '+escape(status['freshness'])+f' · refresh every {poll_seconds}s']
            if status['error']:
                lines.append(f'<span foreground="{colors["error"]}">'+escape(status['error'])+'</span>')
            if status['notices']:
                lines.append(f'<span foreground="{colors["warning"]}">'+escape(status['notices'])+'</span>')
            for name,used,timing in status['windows']:
                text=escape(f'{name}: {used:g}% used')
                threshold='error' if used>=100 else 'warning' if used>=85 else None
                if threshold:text=f'<span foreground="{colors[threshold]}">{text}</span>'
                lines.append(text+' · '+escape(timing))
            if not status['installed']:lines.append('Provider not detected')
            lines += ['<b>Next check:</b> '+escape(status['check'])+' · '+escape(status['check_detail']),
                      '<b>Recovery:</b> '+escape(status['recovery'])+' · '+escape(status['countdown']),
                      escape(status['actions']),escape(status['selection']),escape(status['stats'])]
            update_selectable_markup(self.pages[provider], '\n'.join(lines))
