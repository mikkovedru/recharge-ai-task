# One-use custom messages

A recipient can arm **Send only once** while using a custom message. A confirmed message send consumes that custom message, and future sends use the current default. Definite rejection and skipped delivery leave it armed. If delivery is unconfirmed, the custom message remains consumed to avoid sending it twice. This choice applies to manual and automatic sending and survives restarts.

## Reservation and acknowledgement

Each edit or explicit rearming creates a new `custom_prompt_once` token on the recipient. `UsageLedger.reserve_prompt` claims that token and reserves its message allowance in the same SQLite transaction. Concurrent senders can reserve only one use of the custom text. Later senders use the default text, including when an old worker still holds the earlier recipient settings. Empty fallback messages are rejected before delivery.

The `custom_once` table records pending, sent, uncertain or failed outcomes. Its pending claim is updated in the same transaction as the matching allowance attempt. A pending claim from an exited process is treated as uncertain. Resetting counts preserves one-use consumption and finalizes abandoned pending claims as uncertain before removing allowance attempts. This also prevents reused attempt IDs from rearming an old custom message.

The Goal and message actions remain independent. A Goal failure does not claim the custom text by itself; the independently selected message is still attempted afterward and claims it through the normal message reservation. Only a failed or skipped message leaves the custom text available for retry. An accepted message stays consumed if a subsequent Goal-state check fails.

## Settings and concurrent edits

Workers do not rewrite the settings JSON after sending: doing so could overwrite a newer draft saved by another process. Config loading and the GUI normalize the matching consumed token to an ordinary default-message recipient. The delivery ledger is authoritative even if the JSON still contains the earlier token until the next settings save. A different token represents a newer edit and remains untouched.

The tray advertises `one_use_messages` support. The GUI refuses to arm one-use messages on an active older watch, and refuses to start an older watch with an armed one-use message. Manual delivery uses the updated local sender.

## Verification boundaries

Regression tests cover accepted, failed, skipped and uncertain sends; concurrent threads and independent processes; count resets; stale workers; rearming the same text; newer edits during sending; Goal fallback and post-message Goal failures. GUI checks cover arming, save/apply feedback and returning to the default editor. No live chat messages are required for these tests.
