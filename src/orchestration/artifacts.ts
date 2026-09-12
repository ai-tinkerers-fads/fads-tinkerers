import type { EquipmentUnit, PlannedTask, ProposedPlan } from "@/src/contracts";
import type { StoredIncident } from "@/src/db/store";
import { WORKFLOWS } from "@/src/catalog";

export type EvidenceVerification = {
  confidence: "verified" | "review" | "unverified";
  summary: string;
};

export function googleMapsUrl(latitude: number, longitude: number): string {
  const query = encodeURIComponent(`${latitude},${longitude}`);
  return `https://www.google.com/maps/search/?api=1&query=${query}`;
}

export function formatLocationLink(incident: StoredIncident): string {
  const { address, latitude, longitude } = incident.report;
  return `[${address} (${latitude}, ${longitude})](${googleMapsUrl(latitude, longitude)})`;
}

export function equipmentResourceUrl(id: string): string {
  return `https://app.ambiguous.ai/calendar/resources/${encodeURIComponent(id)}`;
}

export function formatEquipmentLinks(ids: readonly string[], equipment: readonly Pick<EquipmentUnit, "id" | "name">[]): string {
  if (ids.length === 0) return "None";
  return ids.map((id) => {
    const name = equipment.find((item) => item.id === id)?.name ?? "Equipment";
    return `${name} ([${id}](${equipmentResourceUrl(id)}))`;
  }).join(", ");
}

export function renderIncidentDescription(incident: StoredIncident, marker: string): string {
  return `${marker}

**Demo resident:** ${incident.report.residentName}
**Email:** ${incident.report.residentEmail}
**Phone:** ${incident.report.residentPhone}
**Location:** ${formatLocationLink(incident)}

${incident.report.description ?? "No additional description."}`;
}

export function renderWorkflowSubtaskDescription(
  incident: StoredIncident,
  marker: string,
  task: PlannedTask,
  equipment: readonly Pick<EquipmentUnit, "id" | "name">[],
): string {
  return `${marker}
**Location:** ${formatLocationLink(incident)}
**Planned:** ${task.startAt} – ${task.endAt}
**Proposed crew:** ${task.crewMemberName}
**Equipment:** ${formatEquipmentLinks(task.equipmentIds, equipment)}`;
}

export function renderWorkPackage(
  incident: StoredIncident,
  verification: EvidenceVerification,
  plan: ProposedPlan,
  equipment: readonly Pick<EquipmentUnit, "id" | "name">[],
): string {
  const workflow = WORKFLOWS[incident.report.issueType];
  const checklist = plan.tasks.map((task, index) =>
    `${index + 1}. **${task.title}** — ${task.crewMemberName} — ${task.startAt} to ${task.endAt}\n   - **Equipment:** ${formatEquipmentLinks(task.equipmentIds, equipment)}`,
  ).join("\n");

  return `# Work Package — ${incident.id}

## Report
- **Location:** ${formatLocationLink(incident)}
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

export function renderEventDescription(incident: StoredIncident, marker: string, documentId: string): string {
  return `${marker}
Work Package: https://app.ambiguous.ai/docs/${documentId}
Location: ${googleMapsUrl(incident.report.latitude, incident.report.longitude)}
Awaiting dispatcher approval.`;
}
