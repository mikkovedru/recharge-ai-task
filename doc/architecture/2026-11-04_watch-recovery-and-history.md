# Watch recovery and delivery history

The watch worker owns send timing. The dashboard displays its observations,
deadlines and remaining allowances rather than deriving a schedule from its
separate quota refresh. Polling the GUI cannot arm or complete a recovery.

## Recoveries that occur between polls

A quota reset can happen between a near-limit sample and the next check, so
requiring an observed 100% sample misses real recoveries. In addition to explicit
backend blocks, the worker recognizes recovery after a sample of at least 95%
when usage falls below 95% and either the known reset rolls over after its
deadline or usage drops by at least five percentage points. Small corrections
remain insufficient evidence. A completed reset/refill ID needs two consecutive
near-limit samples before another refill using that ID can arm a cycle; one
stale frame cannot replay the previous cycle.

Included-window forecasts are conditional. Usable quota must still be confirmed,
including secondary limits and spend controls, before grace starts. Grace uses
observed recovery time and survives settings restarts. The UI distinguishes a
forecast, a confirmed deadline, retry timing and an overdue worker observation.
Allowance counts are upper bounds because live goal/task rules are checked at
send time.

## Verified actions and checkpoints

Automatic retries remember completed actions per recipient. If Goal activation
was verified and the prompt was rejected, the next retry sends only the prompt.
Repeating the original pair would encounter the consumed Goal allowance and
incorrectly withhold the prompt. An accepted but unverified Goal is uncertain;
it never becomes a prompt-only retry. An attempt that fails before the native
control is invoked remains a definite, retryable failure. The attempt marker
alone cannot establish acceptance. Definite failures release the allowance;
unconfirmed accepted operations retain an uncertain allowance.

Atomic JSON checkpoints in the config directory are scoped to the configured
Codex executable and selected profile paths. They preserve quota observations,
pending cycles, grace, completed actions and delivered recipients across tray
restarts. They do not turn a stopped watch on. A changed set of profile paths
uses its own checkpoint. These paths do not identify account switches inside
the same profile; quota is still checked before every delivery cycle.

Remote acceptance and the local checkpoint cannot be committed atomically.
The worker checkpoints an in-flight recipient before calling Codex. If the
process dies in that interval, reopening records an uncertain outcome and
withholds automatic replay for that recipient in the current cycle. Manual
inspection and an explicit send remain possible. Allowance reservations provide
additional protection for uncertain individual actions.

## Delivery history

`activity.py` stores bounded events in a separate table in the existing
`delivery.sqlite`. Allowance attempts and history have different retention:
resetting counts does not erase history, and pruning history cannot restore an
allowance. Actual operations log attempting/accepted events. Native activation
adds a separate verified event before any selected prompt. Skipped actions and
failed or uncertain results include the reason. Prompt events contain the actual
message after applying the recipient override. Events store the Codex project
name alongside the chat title, including failures and skipped actions. The history
schema is extended in place; older records without project metadata are preserved
as unknown rather than inferred from nonunique titles.

All GUI sends and explicit per-recipient automatic sends use this path. The
GUI reads events directly from SQLite every two seconds, independently of tray
IPC, and remembers an event cursor to avoid duplicate display. Reopening reads
the latest 200 events with their original timestamps. The database retains up
to 1,000 events. The view also bounds its own text buffer. Logging failure does
not replace the actual delivery result; history read errors are shown in the GUI.
