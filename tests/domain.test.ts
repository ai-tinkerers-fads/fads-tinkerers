import { describe, expect, it } from "vitest";
import { canTransition, toMilestone, type SafeIncidentStatus } from "@/src/contracts";

describe("incident lifecycle", () => {
  it("requires review before returning to assessment", () => {
    expect(canTransition("assessing", "needs_review")).toBe(true);
    expect(canTransition("needs_review", "scheduled")).toBe(false);
    expect(canTransition("needs_review", "assessing")).toBe(true);
  });

  it("projects only customer-safe milestones", () => {
    expect(toMilestone("awaiting_approval")).toBe("crew_proposed");
    const keys: Array<keyof SafeIncidentStatus> = ["incidentId", "status", "milestone", "issueLabel", "address", "progressMessage", "queuePosition", "estimatedResolutionAt", "fallbackUsed", "updatedAt"];
    expect(keys).not.toContain("residentEmail");
    expect(keys).not.toContain("crewMemberName");
  });
});
