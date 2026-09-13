import { BadRequestException, ConflictException } from "@nestjs/common";
import { randomUUID } from "node:crypto";
import {
  AdapterError,
  type ComplaintDraft,
  type TaskRecord,
} from "./ambiguous.service";
import { SessionStore } from "./session-store";
import type { StoredSession, Transcript } from "./types";

export const ACKNOWLEDGMENT =
  "Your complaint/question has been logged. A customer service agent will contact you if necessary.";
const DIGITS = [
  "zero",
  "one",
  "two",
  "three",
  "four",
  "five",
  "six",
  "seven",
  "eight",
  "nine",
];
// Spell contact punctuation and individual digits consistently in the requested readback.
// Accept equivalent transcript formatting (e.g. "555" versus "five five five").
export const normalize = (text: string) =>
  text
    .toLowerCase()
    .replace(/@/g, " at ")
    .replace(/\+/g, " plus ")
    .replace(/([a-z0-9])\.(?=[a-z0-9])/g, "$1 dot ")
    .replace(/\d/g, (digit) => ` ${DIGITS[Number(digit)]} `)
    .replace(/[^a-z]+/g, " ")
    .trim()
    .replace(/\s+/g, " ");
export const spokenContact = (contact: string) =>
  contact
    .replace(/@/g, " at ")
    .replace(/\./g, " dot ")
    .replace(/\+/g, " plus ")
    .replace(/\d/g, (digit) => ` ${DIGITS[Number(digit)]} `)
    .replace(/[()-]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
export function isAffirmative(text: string) {
  const answer = normalize(text).replace(/\bthat s\b/g, "that is");
  // A finite affirmative grammar, not a search for the word "yes". Extra facts,
  // conditions, negation, and corrections fail closed.
  const prefix =
    "(?:yes|yeah|yep|sure|absolutely|certainly|of course|correct|that is correct)";
  const action =
    "(?:go ahead|(?:please )?(?:log|record|submit)(?: (?:it|this|that|the complaint|the question|my complaint|my question))?)";
  return new RegExp(
    `^(?:${prefix}(?: (?:${prefix}|please|${action}))*|${action})(?: thank you)?$`,
  ).test(answer);
}

const draftFields = [
  "kind",
  "description",
  "location",
  "contact",
  "name",
  "category",
  "impact",
] as const;
const draftKey = (draft: ComplaintDraft) =>
  JSON.stringify(draftFields.map((field) => normalize(draft[field] ?? "")));
const factText = (text: string) =>
  normalize(text)
    .split(" ")
    .filter(
      (word) => !["a", "an", "the", "on", "in", "at", "near"].includes(word),
    )
    .join(" ");
function containsFacts(text: string, draft: ComplaintDraft) {
  const spoken = ` ${factText(text)} `;
  return draftFields
    .filter((field) => field !== "kind")
    .every((field) => {
      const value = draft[field];
      return !value || spoken.includes(` ${factText(value)} `);
    });
}
const confirmationQuestion =
  /(?:\b(?:shall|should|can|may) I (?:log|record|submit) (?:this|it|that|your complaint|your question|the complaint|the question)|\b(?:is|does) (?:that|this) (?:correct|sound correct|look correct))\s*\?\s*$/i;
export function validateDraft(input: unknown): ComplaintDraft {
  if (!input || typeof input !== "object")
    throw new BadRequestException("A complaint draft is required");
  const record = input as Record<string, unknown>;
  if (record.kind !== "complaint" && record.kind !== "question")
    throw new BadRequestException("Choose complaint or question");
  const draft: ComplaintDraft = {
    kind: record.kind,
    description: "",
    location: "",
  };
  for (const field of [
    "description",
    "location",
    "contact",
    "name",
    "category",
    "impact",
  ] as const) {
    if (record[field] !== undefined && record[field] !== null) {
      if (
        typeof record[field] !== "string" ||
        (record[field] as string).length > 2000
      )
        throw new BadRequestException(`Invalid ${field}`);
      draft[field] = (record[field] as string).trim();
    }
  }
  if (!draft.description || !draft.location)
    throw new BadRequestException(
      "Description and road/location are required. Ask the customer for missing details.",
    );
  return draft;
}

export class Intake {
  constructor(
    private readonly store: SessionStore,
    private readonly createTask: (
      draft: ComplaintDraft,
      key: string,
    ) => Promise<TaskRecord>,
  ) {}

  append(session: StoredSession, entry: Transcript) {
    if (session.transcript.some((item) => item.id === entry.id)) return;
    session.transcript.push(entry);
    this.refreshReadback(session);
    this.store.save(session);
  }

  prepare(session: StoredSession, input: unknown) {
    this.assertActive(session);
    if (session.submission && session.submission.status !== "failed")
      throw new ConflictException(
        "This conversation already has a submission. Start a new conversation for another issue.",
      );
    const draft = validateDraft(input);
    const key = draftKey(draft);
    if (
      session.readback &&
      session.confirmationRequested &&
      (session.preparedDraftKey ??
        (session.draft && draftKey(session.draft))) === key
    ) {
      this.refreshReadback(session);
      this.store.save(session);
      return this.preparedResult(session);
    }
    session.draft = draft;
    session.preparedDraftKey = key;
    session.revision += 1;
    session.submission = null;
    session.confirmationRequested = true;
    session.readbackAfter = session.transcript.length;
    session.readbackCompleteAt = undefined;
    session.readbackEndMs = undefined;
    session.readbackMinStartMs = Math.max(
      0,
      ...session.transcript.map((t) => t.endMs ?? 0),
    );
    session.readback = `I will log your ${draft.kind}: ${draft.description}. Location: ${draft.location}.${draft.contact ? ` Contact: ${spokenContact(draft.contact)}.` : ""}${draft.name ? ` Name: ${draft.name}.` : ""}${draft.category ? ` Category: ${draft.category}.` : ""}${draft.impact ? ` Reported impact: ${draft.impact}.` : ""} Shall I log this?`;
    this.store.save(session);
    return this.preparedResult(session);
  }

  private preparedResult(session: StoredSession) {
    return {
      revision: session.revision,
      readback: session.readback!,
      instruction:
        session.readbackCompleteAt !== undefined
          ? "The current draft has already been read back. If the customer has now clearly agreed, call confirm_draft with this revision. Do not repeat the readback or prepare unchanged facts."
          : "Read the complete readback string aloud word for word, including all description qualifiers and every field. Do not summarize, paraphrase, or omit words. End with Shall I log this? and stop to listen. A natural clear affirmative is sufficient. Then call confirm_draft with this revision. Changed facts require prepare_draft and a fresh readback.",
    };
  }

  async confirm(session: StoredSession, revision: number, settleMs = 1500) {
    this.assertActive(session);
    if (session.submission?.status === "saved") return session.submission;
    if (session.submission && session.submission.status !== "failed")
      throw new ConflictException(
        "Submission already underway or outcome unknown. Do not retry.",
      );
    this.checkConfirmation(session, revision);
    if (settleMs) await new Promise((resolve) => setTimeout(resolve, settleMs));
    // Re-evaluate the current bounded answer after settling. More affirmative
    // fragments are fine; any correction, rejection, or revised draft is not.
    this.checkConfirmation(session, revision);
    if (session.submission && session.submission.status !== "failed")
      throw new ConflictException("Submission already underway.");
    const key = `${session.id}:${revision}`;
    session.submission = { status: "saving", key };
    session.confirmationRequested = false;
    this.store.save(session); // Persist BEFORE calling the remote service.
    try {
      // Explicit demo sessions never invoke external integrations, even when credentials exist.
      const record =
        session.mode === "demo"
          ? { id: `DEMO-${session.id.slice(0, 8)}`, mode: "demo" as const }
          : await this.createTask(session.draft!, key);
      session.submission = { status: "saved", key, ...record };
    } catch (error) {
      session.submission = {
        status:
          error instanceof AdapterError && error.outcome === "rejected"
            ? "failed"
            : "unknown",
        key,
        error:
          error instanceof AdapterError
            ? error.message
            : "Submission outcome is unknown. Check Ambiguous.ai before creating another record.",
      };
    }
    this.store.save(session);
    return session.submission;
  }

  async demoMessage(session: StoredSession, text: string) {
    this.assertActive(session);
    if (session.mode !== "demo")
      throw new BadRequestException(
        "Text simulation is only available in demo mode",
      );
    if (!text.trim() || text.length > 2000)
      throw new BadRequestException("Enter 1–2000 characters");
    this.append(session, { id: randomUUID(), role: "user", text });
    const say = (message: string) =>
      this.append(session, {
        id: randomUUID(),
        role: "assistant",
        text: message,
      });
    if (session.submission?.status === "saved") {
      say(
        "This demo record is already saved. Start a new conversation to log another issue.",
      );
      return;
    }
    switch (session.demoStep) {
      case "issue": {
        if (
          !/road|street|pothole|branch|debris|repair|damage|lane|pavement|traffic|vehicle|highway|sidewalk/i.test(
            text,
          )
        ) {
          say(
            "I can log road-related complaints and questions. Please describe the road damage or your repair question.",
          );
          break;
        }
        session.draft = {
          kind: /\?|when|status|how long|question/i.test(text)
            ? "question"
            : "complaint",
          description: text,
          location: "",
        };
        session.demoStep = "location";
        say(
          "Which road is this on? Please include the town and a nearby landmark or intersection.",
        );
        break;
      }
      case "location":
        session.draft!.location = text;
        session.demoStep = "contact";
        say(
          "What phone number or email should a customer service agent use if follow-up is necessary? You can say skip.",
        );
        break;
      case "contact": {
        session.draft!.contact = /^(skip|no|none|prefer not to say)$/i.test(
          text.trim(),
        )
          ? ""
          : text;
        const result = this.prepare(session, session.draft);
        session.demoStep = "confirm";
        say(result.readback);
        break;
      }
      case "correction": {
        session.draft!.description = text;
        const result = this.prepare(session, session.draft);
        session.demoStep = "confirm";
        say(result.readback);
        break;
      }
      case "confirm": {
        if (isAffirmative(text)) {
          const result = await this.confirm(session, session.revision, 0);
          say(
            result.status === "saved"
              ? `Demo only: a simulated record ${result.id} was saved. In a live call: ${ACKNOWLEDGMENT}`
              : "The record could not be logged.",
          );
        } else {
          session.confirmationRequested = false;
          session.readbackCompleteAt = undefined;
          session.demoStep = "correction";
          say(
            "Nothing has been logged. In this text demo, enter the corrected issue description; I will read the draft back again. Start a new demo to change location or contact.",
          );
        }
        break;
      }
    }
    this.store.save(session);
  }

  private assertActive(session: StoredSession) {
    if (session.status !== "active")
      throw new ConflictException("Conversation is not active");
  }
  private refreshReadback(session: StoredSession) {
    if (!session.draft || session.readbackAfter === undefined) return;
    const entries = session.transcript
      .slice(session.readbackAfter)
      .map((entry, offset) => ({
        entry,
        index: session.readbackAfter! + offset,
      }));
    if (session.mode === "live")
      entries.sort(
        (a, b) => (a.entry.startMs ?? Infinity) - (b.entry.startMs ?? Infinity),
      );
    let block: Transcript[] = [];
    let completedStartMs: number | undefined;
    session.readbackCompleteAt = undefined;
    session.readbackEndMs = undefined;
    for (const { entry, index } of entries) {
      if (
        session.mode === "live" &&
        (entry.startMs === undefined ||
          entry.startMs < (session.readbackMinStartMs ?? 0))
      )
        continue;
      if (entry.role === "user") {
        if (
          session.mode === "live" &&
          entry.startMs !== undefined &&
          completedStartMs !== undefined &&
          entry.startMs >= completedStartMs &&
          entry.startMs < (session.readbackEndMs ?? 0)
        ) {
          session.readbackCompleteAt = undefined;
          session.readbackEndMs = undefined;
        }
        block = [];
        continue;
      }
      if (
        block.length &&
        entry.startMs !== undefined &&
        entry.startMs - (block.at(-1)!.endMs ?? entry.startMs) > 10000
      )
        block = [];
      block.push(entry);
      const spoken = block.map((fragment) => fragment.text).join("");
      // Only a newly completed question can establish a boundary, so later
      // filler speech never moves it past an already-given answer.
      if (
        !entry.text.includes("?") ||
        !confirmationQuestion.test(spoken) ||
        !containsFacts(spoken, session.draft)
      )
        continue;
      session.readbackCompleteAt = index;
      session.readbackEndMs = entry.endMs;
      completedStartMs = block[0].startMs;
    }
  }

  private checkConfirmation(session: StoredSession, revision: number) {
    this.assertActive(session);
    this.refreshReadback(session);
    if (
      !session.draft ||
      !session.confirmationRequested ||
      revision !== session.revision ||
      session.readbackCompleteAt === undefined
    ) {
      throw new ConflictException(
        "The current draft facts and confirmation question must be read aloud before confirmation. If the customer spoke during readback, repeat the current facts once.",
      );
    }
    const entries =
      session.mode === "demo"
        ? session.transcript.slice(session.readbackCompleteAt + 1)
        : session.transcript
            .slice(session.readbackAfter)
            .filter(
              (t) =>
                t.role === "user" &&
                t.startMs !== undefined &&
                t.startMs >= (session.readbackEndMs ?? Infinity),
            )
            .sort((a, b) => a.startMs! - b.startMs!);
    const turns: Transcript[][] = [];
    for (const entry of entries) {
      if (entry.role !== "user") continue;
      const last = turns.at(-1);
      if (
        !last ||
        session.mode === "demo" ||
        (entry.startMs ?? 0) - (last.at(-1)!.endMs ?? 0) > 1800
      )
        turns.push([entry]);
      else last.push(entry);
    }
    // Repeated affirmative turns are harmless. A correction at any point after
    // this readback requires a new draft/readback rather than a later bare yes.
    if (
      !turns.length ||
      turns.some((turn) => !isAffirmative(turn.map((t) => t.text).join("")))
    ) {
      throw new ConflictException(
        "No unambiguous verbal confirmation after the current readback. Listen for a clear affirmative, or collect corrections and read the updated facts back.",
      );
    }
  }
}
