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

`fixtures/branch-removal.json` extends the shared contracts in
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

The loopback demo exposes `GET /health`, `GET /api/state`,
`POST /api/package` (the complete JSON fixture shape), and `POST /api/action`.
Actions are `advance`, `acknowledge`, `snooze`, `complete`, `replan`, `cancel`,
`delay_driver`, `remember`, `forget_lesson`, `forget_outcome`, `seed_history`,
and `next_incident`. `complete`, `replan`, `cancel`, and `delay_driver` require
the current `revision`. Requests use JSON; malformed inputs return 400 and
stale revisions return 409. `scripts/smoke_coordination.py` has executable
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

Run `python3 -m unittest discover -s tests -v` for the deterministic library
suite and `python3 scripts/smoke_coordination.py` for real HTTP integration.
The latter uses a disposable database/server, validates a complete incident and
source forgetting, and terminates its server afterward.

The first browser walkthrough verifies acknowledgement, estimate review,
scoped notes, availability changes and completion. Local run evidence belongs
under ignored `artifacts/`, not in the shared source tree. Before real deployment,
verify upstream identity/authorization, webhook ordering, model isolation,
notification consent and the chosen provider's delivery contracts.
