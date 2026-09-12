export const ISSUE_TYPES = ["fallen_branches", "pothole", "vehicle_or_debris"] as const;
export type IssueType = (typeof ISSUE_TYPES)[number];

export const INCIDENT_STATUSES = [
  "reported",
  "assessing",
  "needs_review",
  "awaiting_approval",
  "scheduled",
  "in_progress",
  "resolved",
  "blocked",
  "cancelled",
] as const;
export type IncidentStatus = (typeof INCIDENT_STATUSES)[number];

export type ConfidenceBand = "verified" | "review" | "unverified";

export type ResidentReportInput = {
  residentName: string;
  residentEmail: string;
  residentPhone: string;
  issueType: IssueType;
  address: string;
  latitude: number;
  longitude: number;
  description?: string;
  imageName: string;
  imageMimeType: string;
};

export type ReportAccepted = {
  incidentId: string;
  trackingToken: string;
  statusUrl: string;
};

export type SafeIncidentStatus = {
  incidentId: string;
  status: IncidentStatus;
  milestone: "received" | "under_review" | "crew_proposed" | "scheduled" | "work_underway" | "needs_information" | "resolved";
  issueLabel: string;
  address: string;
  progressMessage: string;
  queuePosition: number | null;
  estimatedResolutionAt: string | null;
  fallbackUsed: boolean;
  updatedAt: string;
};

export const LIFECYCLE: Readonly<Record<IncidentStatus, readonly IncidentStatus[]>> = {
  reported: ["assessing", "cancelled"],
  assessing: ["needs_review", "awaiting_approval", "blocked", "cancelled"],
  needs_review: ["assessing", "cancelled"],
  awaiting_approval: ["scheduled", "assessing", "blocked", "cancelled"],
  scheduled: ["in_progress", "assessing", "cancelled"],
  in_progress: ["resolved", "blocked", "cancelled"],
  resolved: [],
  blocked: ["assessing", "cancelled"],
  cancelled: [],
};

export function canTransition(from: IncidentStatus, to: IncidentStatus): boolean {
  return LIFECYCLE[from].includes(to);
}

export function toMilestone(status: IncidentStatus): SafeIncidentStatus["milestone"] {
  if (status === "reported") return "received";
  if (status === "assessing") return "under_review";
  if (status === "awaiting_approval") return "crew_proposed";
  if (status === "scheduled") return "scheduled";
  if (status === "in_progress") return "work_underway";
  if (status === "resolved") return "resolved";
  return "needs_information";
}
