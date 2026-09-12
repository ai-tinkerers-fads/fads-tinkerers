import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { AmbiguousClient } from "@/src/ambiguous/client";
import { CREW, EQUIPMENT_CATALOG, WORKFLOWS } from "@/src/catalog";
import type { ConfidenceBand, EquipmentUnit, ProposedPlan } from "@/src/contracts";
import { activeIncidents, incidentById, updateIncident, type StoredIncident } from "@/src/db/store";
import { planIncident } from "@/src/planning/planner";
import { ambiguousConfig } from "./config";

const execFileAsync = promisify(execFile);

type Verification = {
  confidence: ConfidenceBand;
  observedIssue: string;
  matches: boolean;
  summary: string;
  fallbackUsed: boolean;
};

type StoredPlan = {
  plan: ProposedPlan;
  subtaskIds: Record<string, string>;
  approvalTaskId: string;
  eventId: string;
  holdExpiresAt: string;
};

async function verifyEvidence(incident: StoredIncident): Promise<Verification> {
  const prompt = `Inspect the road-damage image at ${incident.imagePath}. The resident selected ${incident.report.issueType}. Reply with JSON only: {"observedIssue":"fallen_branches|pothole|vehicle_or_debris|unclear","matches":boolean,"confidence":"verified|review","summary":"one factual sentence"}. Do not suggest procedures.`;
  try {
    const { stdout } = await execFileAsync("openclaw", [
      "agent", "exec", "--cwd", process.cwd(),
      "--model", "bedrock-proxy/global.anthropic.claude-haiku-4-5-20251001-v1:0",
      "--thinking", "off", "--timeout", "45", "--json", prompt,
    ], { timeout: 55_000, maxBuffer: 2_000_000 });
    const envelope = JSON.parse(stdout) as Record<string, unknown>;
    const text = String(envelope.output ?? envelope.result ?? envelope.message ?? stdout);
    const match = text.match(/\{[^{}]*"observedIssue"[^{}]*\}/s);
    if (!match) throw new Error("No structured vision result");
    return { ...(JSON.parse(match[0]) as Omit<Verification, "fallbackUsed">), fallbackUsed: false };
  } catch {
    return {
      confidence: "unverified",
      observedIssue: "unavailable",
      matches: true,
      summary: "Demo fallback used — vision unavailable; resident selection retained.",
      fallbackUsed: true,
    };
  }
}

function workPackage(incident: StoredIncident, verification: Verification, plan: ProposedPlan): string {
  const workflow = WORKFLOWS[incident.report.issueType];
  const checklist = plan.tasks.map((task, index) =>
    `${index + 1}. **${task.title}** — ${task.crewMemberName} — ${task.startAt} to ${task.endAt}\n   - Equipment: ${task.equipmentIds.join(", ") || "none"}`,
  ).join("\n");
  return `# Work Package — ${incident.id}

## Report
- **Location:** ${incident.report.address} (${incident.report.latitude}, ${incident.report.longitude})
- **Resident-selected issue:** ${workflow.label}
- **Evidence:** ${verification.summary}
- **Confidence:** ${verification.confidence}

## Proposed schedule
- **Start:** ${plan.startAt}
- **Expected completion:** ${plan.endAt}
- **Status:** Tentative — dispatcher approval required

## Crew and checklist
${checklist}

## Decision rationale
${plan.rationale}

## Approved references
${workflow.approvedReferences.map((url) => `- ${url}`).join("\n")}

> Demo plan only. A dispatcher must approve before field work.`;
}

async function writeProgress(client: AmbiguousClient, incident: StoredIncident, message: string): Promise<void> {
  if (!incident.ambiguousTaskId) return;
  if (incident.progressCommentId) {
    await client.updateComment(incident.ambiguousTaskId, incident.progressCommentId, message);
  } else {
    const comment = await client.createComment(incident.ambiguousTaskId, message);
    updateIncident(incident.id, { progressCommentId: comment.id });
  }
  updateIncident(incident.id, { progressMessage: message });
}

