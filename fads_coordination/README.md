# Hooks contract


Every
endpoint takes and returns JSON. Every inbound call carries the employee or
caller id it acts for; the demo trusts it, a real host must authenticate it.
Every outbound item is an info package with `type`, `id`, `createdAt`,
`workspaceId`, `incidentId`, `revision`, and a typed `body`.

### Inbound (data in)

| Endpoint | Body | Effect |
| --- | --- | --- |
| `POST /hooks/assignments` | Full assignment package (existing fixture shape) | Validate, persist, plan, schedule reminders. Same revision and content is a no-op. |
| `POST /hooks/assignments/from-document` | `{source: {kind: csv or ambiguous_sheet, ref}, fieldMap}` | Map rows to a package, then same as above. Reports unmapped fields, never guesses. |
| `POST /hooks/employees/{id}/availability` | `{kind: absence, day_off, late, custom; incidentId?; window: {start, end}; reason; sourceId}` | Store an availability override. Replan. Emit `conflict` if any task becomes blocked or misses its deadline. |
| `POST /hooks/reminders/{id}/acknowledge` | `{employeeId}` | Existing acknowledge rules. |
| `POST /hooks/reminders/{id}/snooze` | `{employeeId, until}` | Existing snooze rules. Emits `conflict` if snooze passes the latest feasible start. |
| `POST /hooks/tasks/{incidentId}/{taskId}/done` | `{employeeId, checklist: [{item, done}], actualMinutes?, waitingMinutes?, scopeChanged?, note?, sourceId}` | Mark complete. Missing actuals are stored as unknown and excluded from estimate learning. Emit `completion`. |
| `POST /hooks/tasks/{incidentId}/{taskId}/proof` | `{employeeId, proof: {kind: image, file, text, link; ref; sha256?; note?}, sourceId}` | Store the reference only. Attach to the task. Included in the next `completion` package. |
| `POST /hooks/workflows/{id}/{version}/confirm` | `{confirmedBy}` | Activate a pending catalog entry. |

`sourceId` is a caller-generated idempotency key. A repeated call with the
same `sourceId` returns the original result and changes nothing.

### Outbound (data and signals out)

Two transports, both always available:

- `GET /hooks/outbox?after=<cursor>&types=reminder,conflict,completion` returns
  packages in order with a next cursor. The frontend or backend polls this.
- Optional push: if `FADS_WEBHOOK_URL` and `FADS_WEBHOOK_SECRET` are set, each
  package is POSTed with an HMAC-SHA256 signature over timestamp plus body,
  bounded retries, and per-package delivery state. Off by default.

| Package type | Body | When |
| --- | --- | --- |
| `schedule_entry` | employeeId, taskId, name, startAt, endAt, prepareAt, location, dependsOn | Each planned or replanned task. Upsert by taskId and revision. |
| `reminder` | employeeId, reminderId, kind prepare or ready, taskId, dueAt, text, acknowledgeUrl, snoozeUrl | When a reminder becomes due inside the employee's work window. |
| `conflict` | employeeId, taskId, cause (absence, snooze, no_window, overdue), affectedTasks, revision, overrideSequence, plainText | When a schedule update makes a task infeasible or moves the projected finish past the deadline. |
| `completion` | employeeId, taskId, completedAt, checklist, actualMinutes or null, waitingMinutes, proofs[], note | On done. |
| `state` | full plan snapshot | On request via `GET /hooks/state/{incidentId}`. |

Revision rule: upstream owns the package revision. Employee availability
overrides live in their own table with their own sequence and always subtract
from availability at plan time. A `conflict` carries both numbers so upstream
can send a new package that reflects the change; overrides stay in force
until they expire or are withdrawn, so a re-sent package cannot silently
re-schedule someone on their day off.

## Run and test

Python 3.11+, standard library only. From the repository root:

```sh
python3 -m fads_coordination.demo
python3 -m unittest discover -s fads_coordination/tests -v
python3 fads_coordination/scripts/smoke_coordination.py
```

# Crew preparation and feedback memory

This module implements the tail of the road-operations demo: confirmed
assignments → preparation/ready reminders → completion and actual effort →
scoped lessons and next-plan estimates. It does not implement resident intake,
OpenClaw/Ambiguous adapters, workflow generation or real dispatch.

## Run and demonstrate

From the repository root, run `python3 -m fads_coordination.demo`. Python 3.11+
and standard-library SQLite are sufficient. The server binds only to
`127.0.0.1:8787`. Use `--port` and `--db` for a separate demo instance. Data
persists in `.fads/`; use a new database path for a clean run.

