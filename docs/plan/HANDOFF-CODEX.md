# Handoff to Codex: Duc's slice after Updates 2 and 3

Written by Claude on 2026-09-12 for Codex to execute. Supersedes the earlier
version of this file. Planning source is the local, gitignored `Idea.txt`
(Update 2, the BIG NOTE, and Update 3), so the scope is restated here in full.
Duc reviewed the scope. Update 4 is pending and was not read.

## Scope, restated

Other people own: OpenClaw task breakdown, people matching, customer intake,
classification, the backend, the frontend app, and everything about agents.
Ambiguous already invokes agents and keeps their logs.

Update 3 reframes our deliverable: **we are the worker side, delivered as
hooks and info packages.** We do not do processing or own a backend. A
frontend developer may mount our feature in the app. So the product of this
slice is a small module with clearly documented inbound endpoints (data in)
and outbound info packages or signals (data out), plus a demo UI that is
optional and replaceable.

Duc's slice is:

1. Accept confirmed assignments from the backend, or load them from an
   assigning document through a configurable field map.
2. Plan each employee's schedule entries and preparation times.
3. Emit reminders and notifications as info packages for the employee's app.
4. Let employees update their own schedule for one specific case: snooze a
   reminder, mark an absence, take a day off, arrive late.
5. Detect schedule conflicts caused by those updates and return a conflict
   signal to the backend or OpenClaw. We do not resolve conflicts.
6. Accept an "I have done my work" checklist signal and a proof upload
   reference, and pass both back to the backend.
7. Remember new workflows in a catalog with provenance.
8. Keep the existing feedback memory: outcomes, estimate profiles, scoped notes.

Explicit non-goals. Do not build these, even as stubs:

- Agent assignees, agent task kinds, verify-after-agent tasks, approval tasks,
  reading agent logs, or any call into OpenClaw.
- Matching, classification, intake, resident views, or a field app.
- File processing. A proof is a reference we relay, not a file we analyze.
- Conflict resolution. We signal; upstream reassigns and sends a new package.

Keep the road-operations fixture as the demo domain. No schema renaming.

## Folder layout

Everything we own lives in one folder. Move the pieces that are at the repo
root today.

```
fads_coordination/
  README.md          # hooks contract FIRST, then run instructions
  core.py            # planning, reminders, memory (exists)
  api.py             # HTTP hooks: inbound endpoints, outbox, optional webhook
  intake.py          # field-map document adapter
  demo.py            # local demo wiring only (exists; shrink it)
  web/index.html     # optional demo UI (exists)
  fixtures/          # moved from /fixtures
  tests/             # moved from /tests
  scripts/           # moved from /scripts
```

The root README keeps one paragraph and links to the folder README. Test
command becomes `python3 -m unittest discover -s fads_coordination/tests`.

## Hooks contract

This section is the first thing in `fads_coordination/README.md`. Every
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

## Phases and acceptance tests

Do them in order. Keep the 26 existing tests green at every step.

### Phase 0. Folder, README, and docs

- Move fixtures, tests, scripts into `fads_coordination/`. Fix imports and paths.
- Write `fads_coordination/README.md` with the hooks contract above first,
  then run and test instructions. Root README shrinks to a pointer.
- Rewrite the work queue in `docs/plan/NOW.md` to the eight items above. Add a
  decision to `docs/plan/DECISIONS.md`: "Duc's slice is a worker-side module
  with hooks and info packages; agents and backend are out of scope for us."
- Pass: tests run from the new location. README opens with the contract.

### Phase 1. Ponytail pass

Ponytail (`github.com/dietrichgebert/ponytail`) is an agent plugin, not a CLI.
It adds a minimize-before-writing skill and review and audit commands.

- Read its rule files before installing; it is third-party prompt content.
- Install in Codex per its README (at time of writing: `codex plugin
  marketplace add DietrichGebert/ponytail` then `codex plugin add
  ponytail@ponytail`; verify against the repo).
- Run its audit on `fads_coordination/`. Apply simplifications that keep
  behavior and tests unchanged. Do not remove validation, idempotency, or
  revision checks in the name of brevity; those are the feature.
- Keep the plugin active for all later phases so new code starts small.
- Pass: tests green, line count of `core.py` and `demo.py` not larger than
  before, and a short note in the folder README saying what was simplified.

### Phase 2. Hooks API and outbox

