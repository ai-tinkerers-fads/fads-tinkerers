# Vision

## One sentence

FADS helps a road-operations department turn a resident's report into a safe,
coordinated field response: identify the incident, choose the right workflow,
assign the capable available crew, and communicate the expected resolution.

## Problem

A blocked road, pothole, accident debris, or other hazard requires more than
logging a ticket. Dispatch must understand what happened, determine the work
required, find people with the right skills and availability, coordinate their
dependencies, and keep the reporting resident informed.

## Product flow

1. **Report:** A resident submits a road issue through a web page with a photo,
   voice note, typed text, location, or any useful combination of those inputs.
2. **Normalize and assess:** The backend records the incident, transcribes
   voice notes, extracts relevant image evidence, and routes the normalized
   report plus original evidence to an agent. The agent selects from predefined
   operational workflows.
3. **Plan:** The system determines required skills, equipment, and task
   dependencies; it chooses an available, qualified crew.
4. **Coordinate:** Crew members receive work in the right sequence, with the
   incident location and overall plan visible.
5. **Resolve:** Work completion updates the incident and gives the resident a
   grounded expected-completion time and resolution update.

## Initial workflow catalog

- **Remove branches from road:** secure site → cut/remove branches → load
  material → transport/dispose → verify road is clear.
- **Fix pothole:** secure site → prepare hole → apply repair → verify/reopen.
- **Remove car/debris from road:** secure site → recover/remove obstruction →
  transport/dispose → verify road is clear.

## Weekend outcome

Demonstrate one end-to-end incident:

1. a resident submits an image or voice note, typed text, and location;
2. the agent uses the normalized inputs and original evidence to classify
   fallen branches blocking a road and chooses the branch removal workflow;
3. the coordinator assigns an available chainsaw operator, loader operator,
   and disposal/transport driver, respecting skills and schedules;
4. the web app shows the ordered work plan and expected completion time; and
5. task completion updates the incident and creates a resident-facing status.

## Principles

- **Workflow-bound autonomy:** the agent selects and fills predefined workflows;
  it does not invent unsafe field procedures.
- **Multimodal evidence:** preserve each submitted input and distinguish a
  voice transcript or visual extraction from the original report.
- **Right capability, right time:** assignment uses skill, availability,
  equipment, and dependencies.
- **Human override:** dispatchers can review or replace classification,
  assignments, and estimates.
- **Auditable decisions:** show why the system chose a workflow and crew.

## Non-goals

- Real emergency dispatch or autonomous safety-critical decisions.
- Live municipal-system integrations.
- City-wide route, labor-rule, or fleet optimization.