1. Open the workboard. Alex receives a simulated ready reminder for securing
   the site. Acknowledge it: the task remains unfinished.
2. Delay the driver by 30 minutes. The projected clearance moves from 11:40
   to 12:10 in the fixture's time zone; old pending reminders are superseded.
3. Complete each prerequisite and log active and waiting minutes. The demo
   explicitly simulates performing the task and advances its clock. Dependent
   tasks unlock in order; the final verification resolves the incident.
4. Add a dispatcher-confirmed preparation note scoped to cutting branches.
   The note appears on that task only and does not add or alter workflow steps.
5. Load five **synthetic** historical outcomes. Cutting recommends 42 minutes
   instead of the template's 30. The active plan retains its original estimate
   until the dispatcher applies recommendations or starts a new incident.
6. Forget an outcome: future profiles recompute. Forget a note: its text is
   removed. Start the next incident after resolution to demonstrate retained
   scoped memory.

The synthetic outcome set tests the mechanism; it is not a claim of improved
real-world prediction. The source incident is a fixture, not live municipal data.

## Upstream handoff

`fads_coordination/fixtures/branch-removal.json` extends the shared contracts in
`docs/plan/INTEGRATIONS.md` without changing those contracts:

- `schemaVersion: 1`, `workspaceId`, `revision` (positive integer), `startAt`
  (offset-bearing timestamp), `timeZone` (IANA), and `context` (explicit cohort).
- `incident` with ID and location; `workflow` with ID, version and approved tasks.
- `employees` with IDs, declared skills, equipment capabilities and **usable
  work windows**. Upstream must subtract other incidents, leave, breaks and
  calendar commitments; this is not a fleet-wide capacity optimizer.
- Exactly one confirmed `assignment` for each workflow task. This module
  validates qualifications and equipment access; it does not choose assignees.
- Tasks may specify `preparationLeadMinutes` (default 15). This is notification
  lead time, not extra work duration. Include actual preparation work in the
  approved task estimate or upstream approved workflow.
- Completed assignments carry `completedAt`; a known `startedAt` is optional.
  In-progress assignments require `startedAt`; overdue work needs a reported
  `remainingMinutes` with its `remainingUpdatedAt` timestamp, or completion,
  before a downstream ETA can be forecast. Remaining effort is anchored to
  that observation, so polling cannot continually postpone an overdue task.

The caller owns the local revision sequence. Identical revision+content is
idempotent; changed content at the same revision and older revisions fail.
The provider adapter must reconcile out-of-order webhooks with current source
records before submitting a new snapshot. These local revisions are not claimed
to exist in Ambiguous. Changes to an approved workflow require a new workflow
version. A date without a time/zone remains unresolved and is rejected.

## Library and HTTP surface

`fads_coordination.core.Coordination(path)` is the integration seam. Supply
explicit workspace/incident IDs and a timezone-aware `now` for deterministic
tests. Close the instance after use. SQLite transactions serialize mutations.

| Method | Purpose |
| --- | --- |
| `put_package(package, now)` | Validate, persist and forecast a confirmed assignment snapshot. |
| `state(workspace, incident, now)` | Read plan, reminder state, simulated inbox and feedback evidence. |
| `tick(workspace, incident, now)` | Recheck current local assignments and deliver eligible in-app reminders. |
| `acknowledge(...)`, `snooze(...)` | Validate recipient and reminder lifecycle. Snooze only pending reminders, before planned start. |
| `complete(...)` | Require completed prerequisites and current revision; record supplied active/waiting minutes and original prediction. |
| `cancel(...)`, `replan(...)` | Cancel pending action or explicitly apply current estimate recommendations with revision checks. |
| `remember(...)`, `lessons(...)` | Write confirmed, scoped preparation notes and retrieve applicable notes. |
| `record_outcome(...)`, `estimate(...)` | Record independent actuals and derive task-type estimates. |
| `forget_lesson(...)`, `forget_outcome(...)` | Remove content/contributions and suppress replay of the same source. |

The loopback demo exposes `GET /health`, `GET /demo/state`,
`POST /hooks/assignments` (the complete JSON fixture shape), and `POST /demo/action`.
Actions are `advance`, `acknowledge`, `snooze`, `complete`, `replan`, `cancel`,
`delay_driver`, `remember`, `forget_lesson`, `forget_outcome`, `seed_history`,
and `next_incident`. `complete`, `replan`, `cancel`, and `delay_driver` require
the current `revision`. Requests use JSON; malformed inputs return 400 and
stale revisions return 409. `fads_coordination/scripts/smoke_coordination.py` has executable
examples. This server is a local demonstration, not an authenticated multi-user
API. A production host must bind trusted identities to workspace and recipient
IDs rather than trusting caller-supplied IDs.

