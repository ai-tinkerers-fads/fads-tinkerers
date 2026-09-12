# Decisions

Use one short entry per material choice. The goal is shared context, not a
formal approval process.

## Template

```md
## YYYY-MM-DD — Decision title

**Decision:** What we chose.

**Why:** Brief rationale and constraints.

**Consequences:** What this unlocks or gives up.

**Owner:** Name or `team`.
```

## 2026-09-12 — Optimize for a narrow, grounded coordination demo

**Decision:** The first demo will focus on two sources, a normalized activity
stream, an attention queue, and evidence back to the original items.

**Why:** This proves the coordination value without spending the weekend on
many integrations or unsupervised agent behavior.

**Consequences:** Additional modalities are represented as adapter candidates,
not required demo scope.

**Owner:** team

## 2026-09-12 — Keep source systems read-only

**Decision:** FADS will summarize and suggest actions, but will not send,
reply, or edit data in connected systems for the hackathon build.

**Why:** Read-only access lowers setup, safety, and trust costs while keeping
the core product idea visible.

**Consequences:** The demo ends with a proposed next action, rather than an
autonomous action.

**Owner:** team
