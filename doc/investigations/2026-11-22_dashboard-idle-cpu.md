# Dashboard idle CPU on GTK

The open dashboard could consume most of one CPU core while idle, with Desktop watch either on or off. This was reproduced on Linux with GTK 3 on a nested X11 display. The fixture loaded 200 synthetic chats and 20 selected targets with custom messages, used a 30-second quota interval and simulated an unavailable provider. Monitoring status came from a local fixture. No provider CLI or external account was needed to reproduce the dashboard work.

Two GTK callbacks kept layout active. The custom-message preview expansion change in `926e921` made the allowance resize callback rewrite its label markup on every size allocation. The write requested another allocation, which ran the callback again. The column-wrapping implementation in `8594845` queued a full table resize and redraw after every batch of width notifications. GTK can send those notifications again during allocation even when the allocated widths are unchanged. Profiling confirmed that the remaining continuous frames after the preview fix were spent measuring and painting the main tree view.

Update the allowance caption when its content or expanded state changes. Keep the allocation callback for overflow measurement. Rewrap and invalidate table geometry when the renderer's effective wrap width changes. Preserve the scroller's horizontal position between refreshes, including when selecting a row scrolls its Title column into view. Pixel checks of the leftmost row stripe must bring that column into view before sampling it.

The tray status timer also treated a missing successful quota snapshot as a reason to run another check. A provider failure could cause a new quota check on each two-second status poll. For Codex, every local quota fetch can start an app-server subprocess. Runtime polling may kick off a first check for a late-arriving inventory. Subsequent checks use the configured quota timer, the manual quota action or the watch worker's own schedule.

This fixture measures dashboard process CPU over 17 seconds per monitoring state. Timing varies with GTK theme, table size, display and provider activity. The synthetic watch status verifies that the dashboard layout loop was independent of watch state. It does not measure CPU used by a live provider or a separate tray process.

| Desktop watch | Before | Fixed | Reduction |
| --- | ---: | ---: | ---: |
| Off | 69.84% of one core | 7.06% | 9.9× |
| On | 64.59% of one core | 6.85% | 9.4× |

The pointer was outside the dashboard for both runs. The table geometry callback ran 240 times with watch off and 217 times with it on before the fix. It ran zero times during the fixed sampling windows after initial layout. The fixed dashboard typically used well under one percent in seconds between polls. Nine failed quota attempts per 17-second window became one attempt across both fixed windows when the 30-second quota timer fired.

## Follow-up profiling

After the layout feedback loops were removed, CPU still rose every two seconds when the tray status reply arrived. A GTK callback profile attributed most dashboard work on that path to rewriting target rows and readiness widgets, followed by drawing the chat table again. Stable rows were being rebuilt even when saved settings, delivery usage, target inventory and the custom-message save state matched. Quota adoption also rendered provider views before the status renderer rendered them again.

The dashboard still samples tray status and delivery usage every two seconds. Stable samples reuse target widgets and skip drawing unchanged health indicators. Status changes, allowance changes, and explicit or scheduled chat inventory refreshes still update the relevant views. Inventory refresh continues to re-evaluate paths and routing readiness even when the resulting target metadata is identical. The table's border painter uses the visible rows, including partially visible rows, and the one-second quota and recovery countdowns continue to tick.

The same 200-chat fixture measured the follow-up against `a2c111c`, which already included the fixes above. The figures cover the combined dashboard changes.

| Desktop watch | Prior fix | After follow-up | Reduction |
| --- | ---: | ---: | ---: |
| Off | 7.78% of one core | 1.78% | 4.4× |
| On | 6.82% of one core | 2.17% | 3.1× |

In the 6.6-second callback profile, three stable tray replies used 121 ms of measured Python callback time before the follow-up and 19 ms afterwards. The 15-second inventory refresh still caused a brief CPU spike in the fixture. Real provider discovery, quota subprocesses and the separate tray process were outside this measurement.