export async function processIncident(id: string): Promise<void> {
  const config = ambiguousConfig();
  const client = new AmbiguousClient(config);
  let incident = incidentById(id);
  if (!incident) return;
  try {
    const marker = `[FADS:${incident.id}]`;
    let fileId = incident.fileId;
    if (!fileId) {
      const file = await client.uploadFile(incident.imagePath, `${incident.id}-${incident.report.imageName}`, incident.report.imageMimeType);
      fileId = file.id;
      updateIncident(id, { fileId });
    }

    let taskId = incident.ambiguousTaskId;
    if (!taskId) {
      const existing = await client.findTaskByMarker(marker);
      const task = existing ?? await client.createTask({
        title: `${incident.id} · ${WORKFLOWS[incident.report.issueType].label}`,
        description: `${marker}\n\n**Demo resident:** ${incident.report.residentName}\n**Email:** ${incident.report.residentEmail}\n**Phone:** ${incident.report.residentPhone}\n**Location:** ${incident.report.address}\n**Coordinates:** ${incident.report.latitude}, ${incident.report.longitude}\n\n${incident.report.description ?? "No additional description."}`,
        projectId: config.projectId,
        assigneeId: "e291aee4-3f6b-4f34-9860-6d9e7e26c802",
        statusId: config.statusIds?.reported,
        priority: "high",
      });
      taskId = task.id;
      updateIncident(id, { ambiguousTaskId: taskId });
      await client.attachFile(taskId, fileId);
    }

    incident = incidentById(id)!;
    await writeProgress(client, incident, "Assessing image evidence against the resident-selected workflow.");
    const verification = await verifyEvidence(incident);
    updateIncident(id, { fallbackUsed: verification.fallbackUsed });
    if (!verification.matches && verification.confidence === "verified") {
      await client.updateTask(taskId, { task_status_id: config.statusIds?.needs_review, status: "blocked" });
      await writeProgress(client, incidentById(id)!, `Needs dispatcher review — image evidence strongly conflicts with ${WORKFLOWS[incident.report.issueType].label}.`);
      updateIncident(id, { status: "needs_review", leaseOwner: null, leaseUntil: null });
      return;
    }

    await writeProgress(client, incidentById(id)!, "Checking crew calendars and exclusive equipment for the earliest safe sequence.");
    const start = new Date().toISOString();
    const end = new Date(Date.now() + 48 * 60 * 60_000).toISOString();
    const availability = await client.getAvailability(CREW.map((member) => member.id), start, end);
    const resources = await client.listResources();
    const equipment: EquipmentUnit[] = [];
    for (const catalog of EQUIPMENT_CATALOG) {
      const resource = resources.find((item) => item.name === catalog.name);
      if (resource) {
        equipment.push({ id: resource.id, catalogKey: catalog.key, name: catalog.name, busy: await client.getResourceAvailability(resource.id, start, end) });
      }
    }
    const result = planIncident({
      incidentId: id,
      workflow: WORKFLOWS[incident.report.issueType],
      crew: CREW.map((member) => ({ ...member, busy: availability[member.id] ?? [] })),
      equipment,
      window: { timezone: "America/Los_Angeles", dailyStartHour: 8, dailyEndHour: 18, horizonHours: 48 },
      now: start,
    });
    if (result.kind === "blocked") {
      await writeProgress(client, incidentById(id)!, `Blocked — ${result.detail}`);
      await client.updateTask(taskId, { status: "blocked", task_status_id: config.statusIds?.blocked });
      updateIncident(id, { status: "blocked", leaseOwner: null, leaseUntil: null });
      return;
    }

    const document = await client.createDocument(`${incident.id} Work Package`, workPackage(incident, verification, result));
    updateIncident(id, { documentId: document.id });
    const subtaskIds: Record<string, string> = {};
    for (const [index, item] of result.tasks.entries()) {
      const subtask = await client.createSubtask(taskId, {
        title: item.title,
        description: `${marker}\nPlanned: ${item.startAt} – ${item.endAt}\nProposed crew: ${item.crewMemberName}\nEquipment: ${item.equipmentIds.join(", ")}`,
        estimatedMinutes: Math.round((Date.parse(item.endAt) - Date.parse(item.startAt)) / 60_000),
        sortOrder: index,
      });
      subtaskIds[item.taskDefinitionId] = subtask.id;
    }
    const approval = await client.createSubtask(taskId, {
      title: "Dispatcher approval required",
      description: `${marker}\nReview Work Package @{document:${document.id}} and tentative schedule. Complete this subtask to approve. Only workspace admins may approve.`,
      statusId: config.statusIds?.awaiting_approval,
      sortOrder: 999,
    });
    if (!config.calendarId) throw new Error("FADS Operations calendar is not configured");
    const event = await client.createEvent(config.calendarId, {
      title: `Tentative · ${incident.id} · ${WORKFLOWS[incident.report.issueType].label}`,
      startAt: result.startAt,
      endAt: result.endAt,
      description: `${marker}\nWork Package: https://app.ambiguous.ai/docs/${document.id}\nAwaiting dispatcher approval.`,
      location: incident.report.address,
      attendeeIds: result.crewMemberIds,
      resourceIds: result.equipmentIds,
    });
    const stored: StoredPlan = {
      plan: result,
      subtaskIds,
      approvalTaskId: approval.id,
      eventId: event.id,
      holdExpiresAt: new Date(Date.now() + 15 * 60_000).toISOString(),
    };
    updateIncident(id, {
      status: "awaiting_approval",
      approvalTaskId: approval.id,
      eventId: event.id,
      planJson: JSON.stringify(stored),
      estimatedResolutionAt: result.endAt,
      leaseOwner: null,
      leaseUntil: null,
      progressMessage: "Crew and equipment proposed; awaiting dispatcher approval.",
    });
    await client.updateTask(taskId, { task_status_id: config.statusIds?.awaiting_approval, status: "in_progress" });
    await writeProgress(client, incidentById(id)!, "Crew and equipment proposed; awaiting an admin to complete the approval subtask.");
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    updateIncident(id, { status: "reported", progressMessage: `Worker error; safely requeued — ${message}`, leaseOwner: null, leaseUntil: null });
  }
}

