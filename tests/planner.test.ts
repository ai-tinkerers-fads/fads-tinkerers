import { describe, expect, it } from "vitest";
import { CREW, EQUIPMENT_CATALOG, WORKFLOWS } from "@/src/catalog";
import type { EquipmentUnit, PlanningRequest } from "@/src/contracts";
import { planIncident } from "@/src/planning/planner";

function request(): PlanningRequest {
  const equipment: EquipmentUnit[] = EQUIPMENT_CATALOG.map((item) => ({ id: `resource-${item.key}`, catalogKey: item.key, name: item.name, busy: [] }));
  return {
    incidentId: "INC-TEST",
    workflow: WORKFLOWS.fallen_branches,
    crew: CREW.map((member) => ({ ...member, busy: [] })),
    equipment,
    window: { timezone: "America/Los_Angeles", dailyStartHour: 8, dailyEndHour: 18, horizonHours: 48 },
    now: "2026-09-14T08:00:00-07:00",
  };
}

describe("planIncident", () => {
  it("returns the same dependency-ordered plan for the same inputs", () => {
    const first = planIncident(request());
    const second = planIncident(request());
    expect(second).toEqual(first);
    expect(first.kind).toBe("plan");
    if (first.kind === "plan") expect(first.tasks.map((task) => task.taskDefinitionId)).toEqual(["secure", "cut", "load", "transport", "verify"]);
  });

  it("reports the exact missing resource", () => {
    const input = request();
    const result = planIncident({ ...input, equipment: input.equipment.filter((item) => item.catalogKey !== "loader") });
    expect(result).toMatchObject({ kind: "blocked", code: "missing_equipment" });
    if (result.kind === "blocked") expect(result.detail).toContain("loader");
  });

  it("moves the plan when crew calendars conflict", () => {
    const input = request();
    const result = planIncident({
      ...input,
      crew: input.crew.map((member) => member.skills.includes("chainsaw") ? { ...member, busy: [{ start: "2026-09-14T08:00:00-07:00", end: "2026-09-14T12:00:00-07:00" }] } : member),
    });
    expect(result.kind).toBe("plan");
    if (result.kind === "plan") expect(Date.parse(result.startAt)).toBeGreaterThanOrEqual(Date.parse("2026-09-14T11:15:00-07:00"));
  });
});
