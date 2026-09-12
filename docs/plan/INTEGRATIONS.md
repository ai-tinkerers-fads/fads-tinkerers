# Integration map

## Adapter contract

Each source adapter converts source records into a common `ActivityEvent`.
Keep the original payload or a stable source reference outside the generated
summary so users can inspect evidence.

```ts
type ActivityEvent = {
  id: string;                 // stable: `${source}:${sourceRecordId}`
  source: "slack" | "email" | "ambiguous" | "other";
  sourceRecordId: string;
  occurredAt: string;         // ISO 8601 UTC
  author: { id?: string; name: string };
  participants?: string[];
  text: string;
  threadId?: string;
  permalink?: string;
  metadata?: Record<string, unknown>;
};
```

## Source status

| Source | Demo role | Access strategy | Status | Notes |
| --- | --- | --- | --- | --- |
| Slack | Primary source | Read-only API or labeled fixtures | Planned | Preserve channel, thread, author, timestamp, permalink. |
| Email | Primary source | Read-only provider API or labeled fixtures | Planned | Preserve sender, recipients, subject, time, thread, link/reference. |
| Ambiguous.ai | Candidate adapter | Investigate later | Deferred | Do not make this a critical path before the two-source flow works. |
| Other tools | Candidate adapters | Contract + fixtures first | Deferred | Add only when a clear demo benefit exceeds setup cost. |

## Ingestion rules

- Source data is read-only for this prototype.
- Normalize timestamps to UTC; render in the viewer’s locale.
- Retain a source reference for every event.
- Do not invent authors, timestamps, or source links when using fixtures.
- Make fixture mode visible in the UI.
- Avoid storing secrets or raw private data in the repository.

## Attention-item contract

Derived items should retain their evidence rather than become detached LLM
claims.

```ts
type AttentionItem = {
  id: string;
  kind: "ask" | "decision" | "blocker" | "follow_up";
  title: string;
  summary: string;
  suggestedNextStep?: string;
  evidenceEventIds: string[];
  confidence?: "high" | "medium" | "low";
};
```

An attention item without at least one evidence event should not be shown as a
fact; at most, present it as an explicitly labeled hypothesis.