export async function reconcileApprovals(): Promise<void> {
  const config = ambiguousConfig();
  const client = new AmbiguousClient(config);
  const pending = activeIncidents().filter((item) => item.status === "awaiting_approval" && item.planJson);
  for (const incident of pending) {
    const stored = JSON.parse(incident.planJson!) as StoredPlan;
    const approval = await client.getTask(stored.approvalTaskId);
    if (approval.status !== "done") continue;
    const activity = await client.listActivity(stored.approvalTaskId);
    const completion = activity.find((row) => row.action === "status_changed");
    if (!completion?.userId || !await client.userIsAdmin(completion.userId)) {
      await client.updateTask(stored.approvalTaskId, { status: "todo" });
      await client.createComment(stored.approvalTaskId, "Approval rejected: only a workspace admin may approve this plan.");
      continue;
    }
    if (Date.parse(stored.holdExpiresAt) < Date.now()) {
      await client.createComment(incident.ambiguousTaskId!, "Tentative hold expired before approval; recomputing availability.");
      updateIncident(incident.id, { status: "reported", progressMessage: "Approval arrived after hold expiry; recomputing plan.", leaseOwner: null, leaseUntil: null });
      continue;
    }
    for (const item of stored.plan.tasks) {
      await client.updateTask(stored.subtaskIds[item.taskDefinitionId]!, { assignee_id: item.crewMemberId });
    }
    await client.updateEvent(stored.eventId, { status: "confirmed", title: `Scheduled · ${incident.id} · ${WORKFLOWS[incident.report.issueType].label}` });
    await client.updateTask(incident.ambiguousTaskId!, { task_status_id: config.statusIds?.scheduled, status: "in_progress" });
    updateIncident(incident.id, { status: "scheduled", progressMessage: "Dispatcher approved the plan; crew and equipment are scheduled." });
  }
}
