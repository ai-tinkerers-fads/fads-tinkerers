import type { WorkflowDefinition } from "@/src/contracts";

const FHWA_WORK_ZONES = "https://highways.dot.gov/safety/proven-safety-countermeasures/work-zones";
const CALTRANS_MAINTENANCE = "https://dot.ca.gov/programs/maintenance";

export const WORKFLOWS: Readonly<Record<WorkflowDefinition["id"], WorkflowDefinition>> = {
  fallen_branches: {
    id: "fallen_branches",
    label: "Remove branches from road",
    description: "Secure the road, cut and load branches, transport debris, then verify clearance.",
    requiredRoles: [
      { skill: "site_safety", count: 1 },
      { skill: "chainsaw", count: 1 },
      { skill: "loader", count: 1 },
      { skill: "transport", count: 1 },
    ],
    approvedReferences: [FHWA_WORK_ZONES, CALTRANS_MAINTENANCE],
    tasks: [
      { id: "secure", name: "Secure the site", requiredSkill: "site_safety", requiredEquipment: ["traffic_control_kit"], dependsOn: [], estimatedMinutes: 20 },
      { id: "cut", name: "Cut and remove branches", requiredSkill: "chainsaw", requiredEquipment: ["chainsaw_kit"], dependsOn: ["secure"], estimatedMinutes: 45 },
      { id: "load", name: "Load material", requiredSkill: "loader", requiredEquipment: ["loader"], dependsOn: ["cut"], estimatedMinutes: 30 },
      { id: "transport", name: "Transport and dispose", requiredSkill: "transport", requiredEquipment: ["transport_truck"], dependsOn: ["load"], estimatedMinutes: 45 },
      { id: "verify", name: "Verify road is clear", requiredSkill: "site_safety", requiredEquipment: ["traffic_control_kit"], dependsOn: ["transport"], estimatedMinutes: 15 },
    ],
  },
  pothole: {
    id: "pothole",
    label: "Fix pothole",
    description: "Secure the road, prepare and repair the pothole, compact it, then verify reopening.",
    requiredRoles: [{ skill: "site_safety", count: 1 }, { skill: "pothole_repair", count: 1 }],
    approvedReferences: [FHWA_WORK_ZONES, CALTRANS_MAINTENANCE],
    tasks: [
      { id: "secure", name: "Secure the site", requiredSkill: "site_safety", requiredEquipment: ["traffic_control_kit"], dependsOn: [], estimatedMinutes: 20 },
      { id: "prepare", name: "Prepare the pothole", requiredSkill: "pothole_repair", requiredEquipment: ["pothole_repair_kit"], dependsOn: ["secure"], estimatedMinutes: 25 },
      { id: "repair", name: "Apply repair material", requiredSkill: "pothole_repair", requiredEquipment: ["pothole_repair_kit"], dependsOn: ["prepare"], estimatedMinutes: 35 },
      { id: "compact", name: "Compact the repair", requiredSkill: "pothole_repair", requiredEquipment: ["compactor"], dependsOn: ["repair"], estimatedMinutes: 20 },
      { id: "verify", name: "Verify and reopen", requiredSkill: "site_safety", requiredEquipment: ["traffic_control_kit"], dependsOn: ["compact"], estimatedMinutes: 15 },
    ],
  },
  vehicle_or_debris: {
    id: "vehicle_or_debris",
    label: "Remove car or debris from road",
    description: "Secure the road, recover the obstruction, transport it, then verify clearance.",
    requiredRoles: [
      { skill: "site_safety", count: 1 },
      { skill: "recovery", count: 1 },
      { skill: "transport", count: 1 },
    ],
    approvedReferences: [FHWA_WORK_ZONES, CALTRANS_MAINTENANCE],
    tasks: [
      { id: "secure", name: "Secure the site", requiredSkill: "site_safety", requiredEquipment: ["traffic_control_kit"], dependsOn: [], estimatedMinutes: 20 },
      { id: "recover", name: "Recover or remove obstruction", requiredSkill: "recovery", requiredEquipment: ["recovery_vehicle"], dependsOn: ["secure"], estimatedMinutes: 45 },
      { id: "transport", name: "Transport obstruction", requiredSkill: "transport", requiredEquipment: ["transport_truck"], dependsOn: ["recover"], estimatedMinutes: 45 },
      { id: "verify", name: "Verify road is clear", requiredSkill: "site_safety", requiredEquipment: ["traffic_control_kit"], dependsOn: ["transport"], estimatedMinutes: 15 },
    ],
  },
};
