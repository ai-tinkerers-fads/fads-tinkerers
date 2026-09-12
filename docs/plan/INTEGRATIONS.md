# Integration map

## System roles

| Component | Role |
| --- | --- |
| Ambiguous | Shared-memory/context layer: retains and retrieves team context. |
| OpenClaw | Coordinator: runs adapters, queries memory, performs grounded reasoning, and records attributable context updates. |
| Web app | Human-facing workspace: context, timeline, evidence, and reviewable updates. |
| Source adapters | Translate Slack, email, voice, images, and future sources into common contracts. |

## Source-event contract

```ts
type ActivityEvent = {
  id: string; // stable: `${source}:${sourceRecordId}`
  source: "slack" | "email" | "voice" | "image" | "other";
  sourceRecordId: string;
  occurredAt: string; // ISO 8601 UTC
  author?: { id?: string; name: string };
  participants?: string[];
  text?: string;
  threadId?: string;
  permalink?: string;
  inputReference?: string; // audio/image reference where applicable
  metadata?: Record<string, unknown>;
};
```

## Shared-memory contract

```ts
type ContextRecord = {
  id: string;
  type: "fact" | "decision" | "ask" | "blocker" | "person" | "artifact";
  statement: string;
  status?: "active" | "resolved" | "superseded" | "uncertain";
  evidenceEventIds: string[];
  createdAt: string;
  updatedAt: string;
  updatedBy: { kind: "person" | "integration" | "coordinator"; id: string };
  sourceReferences?: string[];
};
```

Every write should retain the actor, time, change, and supporting evidence.
Connectors may query common context; their proposed updates must be visible and
reversible in the web app.

## Source status

| Source | Demo role | Access strategy | Status | Notes |
| --- | --- | --- | --- | --- |
| Slack | Primary | Read-only API or fixtures | Planned | Preserve channel, thread, author, timestamp, permalink. |
| Email | Primary | Read-only provider API or fixtures | Planned | Preserve sender, recipients, subject, time, thread, reference. |
| Voice | Multimodal | Record/upload or fixture transcript | Planned | Retain audio/reference, transcript, speaker/time if available. |
| Images / vision | Multimodal | Upload or fixture image + description | Planned | Retain image reference; label extracted information as derived. |
| Ambiguous | Shared memory | Validate API/integration | Planned | Confirm create, retrieve, update, provenance, deletion. |
| OpenClaw | Coordinator | Validate backend interface | Planned | Confirm adapter, retrieval, and update interfaces. |

## Rules

- Keep source systems read-only for this prototype.
- Normalize timestamps to UTC; render in the viewer’s locale.
- Retain a source reference for every event and input type for every multimodal
  event.
- Label extracted or model-inferred information as derived, with evidence.
- Do not store secrets or raw private data in the repository.
