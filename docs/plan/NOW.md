# Now

Last updated: 2026-09-12

## Current implementation slice: live voice intake

The approved first cut uses Next.js/TypeScript and a Node.js/NestJS backend.
Residents have a live GPT-Live-1 conversation about road complaints or repair
questions. After an exact readback and verbal confirmation, the backend logs
an Ambiguous.ai task and explains that a customer service agent will contact
the resident if necessary. Repair-status answers and crew dispatch are outside
this increment. See [VOICE_INTAKE.md](VOICE_INTAKE.md) and the root README for
implementation scope, local setup, and verification.

The broader road-operations goal below remains the follow-on direction.

## Current goal

Build one convincing road-incident loop: image, voice-note, and text intake
plus location; normalization and agent routing; workflow selection; crew
assignment; task coordination; and a resident-visible resolution estimate.

## Working assumptions

- Use a web page as the initial resident reporting channel, accepting typed
  text, image upload, and voice-note upload.
- Use fixture employees, calendars, equipment, and incidents for the demo.
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
3. Implement resident report intake: text, image, voice note, and location.
4. Normalize/transcribe incoming inputs and route the evidence bundle to the agent.
5. Encode the three predefined workflows and their required roles/tasks.
6. Implement classification → workflow selection → crew assignment.
7. Build dispatcher and resident status views, including rationale and ETA.
8. Demonstrate task progression through verification and resolution.

## Team update format

```text
Done: …
Next: …
Blocked by: …
Decision needed: …
```
