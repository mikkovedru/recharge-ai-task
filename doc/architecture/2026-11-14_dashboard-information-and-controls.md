# Dashboard information and control review

## Information contract

Provider information must remain visible through initial startup, quota/status polling, explicit provider checks and settings changes. Installation/version checks run independently in the background at startup; a slow CLI does not block chat discovery. Explicit provider checks replace older results, and ordinary inventory refreshes retain details rather than clearing them. A missing executable or failed version probe has an explanation instead of silently removing the field. Each command is bounded, and provider version checks run concurrently.

The previous startup path used ordinary chat discovery without version probing. Only the explicit provider-check inventory populated installation details. Tests supplied those details directly, so they verified rendering while missing the startup data-flow gap. The startup regression now runs fixture CLI executables through the production metadata reader and checks the visible fields again after ordinary refresh.

The provider identity line contains name, plan where supported, executable path and version. The two detail columns group information as follows:

| Area | Information |
| --- | --- |
| Identity, full width | Provider, plan, executable and version; terminal integrations identify wrapped-terminal support rather than inventing an account plan. |
| Alerts, full width | Provider errors, warnings and installation problems. |
| Quota and checks, left | Availability and observation freshness; every usage window with reset/countdown; usable credits; next check and reason with refresh interval. |
| Recovery and actions, right | Confirmed delivery or forecast with countdown; pending actions; selected recipients and remaining allowance; used and unconfirmed counts. |
| Wrapped terminals | Live session state/countdown/counts beside the launch command and integration limits; no invented shared-account quota. |

The detail sections use two columns when their widths fit, and stack as complete sections when they cannot. Identity and alerts retain the entire tab width. All text wraps and remains selectable; long executable paths must not be ellipsized or hidden in a tooltip. A zero pending-action line is omitted when the schedule already says no send is scheduled; actual pending counts and historical usage remain visible.

Green denotes available/ready or enabled states, yellow denotes warnings/waiting/uncertainty, and red denotes failures or exhausted windows. Installed but inactive tabs remain neutral; absent tabs retain shaded italic captions without a suffix. Text, numeric values and notice icons carry the meaning independently of color. Color values come from the existing theme-aware status palette.

## Shared controls

Recipient membership is independent of enabled actions. The main model stores membership separately from the Goal/Message checkboxes; both its pinned sort group and separator use that field. A passive recipient remains pinned and saved, with an explicit Passive label and italic title in both lists. Task and Goal status keep their actual provider values and colors. The transfer arrow acts on the selected main-list stable identity: add with both actions off, or remove through the existing removal path while retaining preferences and counts. The arrow and Send now form one toolbar group so they cannot wrap apart.

The three recipient action buttons have wrapping captions and a shared measured height, including when the toolbar itself wraps. GTK's actual allocated widths and theme insets determine caption height. Whole buttons move to another row only after the compact captions cannot fit, and widening must shrink both buttons and their row again. Hard-coded height allowances and a fixed wide caption request must not determine the row break.

Resizable panes use the existing native themed divider through the common factory. The [shared-divider contract and actual-theme rendering checks](2026-11-14_shared-pane-dividers.md) document that invariant. New panes inherit their peers' grip pattern, dimensions and hover/focus behavior; an overview-only drawing is not a valid substitute.

## Required visual review gate

Before matching or reorganizing existing UI, capture the actual reference under the user's theme and inventory the visible features and information. Identify grip/icon pattern, thickness, spacing, normal/hover/focus appearance and the fields that must survive. Compare the implementation against that reference in rendered output and by visual inspection, plus real mouse/keyboard and window-resize checks. Matching dimensions or a successful fixture with invented metadata does not establish visual or information fidelity.

The relevant regressions check installation details from startup rather than only manually supplied page strings, preserve all nonredundant provider fields, verify both columns and the narrow fallback, exercise semantic status colors, compare every native divider against existing references, deliberately remove a grip to prove the comparison detects that mistake, and resize action buttons through both wrapping directions. Test the actual Mint-X theme as well as light/dark Adwaita; those themes are not interchangeable references.
