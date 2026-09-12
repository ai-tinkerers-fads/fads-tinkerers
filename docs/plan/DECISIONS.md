# Decisions

Short, dated choices for shared context—not a heavyweight approval process.

## Template

```md
## YYYY-MM-DD — Title

**Decision:** What we chose.
**Why:** Constraints and rationale.
**Consequences:** What this unlocks or gives up.
**Owner:** Name or `team`.
```

## 2026-09-12 — Shared memory is the product center

**Decision:** FADS will organize around inspectable common context rather than
only a unified inbox or activity timeline.

**Why:** The core value is for people and integrations to share durable context
across modalities.

**Consequences:** Every derived record needs provenance and update history.

**Owner:** team

## 2026-09-12 — OpenClaw coordinates; Ambiguous holds context

**Decision:** Use OpenClaw as the coordinating backend and Ambiguous as the
shared-memory/context layer, subject to integration validation.

**Why:** This creates a clean separation between orchestration and durable
team knowledge.

**Consequences:** Confirm both systems' available APIs before locking UI or
adapter architecture.

**Owner:** team

## 2026-09-12 — Prototype stays read-only toward source systems

**Decision:** FADS may propose shared-memory updates, but it will not send,
reply, or edit connected source systems during the hackathon demo.

**Why:** This keeps the demo safe, trustworthy, and achievable.

**Consequences:** The demo ends with a human-reviewed recommendation.

**Owner:** team
