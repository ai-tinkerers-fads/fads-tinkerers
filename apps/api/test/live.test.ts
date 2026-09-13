import test from "node:test";
import assert from "node:assert/strict";
import { liveConfig, LiveService } from "../src/live.service";
import { SessionStore } from "../src/session-store";
import { Intake } from "../src/intake";
import { mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import type OpenAI from "openai";
import type { SidebandWS } from "openai/resources/live/sideband/ws";

test("Live config uses real GPT-Live contract and blocks frontend control of tools", () => {
  const config = liveConfig();
  assert.equal(config.model, "gpt-live-1");
  assert.equal(config.store, false);
  assert.deepEqual(config.client?.data_channel.allowed_client_events, [
    "session.close",
    "session.input_audio.mute",
    "session.input_audio.unmute",
  ]);
  assert.equal(config.delegation?.type, "responses");
  if (config.delegation?.type !== "responses")
    throw new Error("Expected Responses");
  assert.equal(config.delegation.responses.parallel_tool_calls, false);
  const tools = config.delegation.responses.tools!;
  assert.equal(tools.length, 2);
  assert.equal(tools[1].type, "function");
  if (tools[1].type === "function")
    assert.deepEqual(tools[1].parameters?.required, ["revision"]);
});

for (const ending of [
  "acknowledgment",
  "timeout",
  "response failure",
] as const) {
  test(`trusted sideband saves once and closes after ${ending}`, async (t) => {
    const directory = mkdtempSync(join(tmpdir(), "fads-live-"));
    t.after(() => rmSync(directory, { recursive: true, force: true }));
    const store = new SessionStore(directory);
    const { session } = store.create("live");
    let writes = 0;
    const intake = new Intake(store, async () => {
      writes++;
      return { id: "remote-123", mode: "live" };
    });
    const queue: unknown[] = [{ type: "open" }];
    let wake: (() => void) | undefined;
    let closed = false;
    const sent: Array<Record<string, any>> = [];
    const push = (event: unknown) => {
      queue.push(event);
      wake?.();
    };
    const socket = {
      send(event: Record<string, any>) {
        sent.push(event);
      },
      close() {
        closed = true;
        wake?.();
      },
      async *[Symbol.asyncIterator]() {
        while (!closed) {
          if (!queue.length)
            await new Promise<void>((resolve) => {
              wake = resolve;
            });
          const item = queue.shift();
          if (item) yield item;
        }
      },
    };
    const client = {
      live: {
        create: async (body: any) => {
          assert.equal(body.session.model, "gpt-live-1");
          assert.equal(body.transport.sdp, "v=0 offer");
          return {
            session: { id: "live_actual_id" },
            transport: { type: "webrtc", sdp: "v=0 answer" },
          };
        },
      },
    };
    const live = new LiveService(store, intake, {
      completionGraceMs: 20,
      completionTimeoutMs: ending === "timeout" ? 60 : 2_000,
      createClient: () => client as unknown as OpenAI,
      createConnection: (_client, id) => {
        assert.equal(id, "live_actual_id");
        return socket as unknown as SidebandWS;
      },
    });
    const result = await live.start(session, "v=0 offer");
    assert.equal(result.sdp, "v=0 answer");
    const event = (message: unknown) => push({ type: "message", message });
    const tick = () => new Promise((resolve) => setTimeout(resolve, 20));
    const tool = (id: string, name: string, args: unknown) => {
      event({
        type: "response.event",
        delegation_id: `delegation-${id}`,
        event: { type: "response.created", response: { id } },
      });
      event({
        type: "response.event",
        delegation_id: `delegation-${id}`,
        event: {
          type: "response.output_item.done",
          item: {
            type: "function_call",
            name,
            arguments: JSON.stringify(args),
            call_id: id,
          },
        },
      });
      event({
        type: "response.event",
        delegation_id: `delegation-${id}`,
        event: { type: "response.completed", response: { id, output: [] } },
      });
    };
    event({ type: "session.started", session: { id: "live_actual_id" } });
    await tick();
    assert.equal(session.status, "active");
    tool("prepare-1", "prepare_draft", {
      kind: "question",
      description: "When will road repairs finish?",
      location: "Oak Road",
      contact: "",
      category: "",
      name: "",
      impact: "",
    });
    await tick();
    const prepared = sent.find((item) => item.type === "response.item.create");
    assert.ok(prepared);
    const content = JSON.parse(prepared.item.output);
    assert.equal(content.revision, 1);
    assert.equal(writes, 0);
    event({
      type: "session.output_transcript.delta",
      event_id: "incomplete-readback",
      delta: "Your road question is ready. Shall I log this?",
      start_ms: 10,
      end_ms: 30,
    });
    event({
      type: "session.input_transcript.delta",
      event_id: "premature-confirmation",
      delta: "Yes, please.",
      start_ms: 40,
      end_ms: 60,
    });
    tool("confirm-incomplete", "confirm_draft", { revision: 1 });
    await tick();
    const recovery = sent.find((item) =>
      item.type === "response.item.create" && item.item.call_id === "confirm-incomplete",
    );
    assert.ok(recovery);
    const recoveryContent = JSON.parse(recovery.item.output);
    assert.equal(writes, 0, "Missing facts must not bypass verbal confirmation");
    assert.equal(recoveryContent.readback, content.readback);
    assert.equal(recoveryContent.revision, 1);
    assert.match(recoveryContent.instruction, /word for word/);
    event({
      type: "session.output_transcript.delta",
      event_id: "readback-1",
      delta: content.readback,
      start_ms: 100,
      end_ms: 500,
    });
    event({
      type: "session.input_transcript.delta",
      event_id: "yes-1",
      delta: "Yes, log it.",
      start_ms: 600,
      end_ms: 800,
    });
    tool("confirm-1", "confirm_draft", { revision: 1 });
    await new Promise((resolve) => setTimeout(resolve, 1600));
    assert.equal(writes, 1);
    assert.equal(session.submission?.id, "remote-123");
    const confirmed = sent.find(
      (item) =>
        item.type === "response.item.create" &&
        item.item.call_id === "confirm-1",
    );
    assert.equal(JSON.parse(confirmed!.item.output).status, "saved");
    assert.equal(
      sent.filter((item) => item.type === "response.create").length,
      3,
    );
    assert.ok(
      sent.some(
        (item) =>
          item.type === "session.commentary.append" &&
          /has been logged/.test(item.content),
      ),
    );
    if (ending === "acknowledgment") {
      assert.equal(
        session.status,
        "active",
        "Do not hang up before saying the saved outcome",
      );
      event({
        type: "session.output_transcript.delta",
        event_id: "goodbye",
        delta:
          "Your request has been logged. A customer service agent will contact you if necessary. Thank you. Goodbye.",
        start_ms: 900,
        end_ms: 1800,
      });
      await new Promise((resolve) => setTimeout(resolve, 60));
      assert.equal(session.status, "ended");
    } else if (ending === "timeout") {
      await new Promise((resolve) => setTimeout(resolve, 80));
      assert.equal(
        session.status,
        "ended",
        "Missing output speech must not leave a billable session open forever",
      );
    } else {
      // A failed delegated response is actionable, even after an earlier record saved.
      event({
        type: "response.event",
        delegation_id: "delegation-failed",
        event: { type: "response.failed", response: { id: "failed" } },
      });
      await tick();
      assert.equal(session.status, "ended");
      assert.match(session.error ?? "", /reasoning service/);
    }
    assert.ok(sent.some((item) => item.type === "session.close"));
    assert.equal(writes, 1);
    assert.equal(session.submission?.id, "remote-123");
    event({ type: "session.closed", usage: { seconds: 10 } });
    await tick();
    assert.equal(session.status, "ended");
    assert.equal(closed, true);
  });
}
