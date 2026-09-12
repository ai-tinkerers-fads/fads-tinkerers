# FADS

Hackathon prototype for an AI-assisted road-operations department: a resident
reports a road issue, an agent selects the right response workflow, and the
system coordinates an available field crew through completion.

Planning documents: [vision](docs/plan/VISION.md), [current work](docs/plan/NOW.md),
[decisions](docs/plan/DECISIONS.md), [demo](docs/plan/DEMO.md), and
[operations model](docs/plan/INTEGRATIONS.md), and
[incident-report contract](docs/plan/REPORTS.md).

## Worker coordination module

The road-operations worker coordination module accepts confirmed assignments, plans preparation and reminders, and records completion and scoped feedback. See [the module hooks contract, run instructions, and tests](fads_coordination/README.md).
