import type { IssueType } from "./domain";

export type WorkflowTaskDefinition = {
  id: string;
  name: string;
  requiredSkill: string;
  requiredEquipment: readonly string[];
  dependsOn: readonly string[];
  estimatedMinutes: number;
};

export type WorkflowDefinition = {
  id: IssueType;
  label: string;
  description: string;
  requiredRoles: readonly { skill: string; count: number }[];
  tasks: readonly WorkflowTaskDefinition[];
  approvedReferences: readonly string[];
};

export type BusyInterval = { start: string; end: string };
export type CrewMember = {
  id: string;
  name: string;
  skills: readonly string[];
  busy: readonly BusyInterval[];
  distanceKm: number;
};
export type EquipmentUnit = {
  id: string;
  catalogKey: string;
  name: string;
  busy: readonly BusyInterval[];
};
export type WorkingWindow = {
  timezone: string;
  dailyStartHour: number;
  dailyEndHour: number;
  horizonHours: number;
};
export type PlanningRequest = {
  incidentId: string;
  workflow: WorkflowDefinition;
  crew: readonly CrewMember[];
  equipment: readonly EquipmentUnit[];
  window: WorkingWindow;
  now: string;
};
export type PlannedTask = {
  taskDefinitionId: string;
  title: string;
  crewMemberId: string;
  crewMemberName: string;
  equipmentIds: readonly string[];
  startAt: string;
  endAt: string;
};
export type ProposedPlan = {
  kind: "plan";
  incidentId: string;
  startAt: string;
  endAt: string;
  tasks: readonly PlannedTask[];
  crewMemberIds: readonly string[];
  equipmentIds: readonly string[];
  rationale: string;
};
export type PlanningBlocker = {
  kind: "blocked";
  incidentId: string;
  code: "missing_skill" | "missing_equipment" | "no_common_window";
  detail: string;
};
export type PlanningResult = ProposedPlan | PlanningBlocker;
