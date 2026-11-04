# GTK table sizing and interactive status help

## Wrapped button captions

On GTK 3 in Cinnamon, the built-in button/alignment hierarchy measured a wrapped
caption using its minimum width even when the allocated width could show one
line. Copy and Open reserved 67 pixels of height, versus 29 for a plain Refresh
button. The shared horizontal box then stretched Refresh to the same height.
Setting vertical alignment alone only fixes Refresh.

`WrappingButton` requests height for the available width. It reuses native
measurements for theme padding, borders and icons, then asks the caption for its
height at the remaining text width. One-line buttons measured 29 pixels in the
same environment; captions still gain lines when space is limited. Centered
vertical alignment prevents a shorter neighboring button from stretching.

## Columns

Unbounded explicit header wrapping made a 36-pixel Availability column request a
180-pixel header. Headers now have at most two lines with ellipsis and full
caption tooltips. Available label width subtracts native header button geometry,
including information icons and sort indicators, rather than assuming fixed
padding. Cell text remains fully wrapped.

Width notifications arrive during GTK allocation. Applying wrapping and queuing
more column resizes synchronously repeats layout work inside that pass.
`TableLayout` groups geometry updates in an idle callback and then requests a
complete resize/redraw. Narrowing and widening must settle with no pending
geometry work, correct row heights, and unchanged recipient selection. Column
width and order persistence is separate from drawing geometry.

Project moves to the first position for fresh layouts and older saved layouts.
A saved leading-column policy marks that migration, so a later deliberate user
reorder remains effective.

## Hover popovers

A leave event can mean entering a child widget, rather than leaving the popup.
The former 250ms timer also closed the popup without checking the pointer's
current position. Timers scheduled by overlapping header and child crossings
could therefore dismiss help while the user tried to expand an explanation.

Ignore inferior-child crossings and check the current pointer against both
anchor and popup rectangles before dismissing hover-only help. A short travel
delay bridges the space between them. Clicking the info icon, expanding an
explanation or scrolling retains the popup until Close/Escape. Hover opening
remains nonmodal and preserves editor focus; F1 opening provides keyboard focus.

## Inherited message preview

The unchecked custom-message editor remains a readable, copyable default preview.
It is non-editable, hides its editing cursor and uses the theme's background and
foreground colors for a passive tint. The checked editor restores its native
appearance. Avoid opacity or fixed light/dark colors, which can reduce contrast
or conflict with the active GTK theme.
