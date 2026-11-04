# Delivery history and action results

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
