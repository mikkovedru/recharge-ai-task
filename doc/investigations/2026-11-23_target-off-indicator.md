# Off indication in Targets & actions

The named off control in the editor was red before commit `c096da2`. That change deliberately gave selected Off buttons and the paused-message save indicator neutral styling while introducing the read-only saved-settings preview. These controls are separate from the status of a row in the target list.

The row badge was introduced as a neutral **Passive** marker in `694ceb6`. Commit `dc6e953` made it more compact and gave the selected row's badge the generic selection foreground. It also introduced the red status stripe and the explicit explanation that both actions are off. History did not show a red fill on that row badge. The new **Off** badge makes the disabled state red in the row, including when the row is selected. It keeps a contrasting white label and the same compact padding.

The selected **Off** buttons under **Reactivate goals** and **Send messages** share a fixed red fill with the row badge. The earlier editor fix was present in a separate release patch while the committed GTK test still expected neutral styling. The fixed colors now live in the panel's static CSS and the theme-dependent allowance styling excludes Off. The paused custom-message indicator remains neutral.

The native GTK tests verify both editor buttons after switching themes, the selected Off state in read-only previews, and the row badge with and without row selection. These tests run in the existing Linux desktop CI job.
