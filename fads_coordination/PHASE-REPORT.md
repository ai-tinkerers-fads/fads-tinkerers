# Fixture execution report

Phases were implemented in order on `feat/preparation-reminders-memory`.
All commits are local; nothing was pushed. No external service calls were made.
The original 26 behavior tests remain included in every passing suite.

| Phase | Done | Skipped | Tests | Commits |
| --- | --- | --- | --- | --- |
| 0 | Moved fixtures/tests/scripts into the module; hooks-first README; updated work queue and boundary decision. | None. | 27 passed; relocated discovery and contract-first layout. | `2900bf5` |
| 1 | Manual minimization: outcome unpacking and batched settings writes. Core 592→591 lines; demo 232→231 at this phase. | Ponytail download/install/audit: unavailable locally and external calls prohibited. Fallback disclosed in README. | 28 passed; fallback disclosure checked. | `7e43fde` |
| 2 | JSON hooks, ordered outbox, schedule/reminder packages, in-app sink, signed local webhook delivery ledger. | External webhook destinations disabled. | 32 passed; local valid signatures and no duplicate acceptance; bounded 500 retries; timeout→unknown without resend; real HTTP regression walkthrough. | `e252717` |
| 3 | Availability subtraction with independent sequence, tolerance/deadline checks, conflict signals, persistent infeasible snoozes. | Conflict resolution; escalation and additional quiet-hour policy remain off. | 36 passed; day off, late/tolerance, reassignment, retained overrides, idempotency, snooze blocking. | `15a6fe5` |
| 4 | Checklist done, nullable actuals, proof references, completion packages, preserved upstream revision. | Proof-byte uploads and file analysis. | 38 passed plus HTTP walkthrough; unknown actual excluded from learning, proof relay and retry receipts. | `da3ed0b` |
| 5 | Explicit field map, illustrative CSV and saved sheet fixtures, hash revisions, selective reminder supersession. | Live sheet call; actual team document not supplied. | 41 passed plus HTTP walkthrough; repeat imports, changed assignee, missing mapped column, path bounds. | `e822d28` |
| 6 | Pending workflow catalog with provenance, confirmation and cross-incident version enforcement. | None within fixture scope. | 43 passed plus HTTP walkthrough; repeat confirmation and immutable versions. | `6fcc50a` |
| 7 | Full hooks smoke sequence, reset button and endpoint, atomic fixture restoration, namespace isolation, fresh testing ids and forward cursors. | Browser click verification: tab discovery failed twice; native app access was denied. HTTP reset and UI JavaScript checks passed. | 49 passed; full real HTTP fixture sequence; additional 22/22 signed-webhook hook checks; Python compilation and UI JavaScript syntax. | This report's commit (`Phase 7: verify the complete fixture hooks slice and add reset testing`). |

## Local proof

Logs (ignored, not source-controlled):

- `artifacts/phase-0-tests.log` through `artifacts/phase-7-tests.log`.
- `artifacts/phase-7-http.log`: package in → five schedule entries → reminder
  → acknowledge → day off → conflict → replacement package → proof reference
  → done with unknown actual → completion → catalog confirmation → reset.
- `artifacts/phase-7-webhook-http.log`: 22/22 checks against a disposable local
  HTTP host and HMAC receiver, including 500 and timeout delivery behavior.

These are fixture and local-sink results, not live integration proof. The demo
UI is optional; browser automation could not verify the new button visually.
Its endpoint, returned state, atomic rollback, namespace isolation and script
binding were checked without external calls.

The reset button clears the demo workspace including feedback memory and
restores the original fixture. Existing tracked source files and other workspace
rows are preserved. Forgotten proof references do not delete external files;
this module never reads those bytes in the first place.
