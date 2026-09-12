import { AmbiguousClient } from "@/src/ambiguous/client";
import { EQUIPMENT_CATALOG } from "@/src/catalog";
import type { EquipmentUnit, ProposedPlan } from "@/src/contracts";
import { activeIncidents } from "@/src/db/store";
import {
  renderEventDescription,
  renderIncidentDescription,
  renderWorkflowSubtaskDescription,
  renderWorkPackage,
  type EvidenceVerification,
} from "@/src/orchestration/artifacts";
import { ambiguousConfig } from "@/src/orchestration/config";

type StoredPlan = {
  plan: ProposedPlan;
  subtaskIds: Record<string, string>;
};

const client = new AmbiguousClient(ambiguousConfig());
const resources = await client.listResources();
const equipment: EquipmentUnit[] = resources.map((resource) => ({
  id: resource.id,
  catalogKey: EQUIPMENT_CATALOG.find((item) => item.name === resource.name)?.key ?? "unknown",
  name: resource.name,
  busy: [],
}));

for (const incident of activeIncidents()) {
  if (!incident.ambiguousTaskId || !incident.documentId || !incident.eventId || !incident.planJson) continue;

  const marker = `[FADS:${incident.id}]`;
  const stored = JSON.parse(incident.planJson) as StoredPlan;
  const verification: EvidenceVerification = incident.fallbackUsed
    ? {
        confidence: "unverified",
        summary: "Demo fallback used — vision unavailable; resident selection retained.",
      }
    : {
        confidence: "verified",
        summary: "Image evidence verified against the resident-selected workflow.",
      };

  await client.updateTask(incident.ambiguousTaskId, {
    description: renderIncidentDescription(incident, marker),
  });

  for (const task of stored.plan.tasks) {
    const subtaskId = stored.subtaskIds[task.taskDefinitionId];
    if (!subtaskId) continue;
    await client.updateTask(subtaskId, {
      description: renderWorkflowSubtaskDescription(incident, marker, task, equipment),
    });
  }

  await client.updateDocument(
    incident.documentId,
    renderWorkPackage(incident, verification, stored.plan, equipment),
  );
  await client.updateEvent(incident.eventId, {
    description: renderEventDescription(incident, marker, incident.documentId),
    location: incident.report.address,
  });

  console.log(`Updated linked artifacts for ${incident.id}`);
}
