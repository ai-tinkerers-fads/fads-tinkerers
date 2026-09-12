import "reflect-metadata";
import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Intake, isAffirmative } from "../src/intake";
import { SessionStore } from "../src/session-store";
import { AdapterError } from "../src/ambiguous.service";

const draft = {
  kind: "complaint" as const,
  description: "Large pothole",
  location: "Oak Road, Fairview",
  contact: "5551234",
};
function fixture(
  t: test.TestContext,
  createTask = async () => ({ id: "task-1", mode: "live" as const }),
) {
  const directory = mkdtempSync(join(tmpdir(), "fads-intake-"));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const store = new SessionStore(directory);
  const { session, token } = store.create("live");
  session.status = "active";
  const intake = new Intake(store, createTask);
  const readback = () => {
    const result = intake.prepare(session, draft);
    intake.append(session, {
      id: `read-${result.revision}`,
      role: "assistant",
      text: result.readback,
      startMs: 100,
      endMs: 200,
    });
    return result.revision;
  };
  const yes = () =>
    intake.append(session, {
      id: "yes",
      role: "user",
      text: "Yes, log it.",
      startMs: 300,
      endMs: 400,
    });
  return { store, session, token, intake, readback, yes, directory };
}

test("no tool can save without a complete trusted readback and later affirmative", async (t) => {
  let writes = 0;
  const f = fixture(t, async () => {
    writes++;
    return { id: "t", mode: "live" };
  });
  f.intake.prepare(f.session, draft);
  f.yes();
  await assert.rejects(f.intake.confirm(f.session, 1, 0), /read aloud/);
  assert.equal(writes, 0);
});
test("missing description or location cannot prepare confirmation or write", async (t) => {
  let writes = 0;
  const f = fixture(t, async () => {
    writes++;
    return { id: "t", mode: "live" };
  });
  for (const incomplete of [
    { ...draft, description: "" },
    { ...draft, location: "   " },
  ]) {
    assert.throws(() => f.intake.prepare(f.session, incomplete), /required/);
    assert.equal(f.session.draft, null);
    assert.equal(f.session.confirmationRequested, false);
    assert.equal(f.session.revision, 0);
    await assert.rejects(f.intake.confirm(f.session, 0, 0), /read aloud/);
  }
  assert.equal(writes, 0);
});
test("ending a session during confirmation settling prevents a new write", async (t) => {
  let writes = 0;
  const f = fixture(t, async () => {
    writes++;
    return { id: "t", mode: "live" };
  });
  const revision = f.readback();
  f.yes();
  const pending = f.intake.confirm(f.session, revision, 20);
  f.session.status = "ended";
  f.store.save(f.session);
  await assert.rejects(pending, /not active/);
  assert.equal(writes, 0);
  assert.equal(f.session.submission, null);
});
test("ending after a remote write starts preserves its eventual saved result", async (t) => {
  let finish!: () => void;
  const f = fixture(t, async () => {
    await new Promise<void>((resolve) => {
      finish = resolve;
    });
    return { id: "saved-after-close", mode: "live" };
  });
  const revision = f.readback();
  f.yes();
  const pending = f.intake.confirm(f.session, revision, 0);
  assert.equal(f.session.submission?.status, "saving");
  f.session.status = "ended";
  f.store.save(f.session);
  finish();
  assert.equal((await pending).id, "saved-after-close");
  assert.equal(f.store.public(f.session).submission?.status, "saved");
  assert.equal(f.session.status, "ended");
});
test("current revision saves exactly once, including concurrent calls", async (t) => {
  let writes = 0;
  const f = fixture(t, async () => {
    writes++;
    await new Promise((r) => setTimeout(r, 10));
    return { id: "t", mode: "live" };
  });
  const rev = f.readback();
  f.yes();
  const results = await Promise.allSettled([
    f.intake.confirm(f.session, rev, 0),
    f.intake.confirm(f.session, rev, 0),
  ]);
  assert.equal(results.filter((x) => x.status === "fulfilled").length, 1);
  assert.equal(writes, 1);
  assert.equal((await f.intake.confirm(f.session, rev, 0)).id, "t");
  assert.equal(writes, 1);
});
test("corrections invalidate the exact previous draft revision", async (t) => {
  const f = fixture(t);
  const old = f.readback();
  f.yes();
  f.intake.prepare(f.session, { ...draft, location: "Elm Road" });
  await assert.rejects(f.intake.confirm(f.session, old, 0), /read aloud/);
  await assert.rejects(
    f.intake.confirm(f.session, f.session.revision, 0),
    /read aloud/,
  );
});
test("late pre-readback affirmation and speech during readback cannot approve", async (t) => {
  const f = fixture(t);
  const rev = f.readback();
  f.intake.append(f.session, {
    id: "late-yes",
    role: "user",
    text: "Yes, log it",
    startMs: 150,
    endMs: 170,
  });
  await assert.rejects(
    f.intake.confirm(f.session, rev, 0),
    /spoke during readback/,
  );
});
test("an affirmative followed by correction during settling cannot save", async (t) => {
  const f = fixture(t);
  const rev = f.readback();
  f.yes();
  const pending = f.intake.confirm(f.session, rev, 20);
  f.intake.append(f.session, {
    id: "correction",
    role: "user",
    text: " actually no",
    startMs: 420,
    endMs: 450,
  });
  await assert.rejects(pending, /No unambiguous/);
  assert.equal(f.session.submission, null);
});
test("unknown remote results are durable and cannot be retried", async (t) => {
  let writes = 0;
  const f = fixture(t, async () => {
    writes++;
    throw new AdapterError("Timeout", "unknown");
  });
  const rev = f.readback();
  f.yes();
  const result = await f.intake.confirm(f.session, rev, 0);
  assert.equal(result.status, "unknown");
  await assert.rejects(f.intake.confirm(f.session, rev, 0), /unknown/);
  assert.throws(() => f.intake.prepare(f.session, draft), /already has/);
  const reopened = new SessionStore(f.directory);
  assert.equal(reopened.get(f.session.id).submission?.status, "unknown");
  assert.equal(writes, 1);
});
test("crash during saving rehydrates as unknown, and token protects records", (t) => {
  const f = fixture(t);
  f.session.submission = { status: "saving", key: "attempt" };
  f.store.save(f.session);
  const reopened = new SessionStore(f.directory);
  assert.equal(reopened.get(f.session.id).submission?.status, "unknown");
  assert.throws(
    () => reopened.authorized(f.session.id, "Bearer wrong"),
    /Invalid/,
  );
  assert.equal(
    reopened.authorized(f.session.id, `Bearer ${f.token}`).id,
    f.session.id,
  );
});
test("demo flow never invokes external create and needs confirmation", async (t) => {
  const f = fixture(t, async () => {
    throw new Error("Must not call externally");
  });
  f.session.mode = "demo";
  await f.intake.demoMessage(f.session, "There is a pothole in the road");
  await f.intake.demoMessage(f.session, "Oak Road near the park");
  await f.intake.demoMessage(f.session, "skip");
  assert.equal(f.session.submission, null);
  await f.intake.demoMessage(f.session, "yes log it");
  const saved = f.store.public(f.session).submission;
  assert.equal(saved?.status, "saved");
  assert.equal(saved?.mode, "demo");
});
test("ambiguous and negative phrases are not approval", () => {
  for (const text of [
    "yes but change the road",
    "no",
    "do not log it",
    "I said yes yesterday",
    "maybe",
    "yes actually no",
  ])
    assert.equal(isAffirmative(text), false, text);
});

