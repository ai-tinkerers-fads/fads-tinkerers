# Demo story

## Promise

In under two minutes, show how FADS turns scattered Slack, email, and one
multimodal input into shared, inspectable team context.

## Scenario

The team is preparing a partner demo. Slack contains a decision to use a new
sample dataset and assigns a follow-up. An email later raises a deadline risk
because the dataset has not arrived. A voice note or image adds one relevant
detail. Together, they create an unresolved blocker in shared memory.

## Walkthrough

1. **Open shared context.** Show the active decision, missing dataset, and
   source-backed blocker. Explain that Ambiguous supplies common memory and
   OpenClaw coordinates retrieval and updates.
2. **Open the timeline.** Show Slack, email, and voice/image events in time
   order, visibly labeled by source.
3. **Open “Needs attention.”** Show the blocker and a concrete, human-reviewed
   next action: confirm delivery and owner before a stated time.
4. **Show evidence.** Reveal the contributing Slack thread, email, and
   multimodal input with source, time, author where available, and a source
   link/reference.
5. **Show the memory update.** Make clear which context record was created or
   updated, by whom/what, and the evidence that supports it.

## Acceptance checks

- Slack and email appear in one workspace.
- A voice or image contribution appears in the same evidence model.
- Every summary claim traces to source events.
- A context update is attributable and inspectable.
- A viewer understands why this is better than checking channels separately.

## Fallback

Use deterministic fixture data, visibly marked **Demo data**, if integration
setup threatens the core demo. Preserve source identifiers and event shapes so
real adapters can replace fixtures later.
