# Demo story

## Promise

Show in under two minutes how a resident's road-blockage report becomes a
coordinated, explainable field plan rather than an unassigned ticket.

## Scenario

A storm knocks large branches across Pine Street. A resident uploads a photo,
places a map pin, and leaves a voice note: “Large branches are across both
lanes; traffic cannot pass.” The backend transcribes the note, retains the
original audio and photo as evidence, and routes the evidence bundle to the
agent. The agent identifies a road obstruction and selects the **remove
branches from road** workflow.

The chosen crew is:

- **Alex, chainsaw operator:** available now; qualified to cut branches.
- **Jordan, loader operator:** available now; qualified to load material.
- **Sam, transport driver:** available soon; qualified to drive material to the
  disposal site.

## Walkthrough

1. **Resident intake:** Submit the photo, voice note or typed description, and
   Pine Street map pin. The incident appears as `Reported`.
2. **Normalized report:** Show the original image/audio, voice transcript, and
   extracted incident details passed to the agent.
3. **Agent assessment:** Show the image/location/voice analysis, selected
   workflow, confidence, and a dispatcher override control.
4. **Crew plan:** Show why Alex, Jordan, and Sam were chosen: role capability,
   availability, and necessary sequencing.
5. **Workboard:** Show tasks in order: secure site → cut branches → load →
   transport/dispose → verify clear. Each task has an owner and status.
6. **Resident update:** Show a grounded ETA based on scheduled task durations
   and crew availability: “Crew assigned; expected road clearance by 2:30 PM.”
7. **Resolution:** Mark tasks complete. The road becomes `Resolved`, and the
   resident sees that it is clear.

## Acceptance checks

- Text, photo, or voice note plus location create an incident.
- Voice transcription and image extraction remain traceable to the original
  input and are supplied to the agent as structured evidence.
- A predefined workflow—not a free-form plan—is selected.
- The selected crew satisfies all required roles and availability constraints.
- Task dependencies are visible.
- ETA changes intelligibly if a required worker is unavailable.
- The resident and dispatcher have distinct but consistent views.

## Fallback

Use deterministic images, geocoded locations, employee schedules, and agent
classification outputs if live integrations risk the core demonstration. Label
all records **Demo data**.