## Reminder guarantees and boundaries

- Preparation reminders may precede a dependency's completion; their content
  explicitly says to wait. Ready reminders require completed prerequisites.
- Notifications occur inside the recipient's supplied work windows. If no
  contiguous window fits, the task and dependent ETA are visibly blocked.
- Within one incident, the forecast prevents simultaneous tasks for the same
  employee. Equipment capabilities are checked, but shared physical equipment
  reservations and multi-incident scheduling belong upstream.
- Each task/revision has at most one preparation and one ready reminder. If
  ready covers preparation, the latter is superseded. A five-minute recipient
  cooldown and four-notifications-per-hour cap apply across revisions.
- Acknowledgement is not completion. Updates/cancellation invalidate pending
  and unacknowledged old reminders; historical acknowledged receipts remain.
- SQLite atomically commits the simulated inbox row and reminder receipt, so
  replay or restart cannot duplicate that local notification. This is not an
  exactly-once guarantee for a remote channel. A future delivery adapter needs
  accepted/confirmed/unknown outcomes and channel-specific reconciliation.
- The demo clock is persisted and moves only through explicit controls.
  A small server loop polls due jobs; service integrations can call `tick` with
  a real clock. No Slack, WhatsApp, calendar or resident messages are sent.

## Memory policy

Outcome evidence, numerical profiles and preparation notes remain separate.
No OpenClaw memory or model calls are involved, so this slice can be evaluated
independently from another team's memory implementation.

Profiles match **workspace + workflow ID/version + task ID + context**. They
use at most the latest 50 comparable completed outcomes, excluding reported
scope changes. Time waiting is not active effort. Actuals are manually confirmed
or must come from an upstream effort source, never inferred from elapsed time.
Rework with changed scope should be marked excluded; richer cause modeling is
not implemented.

Below five samples, use the approved template estimate. At five or more, use
the median actual/template ratio with five baseline-equivalent observations as
a conservative prior: `factor = 1 + (median_ratio - 1) * n / (n + 5)`.
The estimate is rounded up, with a minimum of one minute. Show sample count,
observed spread and up to ten evidence IDs; the spread is not a confidence
interval. Forecast evidence is frozen per plan revision. Later completion
does not silently adopt new estimates for other pending tasks.

Notes require explicit dispatcher confirmation, a source ID, topic, task scope,
and evidence. They are displayed as information only, never executable
instructions or generated workflow steps. Reusing a topic updates one canonical
note and its version; replayed evidence does not create another note. At most
five active notes per scope are admitted. Temporary notes expire by timestamp.
Exact duplicate text under another topic is rejected; semantic deduplication is
not claimed. Workspace, workflow-version and task boundaries are applied before
retrieval, so unrelated cases cannot inherit the note.

Forgetting removes current note text or outcome evidence and stores opaque
suppression IDs to stop source replay. Profiles are derived from remaining
outcomes, so future recommendations recompute. Previously approved forecasts
remain as historical numeric decisions until explicit replanning; they are not
new evidence. Notes are not copied into notification history. This does not
erase exported files, upstream records or filesystem backups.

## Verification

Run `python3 -m unittest discover -s fads_coordination/tests -v` for the deterministic library
suite and `python3 fads_coordination/scripts/smoke_coordination.py` for real HTTP integration.
The latter uses a disposable database/server, validates a complete incident and
source forgetting, and terminates its server afterward.

The first browser walkthrough verifies acknowledgement, estimate review,
scoped notes, availability changes and completion. Local run evidence belongs
under ignored `artifacts/`, not in the shared source tree. Before real deployment,
verify upstream identity/authorization, webhook ordering, model isolation,
notification consent and the chosen provider's delivery contracts.

## Phase 1 minimization audit

Ponytail was not installed: no local copy or rule files were found, and the
no-external-service-calls constraint prohibits downloading its repository or
installing from its marketplace. A **manual minimization pass** was used.
It removed a temporary outcome-values list and used a single batch statement
for settings writes. Validation, idempotency, transactions, and revision checks
are retained. At the Phase 1 commit, core.py fell from 592 to 591 lines and
demo.py from 232 to 231; all existing behavior tests passed. Later phases use
small standard-library functions and review for unnecessary abstractions.

## Local transport details

Assignment writes include `callerId` alongside the existing package fields;
other administrative writes use `callerId` or the named `confirmedBy` field.
Employee hooks carry `employeeId` matching the path/assignment. GET hooks use
`?callerId=fixture-reader`. Workspace is bound by the host (the demo uses its
fixture workspace); it is not selected by an untrusted URL. A real host must
authenticate these identities. Routes outside `/hooks/` are optional `/demo/`
controls; the old `/api/` routes are removed.

