# Cinnamon tray reconnection

A tray process can serve its controller while its icon is missing. Launching a second copy must repair the existing process's tray surface rather than infer visibility from a responsive control socket. The dashboard, menu, watch worker and CLI jobs are independent of that replaceable surface.

## Manager disappearance and callback survival

GTK's [plug implementation](https://raw.githubusercontent.com/GNOME/gtk/gtk-3-24/gtk/gtkplug.c) sends delete-event when an embedding socket disappears and destroys the plug if the event is unhandled. Keep the plug on that event; recreate it if destroyed. When unembedded, request docking again at two-second intervals, including when the manager owner has not changed.

A missing manager is a normal part of Cinnamon replacement. Xlib's `get_selection_owner` returns integer `X.NONE` (0), not a Window with `id=0`. Dereferencing `.id` on that result raises AttributeError. An exception from a GLib timeout removes the callback, so the surviving application can remain invisible indefinitely. Handle the real missing-owner value explicitly. Keep polling after transient X11/window errors and avoid repeating identical error messages on every tick. Stale draw callbacks must not interfere with a replacement surface.

A same-process GTK socket test does not reproduce this manager-process gap. `test_tray_manager_restart.py` uses a separate XEmbed manager and client on a private Xephyr server. It kills the manager, leaves it absent for longer than a refresh interval, and starts a replacement twice. The original implementation loses its timer during the first gap. Regression checks retain the same client, menu and simulated watch thread throughout recovery, without restarting the user's Cinnamon session or addressing real chats.

## Relaunch repair

`recharge-ai-task --tray` requests `restore-tray` from an existing controller. Normal and Settings launches also request repair before opening their views. The GTK backend replaces only its plug and restarts the refresh source, including when GLib already removed the old source. XApp refreshes its visibility and icon. No watch worker, CLI job, target, allowance or prompt is reset. A status poll remains read-only with respect to the tray surface.

## Physical pixel allocation

XEmbed geometry is measured in physical pixels. GDK reports logical coordinates, and GTK's drawing context already applies the [widget scale factor](https://docs.gtk.org/gtk3/method.Widget.get_scale_factor.html). Read the native allocation, generate artwork at that resolution, and compensate for the context scale exactly once while painting. The drawing area expands to its host allocation. A temporary unavailable window is retried rather than ending the refresh source. The native regression verifies painted corners, logo and background over the full 24-pixel surface at 1× and 48-pixel surface at 2×, after manager replacement and both relaunch paths.

On the reported system, an undocked surviving plug had returned to its 16-pixel minimum; a freshly embedded probe received 24 pixels from Cinnamon. The probe's GDK and X dimensions agreed at 1×. That observation does not establish the exact cause of every previously perceived size change. The application follows the space allocated by the panel; it does not override panel sizing or collapse preferences.

## File-manager icons are separate

Nemo's [custom-icon handling](https://github.com/linuxmint/nemo/blob/master/libnemo-private/nemo-file.c) reads per-file custom icon metadata before its generic file-type icon. Executable metadata points to persistent artwork, never PyInstaller's temporary extraction directory. See [branding and desktop integration](../../docs/branding.md#linux-file-manager-and-menu-icons) for the installation command and portability limits.
