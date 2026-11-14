# Shared pane dividers

All resizable workspace dividers are created by `WindowLayout.pane`. It applies the `workspace-divider` class and GTK's wide handle to every pane, in either orientation. The class identifies the group; divider appearance remains native to the active GTK theme. Do not add pane-specific separator styling, since equal handle dimensions alone do not ensure equal appearance or hover behavior.

The native UI regression compares rendered divider pixels and handle dimensions across the overview, target editor, recipient editor, and workspace panes in Adwaita and Mint-X light and dark themes. Mint-X supplies its dot grip from its own GTK theme assets; keeping the native wide handle preserves the desktop’s existing grip instead of drawing a separate overview grip. It also exercises the overview handle's mouse, keyboard, and persistence behavior.
