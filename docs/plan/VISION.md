# Vision

## One sentence

FADS is a lightweight coordination layer that turns fragmented conversations
and requests across work tools into a clear, shared answer to: **what needs
attention, why, and who can move it forward?**

## Problem

Work context is fragmented. A decision may begin in Slack, an ask may arrive
by email, and the relevant follow-up may live in another AI or work tool.
People lose time reconstructing the story, duplicate work, and miss requests
whose ownership was implicit rather than explicit.

## First user

A small team coordinating a fast-moving project across at least two channels.
They need a quick orientation rather than another inbox: current activity,
open asks, decision context, and suggested next moves.

## Weekend outcome

Demonstrate a trustworthy coordination view that:

1. brings Slack-like messages and email-like messages into a shared timeline;
2. preserves source links and enough context to inspect each item;
3. identifies a small number of open asks, decisions, or blockers; and
4. explains the evidence behind each summary or suggested action.

## Product principles

- **Source-first.** Keep provenance, timestamps, participants, and links.
- **Useful before complete.** A narrow, reliable two-source flow beats broad
  but brittle integrations.
- **Human stays in control.** Suggest and summarize; do not send, reply, or
  change anything in a connected tool during the demo.
- **Reversible by default.** Ingestion and analysis should be safe to rerun.
- **Legible reasoning.** A user can see what messages led to a conclusion.

## Non-goals for the hackathon

- Replacing Slack, email, or a project-management system.
- Building a universal integration platform.
- Fully autonomous agents that communicate externally.
- Perfect entity resolution, permissions, or historical backfill.