test("chunked email and numeric phone readbacks accept equivalent spoken formatting", async (t) => {
  const f = fixture(t);
  const prepared = f.intake.prepare(f.session, {
    ...draft,
    contact: "sam.lee@example.com, +1 (555) 123-4567",
  });
  const spoken = prepared.readback
    .replace("sam dot lee at example dot com", "sam.lee@example.com")
    .replace(
      "plus one five five five one two three four five six seven",
      "+1 555 123 4567",
    );
  const halfway = Math.floor(spoken.length / 2);
  f.intake.append(f.session, {
    id: "fragment-1",
    role: "assistant",
    text: spoken.slice(0, halfway),
    startMs: 100,
    endMs: 150,
  });
  assert.equal(f.session.readbackCompleteAt, undefined);
  f.intake.append(f.session, {
    id: "fragment-2",
    role: "assistant",
    text: spoken.slice(halfway),
    startMs: 150,
    endMs: 200,
  });
  f.yes();
  assert.equal(
    (await f.intake.confirm(f.session, prepared.revision, 0)).status,
    "saved",
  );
});

const naturalDraft = {
  kind: "complaint" as const,
  description: "Two potholes.",
  location:
    "Cedar Avenue, near the downtown Fairview Public Library, Fairview.",
  contact: "resident@example.com",
  category: "Potholes",
};
const naturalReadback =
  "Here's what I'll log. Two potholes. Location, Cedar Avenue near the downtown Fairview Public Library, Fairview. Contact, resident at example dot com. Category, potholes. Shall I log it?";
function chunks(
  f: ReturnType<typeof fixture>,
  text: string,
  role: "assistant" | "user",
  start: number,
) {
  const parts = text.match(/\s*\S+/g) ?? [];
  parts.forEach((part, index) =>
    f.intake.append(f.session, {
      id: `${role}-${start}-${index}`,
      role,
      text: part,
      startMs: start + index * 200,
      endMs: start + (index + 1) * 200,
    }),
  );
  return start + parts.length * 200;
}

