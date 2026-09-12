# FADS

Hackathon prototype for an AI-assisted road-operations department: a resident
reports a road issue, an agent selects the right response workflow, and the
system coordinates an available field crew through completion.

## Run the coordination demo

Python 3.11+ with its standard library is sufficient; no API keys or dependency
installation are needed.

```sh
python3 -m fads_coordination.demo
```

Open [the local workboard](http://127.0.0.1:8787). It demonstrates preparation
reminders, crew availability changes, task completion and scoped feedback
memory using the approved branch-removal workflow. All notifications are
simulated in-app. The demo clock advances through the controls, and state
persists in `.fads/demo.sqlite` across restarts.

```sh
python3 -m unittest discover -s tests -v
python3 scripts/smoke_coordination.py
```

The smoke test starts its own temporary local server and database, exercises
real HTTP requests, and cleans up after itself. See the
[coordination module guide](docs/COORDINATION.md) for the team handoff, API,
memory behavior, limitations and a two-minute walkthrough.

Planning documents: [vision](docs/plan/VISION.md), [current work](docs/plan/NOW.md),
[decisions](docs/plan/DECISIONS.md), [demo](docs/plan/DEMO.md), and
[operations model](docs/plan/INTEGRATIONS.md).
