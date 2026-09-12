# FADS

Hackathon prototype for an AI-assisted road-operations department: a resident
reports a road issue, an agent selects the right response workflow, and the
system coordinates an available field crew through completion.

The deployed website offers two modes: photo reports for maintenance planning
and voice conversations for confirmed complaint/question logging in Ambiguous.
Voice intake collects details, reads them back, and requires verbal confirmation
before creating a task assigned to FADS-Claw in Road Incidents. It does not
promise repair dates or dispatch a crew during a call.

## Run locally

Requires Node.js 22 or newer and npm. The frontend is Next.js/TypeScript; the
backend is Node.js/NestJS. Run from the repository root:

```sh
npm install
cp apps/api/.env.example apps/api/.env
npm run dev:voice
```

Open [localhost:3000/voice](http://localhost:3000/voice). Set
`NEXT_PUBLIC_API_URL=http://localhost:3001/api` in `apps/web/.env.local` for this
local setup. Run `npm run dev` separately for the photo app on port 8808.
Without provider credentials the voice page offers a clearly labeled text demo
that creates no external records. Try a
road issue, then a location, then contact details or `skip`, followed by
`yes, log it` after the readback. A declined confirmation allows a corrected
description and a fresh readback.

## Live voice and records

For local development, set `OPENAI_API_KEY` and `AMBIGUOUS_API_KEY` in
`apps/api/.env`. The OpenAI project needs access to `gpt-live-1` and the
delegation model (`gpt-5.6-terra` by default). Allow microphone access in your
browser. Set `WEB_ORIGIN` to the exact browser origin.

Ambiguous tasks use `AMBIGUOUS_API_KEY` or the server's `FADS_CLAW_TOKEN`.
`FADS_RESOURCES_PATH` supplies the Road Incidents project and Reported status.
`AMBIGUOUS_ASSIGNEE_ID` selects the assignee. For audio with simulated saves,
set `AMBIGUOUS_MODE=demo`; this is visibly labeled and never silently enabled.
The browser receives only its conversation token, never provider API keys.

Production: https://fads.aindoori.com/voice. The main website includes a
Photo report / Voice report switch. Next.js proxies `/voice` to port 8810
and `/voice-api` to port 8811. Install the units in `deploy/` after `npm run build`.
The API unit reads `~/.config/fads/runtime.env` and `~/.config/fads/openai.env`.
The voice web process never receives the OpenAI key.
Inspect service status with `systemctl status fads-voice-api fads-voice-web`.

## Verification

```sh
npm run typecheck
npm test
npm run build
# With the backend running:
npm run test:smoke
```

Unit tests cover the adapter and confirmation/duplicate-write rules. The HTTP
smoke test uses only an explicit demo session, covering a query, correction,
confirmation, simulated logging, authorization, and session shutdown.

## Prototype limits

One record per conversation. Transcripts, drafts, and save outcomes are stored
locally under `apps/api/.data` by default; raw audio is not retained by this
application. This is a single-process, local prototype with no multi-user login.
Review data retention and authentication before hosting it. The text demo is
deterministic and cannot replace testing an actual spoken conversation.

If a write times out, its outcome stays **unknown** and is not retried. Check
Ambiguous.ai for the intake reference before creating another record. Ending
a conversation stops new actions but cannot undo an already-started save.

See the [voice intake plan](docs/plan/VOICE_INTAKE.md) for this increment.

Planning documents: [vision](docs/plan/VISION.md), [current work](docs/plan/NOW.md),
[decisions](docs/plan/DECISIONS.md), [demo](docs/plan/DEMO.md), and
[operations model](docs/plan/INTEGRATIONS.md), and
[incident-report contract](docs/plan/REPORTS.md).
