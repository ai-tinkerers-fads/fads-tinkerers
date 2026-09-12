import assert from "node:assert/strict";

const base = process.env.SMOKE_API_URL || "http://localhost:3001/api";
async function call(path, body, token) {
  const response = await fetch(`${base}${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: {
      "Content-Type": "application/json",
      Origin: process.env.SMOKE_WEB_ORIGIN || "http://localhost:3000",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const data = await response.json();
  return { status: response.status, data };
}

const config = await call("/config");
assert.equal(config.status, 200);
assert.equal(config.data.demoAvailable, true);
const created = await call("/sessions", { mode: "demo" });
assert.ok(created.status >= 200 && created.status < 300);
const { id, token } = created.data;
assert.ok(id && token);
const path = `/sessions/${id}`;
assert.equal((await call(path)).status, 401);
assert.equal((await call(path, undefined, "wrong-token")).status, 401);

async function say(text) {
  const result = await call(`${path}/demo-message`, { text }, token);
  assert.ok(
    result.status >= 200 && result.status < 300,
    JSON.stringify(result.data),
  );
  return result.data;
}

let state = await say("When will the pothole on our road be repaired?");
assert.equal(state.submission, null);
state = await say("Pine Street, Springfield, near the library");
assert.equal(state.submission, null);
state = await say("resident@example.test");
assert.equal(state.draft.kind, "question");
assert.equal(state.confirmationRequested, true);
assert.equal(state.submission, null);
const originalRevision = state.revision;
state = await say("No, I need to correct the description");
assert.equal(state.submission, null);
state = await say("When will both potholes by the library be repaired?");
assert.ok(state.revision > originalRevision);
assert.equal(state.confirmationRequested, true);
assert.equal(state.submission, null);
state = await say("Yes, log it");
assert.equal(state.submission.status, "saved");
assert.equal(state.submission.mode, "demo");
const recordId = state.submission.id;
state = await say("Yes, log it");
assert.equal(state.submission.id, recordId);
assert.equal((await call(path, undefined, token)).data.token, undefined);
const ended = await call(`${path}/end`, {}, token);
assert.equal(ended.data.status, "ended");
assert.equal(
  (await call(`${path}/demo-message`, { text: "yes" }, token)).status,
  409,
);
console.log(
  "HTTP smoke passed: intake, query classification, correction, confirmation, demo save, duplicate prevention, session authorization, and end.",
);
