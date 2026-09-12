# Now

Last updated: 2026-09-12

## Current goal

Build the thinnest end-to-end coordination demo: two input channels, one
normalized event stream, and a grounded "needs attention" view.

## Working assumptions

- Start with Slack and email as the two demonstrated sources.
- Use real read-only integrations only if credentials and setup are quick;
  otherwise use clearly labeled fixture data that resembles the real schema.
- Treat Ambiguous.ai and other sources as follow-on adapters, not demo
  dependencies.
- The application never sends messages or modifies source data.

## Next decisions

| Decision | Suggested default | Owner | Status |
| --- | --- | --- | --- |
| Demo sources | Slack + email | Unassigned | Open |
| Integration approach | Read-only APIs; fixtures as fallback | Unassigned | Open |
| Normalized event schema | One `ActivityEvent` contract | Unassigned | Open |
| Main demo surface | Timeline + attention queue + evidence drawer | Unassigned | Open |
| Deployment approach | Local first; hosted only if time remains | Unassigned | Open |

## Immediate work queue

1. Agree on the demo story in [DEMO.md](DEMO.md).
2. Define the smallest normalized event schema in [INTEGRATIONS.md](INTEGRATIONS.md).
3. Pick the application stack and create the runnable skeleton.
4. Implement one source adapter and fixture fallback.
5. Build the shared timeline, then the attention queue.
6. Add an evidence path from every generated claim back to source events.

## Team check-in template

Post a short update whenever a meaningful change lands:

```text
Done: …
Next: …
Blocked by: …
Decision needed: …
```

Keep this file to current intent and blockers. Record settled choices in
[DECISIONS.md](DECISIONS.md), not here.
