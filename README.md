# FADS

Hackathon prototype for an AI-assisted road-operations department: a resident
reports a road issue, an agent selects the right response workflow, and the
system coordinates an available field crew through completion.

The first implemented slice is **voice intake**: a resident talks about a road
complaint or repair question, the assistant reads the captured details back,
and a verbal confirmation logs one task in Ambiguous.ai. The assistant explains
that a customer service agent will contact the resident if necessary. This
slice does not answer repair-status questions or dispatch crews.

## Run locally

Requires Node.js 22 or newer and npm. The frontend is Next.js/TypeScript; the
backend is Node.js/NestJS. Run from the repository root:

```sh
npm install
cp apps/api/.env.example apps/api/.env
npm run dev
```

Open [localhost:3000](http://localhost:3000). The backend binds to
`127.0.0.1:3001`. Without credentials, the page offers a clearly labeled text
demo that simulates the conversation and creates no external records. Try a
road issue, then a location, then contact details or `skip`, followed by
`yes, log it` after the readback. A declined confirmation allows a corrected
description and a fresh readback.

## Live voice and records

Set `OPENAI_API_KEY` and `AMBIGUOUS_API_KEY` in `apps/api/.env`, then restart the
backend. The OpenAI project needs access to `gpt-live-1` and the configured
delegation model (`gpt-5.6-terra` by default). Allow microphone access in the
browser. Keep the browser on localhost for the configured origin.

Ambiguous.ai tasks are created in the token's workspace, unassigned unless
`AMBIGUOUS_ASSIGNEE_ID` is configured. To test real audio with simulated saves,
set `AMBIGUOUS_MODE=demo`; this is visibly labeled and never silently enabled.
The browser receives only its conversation token, never provider API keys.

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
[operations model](docs/plan/INTEGRATIONS.md).
