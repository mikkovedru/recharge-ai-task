# Tray icon size in the standalone Flatpak

The standalone Flatpak and the native executable both used the direct Cinnamon XEmbed backend on the reported machine. Its Cinnamon X11 panel, with the collapsible system tray applet, assigned a 24×24-pixel slot to both. X11 captures of that slot contained identical pixels. The host launcher also preserved the Cinnamon desktop, X11 session and display in this test. A Flatpak-specific change to panel sizing or scaling could not be reproduced.

The slot was fully painted, but the blue ring occupied only an 18×18-pixel area within it. The tray now gives the logo more of the space above the yellow or green status strip. After a fresh install, an X11 capture of the rebuilt Flatpak in the same panel measured a 20×20-pixel ring and 121 blue pixels, up from 96. At 16 pixels, the ring grows from 12×11 to 14×13 pixels. The underlying 64-pixel tray image and the desktop app icon sizes stay the same. Both distributions use the same tray artwork.

The branding regression checks minimum visible ring dimensions at 16, 24 and 32 pixels and checks both status colors. The window size remains under panel control. See the [Cinnamon tray reconnection investigation](2026-11-04_cinnamon-tray-reconnection.md) for native allocation and scale handling.
