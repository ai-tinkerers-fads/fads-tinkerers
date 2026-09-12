# Now

Last updated: 2026-09-12

## Current goal

Build the thinnest end-to-end shared-memory demo: two input channels, common
context in Ambiguous, OpenClaw coordination, and a web workspace explaining
what the team knows and why.

## Working assumptions

- Demonstrate Slack and email first; use read-only APIs when quick, otherwise
  use clearly labeled fixtures.
- Use Ambiguous for the shared-memory/context layer, subject to its available
  API and integration model.
- Use OpenClaw for adapter orchestration, retrieval, and context updates.
- Include one multimodal input: voice transcript or image with extracted
  context.
- Never send messages or modify source data in the prototype.

## Decisions to make

| Decision | Suggested default | Owner | Status |
| --- | --- | --- | --- |
| Demo sources | Slack + email | Unassigned | Open |
| Shared-memory contract | Context records with provenance/history | Unassigned | Open |
| Multimodal input | Voice transcript or image | Unassigned | Open |
| Main surface | Shared context + timeline + evidence drawer | Unassigned | Open |
| Deployment | Local first | Unassigned | Open |

## Immediate work queue

1. Confirm the demo narrative in [DEMO.md](DEMO.md).
2. Validate Ambiguous and OpenClaw integration paths.
3. Define common source-event and memory contracts.
4. Build the runnable web-app skeleton.
5. Implement one source adapter, one multimodal path, and fixture fallbacks.
6. Make every memory record and generated claim traceable to evidence.

## Team update format

```text
Done: …
Next: …
Blocked by: …
Decision needed: …
```

Use this page for current intent; record settled choices in
[DECISIONS.md](DECISIONS.md).
