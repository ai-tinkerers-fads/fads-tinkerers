# Decisions

Short, dated choices for shared operating context—not a heavyweight approval
process.

## Template

```md
## YYYY-MM-DD — Title

**Decision:** What we chose.
**Why:** Constraints and rationale.
**Consequences:** What this unlocks or gives up.
**Owner:** Name or `team`.
```

## 2026-09-12 — Model the product as road-operations coordination

**Decision:** FADS is an AI-assisted government road-operations department,
not a cross-tool shared-memory product.

**Why:** The road-incident model gives the team a concrete user journey,
bounded workflows, meaningful agent decisions, and visual demo value.

**Consequences:** All UI and backend work should serve report intake, incident
assessment, workflow execution, and crew coordination.

**Owner:** team

## 2026-09-12 — Constrain agent behavior to predefined workflows

**Decision:** The agent chooses among a small catalog of human-defined
workflows, then fills in assignments and sequencing.

**Why:** It creates an explainable, safe, buildable demo while retaining the
core value of agentic coordination.

**Consequences:** Encode branch removal, pothole repair, and obstruction
removal as data; do not rely on free-form operational plans.

**Owner:** team

## 2026-09-12 — Use simulated operations data for the hackathon

**Decision:** Employees, schedules, equipment, incidents, and notifications
are fixture/simulated data for the demo.

**Why:** The product can be demonstrated without real municipal access or
safety-critical integrations.

**Consequences:** Clearly label the demo environment and keep all dispatch
actions reviewable.

**Owner:** team

## 2026-09-12 — Worker-side module boundary

**Decision:** Duc's slice is a worker-side module with hooks and info packages; agents and backend are out of scope for us.

**Why:** A host can mount the module without depending on the optional demo UI.

**Consequences:** Confirmed packages come in; schedules, reminders, conflicts, and completion references go out. This implementation uses fixtures and local sinks only.

**Owner:** Duc
