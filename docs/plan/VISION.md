# Vision

## One sentence

FADS gives a team shared, multimodal memory: information from tools,
conversations, voice, and visual inputs becomes common context that people and
integrations can safely find, understand, and update.

## Problem

Work context is fragmented. A decision can begin in Slack, an ask can arrive
by email, a useful detail can be spoken aloud, and supporting evidence can sit
inside an image. Each tool has a partial view; the team has no durable shared
context across them.

## Product shape

- **Shared memory:** Ambiguous stores or indexes durable, source-grounded team
  context: facts, decisions, asks, relationships, and updates.
- **Coordinator:** OpenClaw coordinates ingestion, retrieval, reasoning, and
  scoped updates between integrations and shared memory.
- **Web workspace:** a transparent page showing current context, evidence,
  activity timeline, open items, and connected sources.
- **Multimodal inputs:** text, voice, images, and other visual inputs can add
  context with their input type and provenance retained.
- **Two-way integrations:** connected tools can query common context and, when
  authorized, propose or make attributable, reversible updates.

## Weekend outcome

Demonstrate a shared-memory loop that:

1. ingests Slack-like messages and email-like messages into common context;
2. displays that context and source evidence in a web workspace;
3. uses OpenClaw to retrieve grounded context for an open ask, decision, or
   blocker; and
4. accepts a voice transcript or image and visibly incorporates its evidence.

## Principles

- **Source-first:** retain provenance, timestamps, participants, and links.
- **Inspectable memory:** users can see what was remembered, why, and when it
  changed.
- **Human-controlled:** updates are visible, attributable, and reversible; the
  demo does not send messages or edit source systems.
- **Useful before complete:** a dependable small flow beats a broad, brittle
  integration surface.

## Non-goals

- Replacing Slack, email, or project-management tools.
- A universal integration platform or perfect historical backfill.
- Fully autonomous external communications.
