import "reflect-metadata";
import { test, afterEach } from "node:test";
import assert from "node:assert/strict";
import {
  AdapterError,
  AmbiguousService,
  type ComplaintDraft,
} from "../src/ambiguous.service";

const originalFetch = globalThis.fetch;
const originalEnv = { ...process.env };
afterEach(() => {
  globalThis.fetch = originalFetch;
  process.env = { ...originalEnv };
});
const draft: ComplaintDraft = {
  kind: "complaint",
  category: "pothole",
  location: "Main Road near library",
  description: "Deep pothole blocks one lane",
  contact: "555-0100",
};
function configure() {
  process.env.AMBIGUOUS_API_KEY = "test-secret";
  delete process.env.AMBIGUOUS_MODE;
  delete process.env.AMBIGUOUS_ASSIGNEE_ID;
}

test("maps confirmed draft to documented task schema and unwraps task ID", async () => {
  configure();
  let count = 0;
  globalThis.fetch = async (url, options) => {
    count++;
    assert.equal(url, "https://app.ambiguous.ai/api/tasks");
    assert.equal(options?.method, "POST");
    assert.equal(
      (options?.headers as Record<string, string>).Authorization,
      "Bearer test-secret",
    );
    const body = JSON.parse(options?.body as string);
    assert.deepEqual(Object.keys(body).sort(), ["description", "title"]);
    assert.match(body.description, /Intake reference: intake-1/);
    assert.match(body.description, /555-0100/);
    return Response.json({ task: { id: "task-1" } }, { status: 201 });
  };
  assert.deepEqual(await new AmbiguousService().createTask(draft, "intake-1"), {
    id: "task-1",
    url: "https://app.ambiguous.ai/tasks/task-1",
    mode: "live",
  });
  assert.equal(count, 1);
});

test("network timeout is unknown and never retried", async () => {
  configure();
  let count = 0;
  globalThis.fetch = async () => {
    count++;
    throw new DOMException("Timeout", "TimeoutError");
  };
  await assert.rejects(
    new AmbiguousService().createTask(draft, "intake-2"),
    (error: unknown) =>
      error instanceof AdapterError && error.outcome === "unknown",
  );
  assert.equal(count, 1);
});

test("HTTP rejection is distinguished from uncertain server error", async () => {
  configure();
  for (const [status, outcome] of [
    [401, "rejected"],
    [500, "unknown"],
  ] as const) {
    globalThis.fetch = async () =>
      new Response("Provider internal details", { status });
    await assert.rejects(
      new AmbiguousService().createTask(draft, "intake-3"),
      (error: unknown) =>
        error instanceof AdapterError &&
        error.outcome === outcome &&
        !error.message.includes("Provider internal details"),
    );
  }
});

test("successful HTTP response without documented task ID remains unknown", async () => {
  configure();
  globalThis.fetch = async () => Response.json({ id: "wrong-envelope" });
  await assert.rejects(
    new AmbiguousService().createTask(draft, "intake-4"),
    (error: unknown) =>
      error instanceof AdapterError && error.outcome === "unknown",
  );
});

test("missing credentials never silently produces a demo success", async () => {
  configure();
  delete process.env.AMBIGUOUS_API_KEY;
  globalThis.fetch = async () => {
    throw new Error("Must not call network");
  };
  await assert.rejects(
    new AmbiguousService().createTask(draft, "intake-5"),
    (error: unknown) =>
      error instanceof AdapterError && error.outcome === "rejected",
  );
  process.env.AMBIGUOUS_MODE = "demo";
  assert.deepEqual(await new AmbiguousService().createTask(draft, "intake-5"), {
    id: "demo-intake-5",
    mode: "demo",
  });
});
