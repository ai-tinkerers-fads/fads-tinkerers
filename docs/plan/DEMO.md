# Demo story

## The promise

In under two minutes, show how FADS turns scattered Slack and email activity
into a shared understanding of what needs attention next.

## Scenario

The team is preparing a partner demo. A Slack thread contains a decision to
use a new sample dataset and assigns a follow-up. An email later raises a
deadline risk because the dataset has not arrived. Neither item is enough on
its own; together, they reveal an unresolved blocker.

## Walkthrough

1. **Open the activity timeline.** Show mixed Slack and email events in
   chronological order, visibly labeled by source.
2. **Orient the viewer.** FADS displays a concise current-state summary:
   the sample dataset decision exists, the delivery is still pending, and the
   partner demo is at risk.
3. **Open “Needs attention.”** Show a small ranked queue with one concrete
   blocker: confirm dataset delivery and owner.
4. **Show the evidence.** Open the item to reveal the contributing Slack
   thread and email, including source, time, author, and a link or stable
   source reference.
5. **Close with a safe recommendation.** FADS proposes a human-reviewed next
   step, such as “ask the dataset owner for an ETA before 3 PM.” It does not
   send the message.

## Acceptance checks

- At least two sources appear in the same view.
- Every summary claim is traceable to one or more source events.
- The UI makes an unresolved request, decision, or blocker obvious.
- A viewer understands why this is better than checking the two channels
  separately.

## If integrations are unavailable

Use deterministic fixture data, clearly marked **Demo data**, with source
identifiers and realistic event shapes. The UI and reasoning path should stay
the same so a real adapter can replace each fixture later.
