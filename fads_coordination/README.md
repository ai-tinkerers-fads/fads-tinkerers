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
python3 fads_coordination/scripts/smoke_hooks.py
```

Open [the local workboard](http://127.0.0.1:8787). `--port` and `--db` select an
isolated demo. The clock advances only through the controls; SQLite state
persists in `.fads/demo.sqlite`. All people, locations, work, and delivery are
fixtures. Verification logs belong in the ignored repository `artifacts/`.
Fixture success is not live-service proof.

The product is the worker-side module. `api.py` exposes `Hooks` and an optional
loopback HTTP handler; `core.py` owns deterministic planning and persistence.
A host supplies authenticated workspace/caller context, database, and clock.
The optional `demo.py` mounts `/`, `/demo/state`, `/demo/action`, and
`POST /demo/reset`; these are not required for hooks integration. Other owned
parts live beside them: `web/`, `fixtures/`, `tests/`, and `scripts/`.

## Assignment and reminder behavior

Use [branch-removal.json](fixtures/branch-removal.json) for the unchanged package
shape. Timestamps require offsets and the incident declares an IANA time zone.
The caller supplies an approved task graph, confirmed employees, qualifications,
equipment access, and usable work windows. The module checks those constraints
and sequences dependencies; upstream owns cross-incident capacity and actual
equipment reservations. It does not resolve conflicts or generate procedures.

Preparing does not imply permission to start. Ready reminders require completed
prerequisites; acknowledgement does not complete work. In-app receipts and the
outbox commit together. Due reminders recheck the current assignment and usable
work window; reassignment, completion and cancellation invalidate stale work.
There is a five-minute recipient cooldown and four-reminders-per-hour cap across
incidents. An overdue in-progress task needs an updated remaining-effort report
or completion to unblock downstream ETA. Quiet hours beyond supplied work
windows and escalation remain unconfigured and off.

The ordinary assignment hook rejects stale/reused changed revisions. Same
revision plus identical content is a no-op. Schedule updates include revision
and overrideSequence; clients apply them in outbox cursor order. Local hooks
use workspace-scoped SQLite transactions and source receipts for retries.

## Reset testing

**Reset testing** clears the fixture workspace's incidents, reminders, inbox,
outbox/delivery state, availability overrides, done records, proof references,
catalog, document receipts, outcomes, and notes. It restores the initial five
tasks, fixture clock, and first ready reminder. It preserves other workspaces,
repository files, and external systems. Reset is also available at
`POST /demo/reset` with `{"callerId":"fixture-tester"}`; it is demo-only.

Reset is atomic and creates a fresh testing epoch for reminder/package ids.
Outbox cursors keep increasing, so an existing poller sees restored entries.
The endpoint returns the full restored snapshot; the demo replaces its view.
A host that embeds reset must likewise clear its displayed test state. Use
**Start next incident with this memory** after resolution to retain learning;
use reset for a completely fresh test.

## Memory policy

Outcome evidence, numerical profiles and preparation notes remain separate.
This memory is an independent local store.

Profiles match **workspace + workflow ID/version + task ID + context**. They
use at most the latest 50 comparable completed outcomes, excluding unknown actuals and reported
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

## Workflow catalog

A previously unseen workspace/id/version is recorded once as `pending`, with
the supplied graph and first-registration provenance (`createdBy`, `createdAt`,
`sourceRef`, `howBuilt`). These identify the importing caller and registration
time, not an inferred original author. Explicit field-map imports also retain
the source digest. Confirmation records the first `confirmedBy` and timestamp
and activates the entry; repeat confirmation returns that original record.
The catalog is included in the state snapshot. Pending catalog review does not
undo already confirmed assignments: this module does not choose workflows.
Changed definitions under an existing version are rejected across incidents.
Existing demo databases backfill entries with clearly labelled migration
provenance; other hosts can replay their current package to register it.

## Phase report and verification limits

See [the per-phase report](PHASE-REPORT.md) for Done, Skipped, Tests, and Commits.
The final fixture suite has 49 passing tests; the complete HTTP walkthrough and
22 signed-webhook hook checks also pass. Browser automation could not discover
tabs and native app access was denied, so visual/click verification of the reset
button is not claimed. Its real HTTP endpoint, reset data behavior, binding and
JavaScript syntax were verified. No remote integration, file-byte upload, or
push to the Git remote was performed.
