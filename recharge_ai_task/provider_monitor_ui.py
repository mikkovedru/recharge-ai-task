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


class ProviderDetails(Gtk.Box):
    """Visible provider fields, grouped into two columns when there is room."""
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=8)
        self.identity = self._label()
        self.alerts = self._label()
        self.quota = self._label()
        self.automation = self._label()
        self.labels = (self.identity, self.alerts, self.quota, self.automation)
        self.pack_start(self.identity, False, False, 0)
        self.pack_start(self.alerts, False, False, 0)
        self.columns = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,
            column_spacing=20, row_spacing=8, min_children_per_line=1, max_children_per_line=2)
        self.columns.get_style_context().add_class('provider-details-columns')
        for label in (self.quota, self.automation):
            section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            section.set_size_request(300, -1)
            section.pack_start(label, False, False, 0)
            self.columns.add(section)
            section.get_parent().set_can_focus(False)
        self.pack_start(self.columns, False, False, 0)
        self.alerts.set_no_show_all(True)

    @staticmethod
    def _label():
        label = Gtk.Label(xalign=0, yalign=0, wrap=True, selectable=True)
        label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_width_chars(1)
        label.set_max_width_chars(1)
        label.set_hexpand(True)
        label.set_valign(Gtk.Align.START)
        return label

    def update(self, identity, quota, automation, alerts=''):
        for label, value in ((self.identity, identity), (self.quota, quota),
                             (self.automation, automation), (self.alerts, alerts)):
            update_selectable_markup(label, value)
        self.alerts.set_visible(bool(alerts))

    def get_text(self):
        """Return the same information that is visibly presented in the page."""
        return '\n'.join(label.get_text() for label in self.labels if label.get_text())


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
            .provider-details-columns > flowboxchild { padding: 0; }
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
        self.all_tab = Gtk.Label(label='All')
        self.append_page(self._scroll(summary), self.all_tab)
        for provider, caption in NAMES.items():
            body = ProviderDetails()
            self.selection_labels.extend(body.labels)
            tab=Gtk.Label(label=caption)
            header=Gtk.Box(spacing=3)
            notice=ProviderNotice()
            header.pack_start(tab,False,False,0)
            header.pack_start(notice,False,False,0)
            header.show_all()
            self.append_page(self._scroll(body),header)
            self.tab_notices[provider]=notice
            self.tab_headers[provider]=header
            self.pages[provider]=body
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
        def tone(text, level='normal'):
            value = escape(text)
            return f'<span foreground="{colors[level]}">{value}</span>' if level in colors else value
        active_states = [status['state'] for status in statuses.values() if status['installed']]
        overall = next((state for state in ('error', 'warning', 'enabled') if state in active_states), 'off')
        all_markup = tone('All', 'success' if overall == 'enabled' else overall)
        if self.all_tab.get_label() != all_markup:
            self.all_tab.set_markup(all_markup)
        self.all_tab.get_accessible().set_name('All providers: '+overall)
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
            caption = NAMES[provider]
            caption_markup = tone(caption, ('success' if level == 'enabled' else level) if installed else 'normal')
            if self.tab_labels[provider].get_label() != caption_markup:
                self.tab_labels[provider].set_markup(caption_markup)
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
            page = self.pages[provider]
            identity = f'<b>{title}</b>'
            if status.get('terminal_only'):
                identity += ' · Wrapped terminal'
                if installation:
                    identity += ' · '+installation
                observed = status.get('terminal_observations', [])
                observations = '\n'.join(tone(line, 'warning' if level == 'warning' else 'success' if level == 'enabled' else 'normal') for line in observed)
                instructions = '<b>Start:</b> '+escape(status['command'])+'\n'+escape(status['notices'])
                if not installed:
                    instructions += '\nInstall the provider CLI and sign in first.'
                page.update(identity, '<b>Wrapped sessions</b>\n'+observations, instructions)
                continue
            identity += ' · Plan: '+escape(status['plan'])
            if installation:
                identity += ' · '+installation
            availability_level = ('error' if status['error'] else 'warning' if status['availability'] == 'Quota unavailable'
                                  else 'error' if status['availability'] == 'Quota exhausted' else 'success')
            quota = [tone(status['availability'], availability_level)+' · '+escape(status['freshness'])]
            for name, used, timing in status['windows']:
                left = max(0, min(100, 100-used))
                quota.append(tone(f'{name}: {left:g}% left', 'error' if left <= 0 else 'warning' if left <= 15 else 'normal')+' · '+escape(timing))
            if status.get('credits'):
                quota.append(tone(status['credits'], 'success'))
            check_level = ('error' if status['check'] == 'Needs attention' else 'warning' if status['check'] in
                           ('Unavailable', 'Checking…', 'Updating…', 'Waiting', 'Waiting…') else 'success' if status['monitored'] else 'normal')
            quota.append('<b>Next check:</b> '+tone(status['check'], check_level)+' · '+escape(status['check_detail'])+f' · refresh every {poll_seconds}s')
            recovery_level = ('success' if status['recovery'].startswith('Send:') else 'warning' if
                              status['recovery'].startswith(('Forecast:', 'Waiting', 'Schedule unavailable', 'Updating')) else
                              'error' if status['recovery'] == 'Monitoring needs attention' else 'normal')
            automation = ['<b>Recovery:</b> '+tone(status['recovery'], recovery_level)+' · '+escape(status['countdown'])]
            # A zero pending batch repeats "No send scheduled"; actual pending
            # action counts remain visible separately from remaining allowance.
            if status['actions'] != '0 messages · 0 Goal activations':
                automation.append(escape(status['actions']))
            automation += [escape(status['selection']), escape(status['stats'])]
            alerts = []
            if status['error']:
                alerts.append(tone(status['error'], 'error'))
            if status['notices']:
                alerts.append(tone(status['notices'], 'warning'))
            if not installed:
                alerts.append('Provider not detected')
            page.update(identity, '\n'.join(quota), '\n'.join(automation), '\n'.join(alerts))
