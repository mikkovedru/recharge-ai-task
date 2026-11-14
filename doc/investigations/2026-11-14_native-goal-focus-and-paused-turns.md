# Native Goal focus, control discovery and paused turns

## Report and confirmed observations

A manual Goal attempt on 2026-11-14 failed after one minute with `Another application has focus; no Goal action sent`. This exception comes from the native helper's foreground-process check before Resume; it does not inspect Goal or task status. The historical log does not identify which application gained focus or why. The helper acquired Codex before URI dispatch but did not acquire it again after the handler returned.

The user staged a paused Goal with a still-running turn. Read-only checks confirmed native and desktop Goal status `paused` with task status `active`. Later checks found the Goal still paused and the task idle, consistent with the user's report that work continued briefly before stopping. These observations establish that the states can temporarily differ; they do not establish a fixed stop delay or a general guarantee about Codex pause semantics.

Manual recovery already permits paused Goals during active turns. Automatic recovery protects a pause. The focus exception was a separate navigation guard, so it is not evidence that the paused/active combination was rejected by recovery policy. Tests now also cover an active turn becoming idle while navigation is in progress.

## Control discovery and focus handling

The helper now acquires the verified Codex foreground again immediately after URI dispatch, before reading the selected chat or operating menus. URI dispatch completion does not establish foreground ownership. Later focus loss still aborts; it is not automatically replayed or repeatedly overridden. Navigation errors include the exact chat ID, elapsed navigation time, verified desktop PID and a foreground/retry instruction. Post-click failures remain uncertain because Resume may already have succeeded.

Repeated whole-frame accessibility walks fetched the conversation while searching for sidebar buttons and menus. The scoped adapter now uses the verified application's [AT-SPI Collection.GetMatches](https://raw.githubusercontent.com/GNOME/at-spi2-core/main/xml/Collection.xml) interface to select roles inside the exact accessible subtree. Returned references must still belong to the pinned application. Unsupported Collection methods use the existing tree-walk path; transport errors and timeouts do not silently retry. No global desktop traversal or Cache.GetItems request was introduced.

In three interleaved read-only runs per implementation against the same already-selected, paused/idle chat, tree-walk navigation took 4.091, 5.205 and 4.548 seconds. Direct control queries took 1.162, 1.149 and 1.137 seconds. Median navigation fell from 4.548 s to 1.149 s (x3.96). These measurements isolate control lookup: both modes used the same foreground-acquisition behavior and preserved the clipboard. They are local observations on Codex desktop build 26.1111.21308, not a cross-machine latency guarantee. A representative steady run replaced roughly 4,600 GetChildren/GetRole calls with four GetChildren, twelve GetRole and thirteen or fourteen Collection calls.

An earlier cold navigation took 12.925 s and made more than 15,000 tree-walk calls. That run began in a different navigation state and must not be attributed solely to the control-query change. Read-only inspection also briefly saw registered frames with no children before their controls appeared. The cause of that transient empty tree remains unestablished.

## Live verification and remaining limits

One Goal-only manual recovery was performed on the user's named webcam-support chat after its delayed stop had finished. The initial state was Goal paused / task idle. Recovery succeeded in 4.287 s; native Goal and desktop Goal both became active and the desktop task became active. Goal identity, objective, creation time and token budget stayed unchanged; usage accounting did not decrease. Prompt-send and steer entry points were forbidden during the verification. No message was added.

A live paused/active state had been observed earlier, but that turn was already idle by activation time. Active/active and active-to-idle recovery transitions therefore have regression coverage rather than a live re-staging test. No additional pause was injected into the user's resumed work. A future genuine focus loss can still stop navigation safely and now reports its stage. The historical cause of the original focus transfer remains unknown.

See the [earlier exact-chat navigation investigation](2026-11-04_exact-chat-goal-navigation.md) for canonical-ID, clipboard and unique-button constraints, and the [Cinnamon investigation](2026-11-05_cinnamon-goal-accessibility.md) for why application scoping and avoidance of global accessibility caches remain necessary.
