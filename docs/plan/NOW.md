# Now

## Worker-side module (Duc)

Duc’s worker-side module queue (2026-09-12), fixture and local sinks only:

1. Accept confirmed assignments or map fixture assigning documents.
2. Plan employee schedule entries and preparation times.
3. Emit reminder and notification info packages.
4. Accept snoozes, absence, day off, and late arrival updates.
5. Signal conflicts for upstream resolution.
6. Relay done checklists and proof references.
7. Catalog new workflows with provenance and confirmation.
8. Retain scoped outcomes, estimates, and preparation notes.

Execution order and acceptance conditions live in a local, untracked handoff note; ask Duc for it.
Module contract and tests: [fads_coordination/README.md](../../fads_coordination/README.md).

## Team goal

Build one convincing road-incident loop: image, voice-note, and text intake
plus location; normalization and agent routing; workflow selection; crew
assignment; task coordination; and a resident-visible resolution estimate.

## Working assumptions

- Use a web page as the initial resident reporting channel, accepting typed
  text, image upload, and voice-note upload.
- Use fixture employees, calendars, equipment, and incidents for the demo.
- Link the existing Ambiguous workspace members to **simulated** field crew
  profiles, so OpenClaw can assign visible tasks to real workspace accounts.
- Start with fallen branches, potholes, and vehicle/debris removal as the only
  workflow types.
- A human dispatcher can override every classification, assignment, and ETA.
- Demonstrate branch removal first because it clearly needs coordinated roles.

## Decisions to make

| Decision | Suggested default | Owner | Status |
| --- | --- | --- | --- |
| Primary demo incident | Fallen branches blocking a road | Unassigned | Open |
| Image analysis | Classify a supplied demo image with confidence | Unassigned | Open |
| Voice analysis | Transcribe a supplied voice note and extract incident details | Unassigned | Open |
| Location | Map pin or typed address; fixture geocoding allowed | Unassigned | Open |
| Crew data | Fixture roster, skills, availability, equipment | Unassigned | Open |
| Assignment policy | Capability + availability first; simple distance tie-breaker | Unassigned | Open |
| Resident communication | In-app status and ETA | Unassigned | Open |

## Immediate work queue

1. Confirm the branch-blockage demo in [DEMO.md](DEMO.md).
2. Create fixture data for employees, capabilities, schedules, equipment, and
   three incidents.
3. Confirm each workspace member's simulated crew profile in [REPORTS.md](REPORTS.md).
4. Implement resident report intake: text, image, voice note, and location.
5. Normalize/transcribe incoming inputs and route the evidence bundle to the agent.
6. Encode the three predefined workflows and their required roles/tasks.
7. Implement classification → workflow selection → crew assignment.
8. Build dispatcher and resident status views, including rationale and ETA.
9. Demonstrate task progression through verification and resolution.

## Team update format

```text
Done: …
Next: …
Blocked by: …
Decision needed: …
```
