import { Injectable } from "@nestjs/common";

export interface ComplaintDraft {
  kind: "complaint" | "question";
  category?: string;
  description: string;
  location: string;
  contact?: string;
  name?: string;
  impact?: string;
}

export interface TaskRecord {
  id: string;
  url?: string;
  mode: "live" | "demo";
}

export class AdapterError extends Error {
  constructor(
    message: string,
    public readonly outcome: "rejected" | "unknown",
  ) {
    super(message);
    this.name = "AdapterError";
  }
}

/** Contract verified against https://app.ambiguous.ai/api/openapi.json.
 * Confirmation and durable duplicate protection belong to the intake service.
 * This adapter never retries a write or falls back from live to demo.
 */
@Injectable()
export class AmbiguousService {
  async createTask(
    draft: ComplaintDraft,
    submissionId: string,
  ): Promise<TaskRecord> {
    if (process.env.AMBIGUOUS_MODE === "demo") {
      return { id: `demo-${submissionId}`, mode: "demo" };
    }
    const token = process.env.AMBIGUOUS_API_KEY;
    if (!token)
      throw new AdapterError(
        "Ambiguous.ai API key is not configured.",
        "rejected",
      );
    const body = {
      title:
        `Road ${draft.kind}: ${draft.category || "general"} — ${draft.location}`.slice(
          0,
          255,
        ),
      description: [
        `Customer ${draft.kind} received through voice intake.`,
        `Intake reference: ${submissionId}`,
        "",
        `Location: ${draft.location}`,
        `Category: ${draft.category || "Not specified"}`,
        `Reported issue or question: ${draft.description}`,
        `Reported impact: ${draft.impact || "Not provided"}`,
        `Customer name: ${draft.name || "Not provided"}`,
        `Contact details: ${draft.contact || "Not provided"}`,
        "",
        "Customer verbally confirmed this record. Contact the customer if necessary.",
      ].join("\n"),
      ...(process.env.AMBIGUOUS_ASSIGNEE_ID
        ? { assignee_id: process.env.AMBIGUOUS_ASSIGNEE_ID }
        : {}),
    };
    // Do not set priority: Ambiguous auto-sets an SLA due date when it is supplied.
    // Keep the origin fixed so a misconfigured URL cannot receive the API token.
    let response: Response;
    try {
      response = await fetch("https://app.ambiguous.ai/api/tasks", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
          "API-Version": "1",
        },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(15_000),
        redirect: "error",
      });
    } catch {
      throw new AdapterError(
        "Record creation outcome is unknown. Check Ambiguous.ai using the intake reference before trying again.",
        "unknown",
      );
    }
    if (!response.ok) {
      // Only documented pre-write rejections are safe to describe as failed.
      const definiteRejection = [400, 401, 403, 404, 422, 429].includes(
        response.status,
      );
      throw new AdapterError(
        definiteRejection
          ? `Ambiguous.ai rejected record creation (HTTP ${response.status}).`
          : "Record creation outcome is unknown. Check Ambiguous.ai before trying again.",
        definiteRejection ? "rejected" : "unknown",
      );
    }
    try {
      const data: unknown = await response.json();
      const id = (data as { task?: { id?: unknown } })?.task?.id;
      if (typeof id !== "string" || !id.trim())
        throw new Error("Missing task ID");
      return {
        id,
        url: `https://app.ambiguous.ai/tasks/${encodeURIComponent(id)}`,
        mode: "live",
      };
    } catch {
      throw new AdapterError(
        "Ambiguous.ai returned an unreadable creation result. Check the intake reference before trying again.",
        "unknown",
      );
    }
  }
}