Webhook push is disabled unless both environment variables are set. For this
fixture-only implementation, only `http://127.0.0.1:<port>/<path>` is accepted;
redirects are not followed. Headers are `X-FADS-Timestamp` (Unix seconds),
`X-FADS-Signature: sha256=<hex HMAC(secret, timestamp + "." + exact JSON bytes)>`,
and `Idempotency-Key` (package id). Receivers must verify signatures, freshness,
and ids. 2xx is accepted; 5xx retries at most three total attempts with 2/4-second
delays; other HTTP responses fail. Timeout, connection uncertainty, or a crash
while sending remains `unknown` and requires host reconciliation, never a blind
resend. Acceptance is not proof of downstream processing. Delivery state lives
in `webhook_deliveries`; polling is always available independently of push.

## Availability and conflict semantics

Employee updates carry `employeeId` matching the path and a unique `sourceId`.
`day_off`/`absence` remove the calendar day containing `window.start` in the
incident's IANA zone (including 23/25-hour days). For `late`, `window.start`
is the new arrival time; time from midnight until arrival is unavailable.
`custom` subtracts the exact start/end interval. End must follow start in the
request. Overrides expire at the end of the removed interval. They do not
increment the upstream revision, and survive replacement assignment packages.
Unscoped overrides affect all this employee's known incidents; day-based
updates need an incident scope if time zones differ. Withdrawals are reserved
for a future host interface; this slice exposes expiry only.

`conflictToleranceMinutes` on the assignment package defaults to **0**, an
explicit fixture default awaiting team policy. A newly blocked task, a finish
moving later by more than this tolerance, or a newly missed incident
`deadlineAt` emits one conflict per affected incident. It names the primary
employee/task and downstream affected tasks; it does not resolve anything.
A 20-minute late arrival may use existing slack and produce no conflict.
Schedule upserts include `overrideSequence`; consumers order same-revision
updates by outbox cursor. Snoozes beyond feasible work windows persist as
constraints and signal a conflict, instead of silently undoing the snooze.

## Completion and evidence

Done requires a nonempty checklist of `{item, done: true}` records and the
assigned `employeeId`. `actualMinutes` omitted or null stays SQL/JSON null and
is excluded from estimate samples; zero is accepted only when explicitly
supplied. Waiting minutes default to zero and do not train active estimates.
Local checklist completion is an overlay, so it does not increment or rewrite
the upstream assignment revision, and replaying a snapshot cannot reopen work.
The legacy library/demo replan and cancellation helpers represent new simulated
upstream revisions; employee hooks never use them.

Proof hooks store only the provided reference, optional checksum text, and note.
No URL is fetched, no path opened, and no checksum or content is analyzed.
Post proof before done to include it in the completion envelope. Later proof
references are visible in the state snapshot; already emitted envelopes remain
immutable. File-byte upload is off and has no endpoint. Source receipts are
transactional with the write and outbox event, preventing duplicates on replay.
The UI shows `actual unknown` and allows leaving active minutes blank.

## Fixture document mapping

`POST /hooks/assignments/from-document` takes `callerId`, `source`, and
`fieldMap`. Use `source: {"kind":"csv","ref":"assignments.csv"}` and the
object in [field-map.json](fixtures/field-map.json). The CSV is an illustrative
fixture, not a team-supplied assigning document. Every column choice lives in
that map. Sections are `package` (dot paths), `tasks`, `employees`, and
`assignments`; specs declare a column and text/integer/number/json conversion.
Repeated employee and task rows must agree. Missing required mappings name
the package field; missing mapped columns name the exact column. Nothing is
inferred from column names. Optional metadata columns must opt in explicitly.

Only files inside this module's fixture directory can be read (256 KiB,
100-row limits). `kind: ambiguous_sheet` reads `sheet-response.json`, a saved
`{rows: [...]}` fixture, through the same map. The live sheet endpoint is
**not called or verified**, and its actual response envelope may need mapping.

A full SHA-256 of normalized mapped rows plus source identity is returned as
`documentRevision`. The package revision uses its first 52 bits (exact in JSON
numbers); full hashes detect collisions. These identities have no numeric time
order: the trusted document adapter applies changed snapshots transactionally,
while the ordinary assignment hook retains increasing-revision checks. Replaying
the current hash is a no-op; replaying an older imported hash is rejected.
Consumers order changes by outbox cursor. Only tasks whose assignments or
schedule actually changed have reminders superseded; unchanged reminder IDs
and acknowledgement state carry forward to the new revision.