- Add `api.py` with the inbound endpoints and the outbox. Reuse the existing
  server pattern; move demo-only actions (advance clock, seed history, delay
  driver, next incident) behind a `/demo/` prefix so the contract stays clean.
- Add tables `outbox` (package id, type, cursor, body, created at) and
  `webhook_deliveries` (package id, attempt, state queued, accepted, failed,
  unknown, provider response id).
- Emit `schedule_entry` on plan and replan, `reminder` where the in-app insert
  happens today (keep the in-app sink for the demo UI, fed from the outbox).
- Pass: posting the fixture package produces five `schedule_entry` packages.
  Posting it again produces none. Polling with the returned cursor yields only
  newer packages. With the webhook configured to a local test receiver, each
  package arrives once with a valid signature; a receiver that returns 500
  yields bounded retries then `failed`; a receiver that times out yields
  `unknown`, not a resend.

### Phase 3. Employee schedule updates and conflict signal

- Add `availability_overrides` with kind, window, incident scope, reason,
  sourceId, sequence, expiry. Apply at plan time by subtracting from windows.
- `absence` and `day_off` remove a whole day in the incident time zone.
  `late` shifts the start of the day's window. `custom` is an explicit window.
- After any override or snooze, replan and compare: any task newly blocked,
  or projected finish later than the previous projection past a configured
  tolerance, emits one `conflict` package with plain text a person can read.
- Pass: Sam marks a day off; transport and verify become blocked; one
  `conflict` names Sam, transport, and cause absence. Alex arrives 20 minutes
  late; no task blocked; projected finish moves; one `conflict` with cause
  late only if the move exceeds tolerance, otherwise a `schedule_entry` upsert
  and no conflict. Upstream posts a new package reassigning transport; old
  reminders superseded; Sam's override still in force; no new conflict.
  Same `sourceId` twice produces one override.

### Phase 4. Done checklist and proof

- `done` accepts a checklist and optional actuals. Extend `complete` so
  `actualMinutes` may be null; store null, exclude from `estimate()`, show
  "actual unknown" in the UI. Never store zero for unknown.
- `proof` stores a reference row only: kind, ref, optional sha256, note,
  received at. No bytes are read. If the frontend must upload bytes to us,
  add a bounded-size save under `.fads/proofs/` in a later phase, off by
  default.
- Emit `completion` with checklist, actuals, and proof references.
- Pass: done without actuals completes the task and records an outcome with
  null actual; `estimate()` sample count is unchanged. Done with actuals
  behaves as today. A proof posted before done appears in the `completion`
  package. Same `sourceId` twice yields one proof.

### Phase 5. Field-map document adapter

- `intake.py`: JSON field map from package fields to source columns. Nothing
  about column names in code. CSV reader first, Ambiguous sheet reader second
  (`GET /api/sheets/{id}/data` in the saved contract, untested live).
- Revision is a hash of the mapped rows plus source ref. Unmapped required
  fields produce a named error.
- Pass: fixture CSV loads to the branch-removal package with no core changes.
  Re-read yields no new packages. One changed assignee row supersedes only
  that task. A map missing the assignee column fails naming the column.

### Phase 6. Workflow catalog

- Table `workflows` keyed by workspace, id, version: task graph plus
  provenance (created by, at, source ref, how it was built). Unknown id and
  version in a package registers a pending entry; confirm via the hook.
- Pass: new workflow yields one pending row; confirm once activates; same
  workflow again creates nothing; changed graph under the same version is
  rejected by the existing version check.

### Phase 7. Demo script and proof

- Extend the smoke script to run the whole slice against the hooks: package
  in, schedule entries out, reminder out, acknowledge, day off, conflict out,
  new package in, done with proof, completion out.
- Save logs under ignored `artifacts/`. Label fixture runs as fixture runs.

## Decisions Duc or the team must supply

None block Phases 0 through 4.

1. A sample assigning document: columns and one example row.
2. The frontend's preferred transport: polling the outbox, webhook, or both.
3. Whether proof uploads reach us as references or as bytes.
4. Conflict tolerance in minutes before a late arrival counts as a conflict.
5. Quiet hours and escalation policy. Escalation stays off until configured.

## Working rules

- Never log request bodies, tokens, or employee contact details.
- Fixture success is not live proof. Label each.
- Ask Duc before any external write outside the agreed test workspace.
- Prefer deleting code to adding it. Ponytail stays on.