test("natural chunked factual readback plus yes of course saves without exact boilerplate", async (t) => {
  const f = fixture(t);
  const prepared = f.intake.prepare(f.session, naturalDraft);
  const end = chunks(f, naturalReadback, "assistant", 1000);
  chunks(f, "Yes, of course", "user", end + 1000);
  assert.equal(
    (await f.intake.confirm(f.session, prepared.revision, 0)).status,
    "saved",
  );
});

test("a fresh complete readback recovers after an interrupted earlier attempt", async (t) => {
  const f = fixture(t);
  const prepared = f.intake.prepare(f.session, naturalDraft);
  let end = chunks(f, "Two potholes. Location Cedar Avenue", "assistant", 1000);
  end = chunks(f, "Yes", "user", end + 200);
  chunks(
    f,
    "near the downtown Fairview Public Library, Fairview. Contact resident at example dot com. Shall I log it?",
    "assistant",
    end + 200,
  );
  await assert.rejects(
    f.intake.confirm(f.session, prepared.revision, 0),
    /read aloud/,
  );
  end = chunks(f, naturalReadback, "assistant", 20000);
  chunks(f, "That's correct", "user", end + 500);
  assert.equal(
    (await f.intake.confirm(f.session, prepared.revision, 0)).status,
    "saved",
  );
});

test("repeated affirmative turns and unchanged prepare preserve current confirmation", async (t) => {
  const f = fixture(t);
  const prepared = f.intake.prepare(f.session, naturalDraft);
  const end = chunks(f, naturalReadback, "assistant", 1000);
  chunks(f, "Yes", "user", end + 1000);
  chunks(f, "Yes, please log the complaint", "user", end + 5000);
  const repeated = f.intake.prepare(f.session, {
    ...naturalDraft,
    name: "",
    impact: "",
    category: "potholes",
  });
  assert.equal(repeated.revision, prepared.revision);
  assert.ok(f.session.readbackCompleteAt !== undefined);
  assert.equal(
    (await f.intake.confirm(f.session, repeated.revision, 0)).status,
    "saved",
  );
});

test("missing factual values or a missing confirmation question cannot establish readback", async (t) => {
  const f = fixture(t);
  const prepared = f.intake.prepare(f.session, naturalDraft);
  let end = chunks(
    f,
    naturalReadback.replace(
      "resident at example dot com",
      "another at example dot com",
    ),
    "assistant",
    1000,
  );
  chunks(f, "Yes", "user", end + 200);
  await assert.rejects(
    f.intake.confirm(f.session, prepared.revision, 0),
    /read aloud/,
  );
  end = chunks(
    f,
    naturalReadback.replace("Shall I log it?", ""),
    "assistant",
    20000,
  );
  chunks(f, "Yes", "user", end + 200);
  await assert.rejects(
    f.intake.confirm(f.session, prepared.revision, 0),
    /read aloud/,
  );
});

test("a genuine correction cannot be overridden by a later bare yes", async (t) => {
  const f = fixture(t);
  const prepared = f.intake.prepare(f.session, naturalDraft);
  let end = chunks(f, naturalReadback, "assistant", 1000);
  chunks(f, "Actually change the location to Birch Road", "user", end + 1000);
  chunks(f, "Yes", "user", end + 6000);
  await assert.rejects(
    f.intake.confirm(f.session, prepared.revision, 0),
    /No unambiguous/,
  );
  const revised = f.intake.prepare(f.session, {
    ...naturalDraft,
    location: "Birch Road",
  });
  assert.equal(revised.revision, prepared.revision + 1);
  await assert.rejects(
    f.intake.confirm(f.session, prepared.revision, 0),
    /read aloud/,
  );
  end = chunks(f, revised.readback, "assistant", 30000);
  chunks(f, "Yep", "user", end + 500);
  assert.equal(
    (await f.intake.confirm(f.session, revised.revision, 0)).status,
    "saved",
  );
});

test("affirmative fragments added while settling do not cause another confirmation loop", async (t) => {
  const f = fixture(t);
  const prepared = f.intake.prepare(f.session, naturalDraft);
  const end = chunks(f, naturalReadback, "assistant", 1000);
  chunks(f, "Yes", "user", end + 1000);
  const pending = f.intake.confirm(f.session, prepared.revision, 20);
  chunks(f, ", of course", "user", end + 1200);
  assert.equal((await pending).status, "saved");
});

test("natural affirmatives remain a finite grammar excluding conditions and corrections", () => {
  for (const phrase of [
    "Yes, of course",
    "That's correct",
    "Yep",
    "Yes please log the complaint",
    "Sure, go ahead",
  ])
    assert.equal(isAffirmative(phrase), true, phrase);
  for (const phrase of [
    "Yes but change the road",
    "Yes not yet",
    "Yes if you change it",
    "Actually no",
    "That's incorrect",
  ])
    assert.equal(isAffirmative(phrase), false, phrase);
});
