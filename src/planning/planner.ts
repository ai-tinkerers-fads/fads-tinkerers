import type {
  BusyInterval,
  EquipmentUnit,
  PlannedTask,
  PlanningRequest,
  PlanningResult,
} from "@/src/contracts";

const SLOT_MS = 15 * 60 * 1000;

function overlaps(start: number, end: number, intervals: readonly BusyInterval[]): boolean {
  return intervals.some((interval) => start < Date.parse(interval.end) && end > Date.parse(interval.start));
}

function dayWindow(candidate: Date, request: PlanningRequest): { start: number; end: number } {
  const start = new Date(candidate);
  start.setHours(request.window.dailyStartHour, 0, 0, 0);
  const end = new Date(candidate);
  end.setHours(request.window.dailyEndHour, 0, 0, 0);
  return { start: start.getTime(), end: end.getTime() };
}

function nextSlot(time: number): number {
  return Math.ceil(time / SLOT_MS) * SLOT_MS;
}

export function planIncident(request: PlanningRequest): PlanningResult {
  for (const role of request.workflow.requiredRoles) {
    const eligible = request.crew.filter((member) => member.skills.includes(role.skill));
    if (eligible.length < role.count) {
      return {
        kind: "blocked",
        incidentId: request.incidentId,
        code: "missing_skill",
        detail: `Need ${role.count} crew member(s) with ${role.skill}; found ${eligible.length}.`,
      };
    }
  }

  const equipmentByKey = new Map<string, EquipmentUnit[]>();
  for (const unit of request.equipment) {
    const group = equipmentByKey.get(unit.catalogKey) ?? [];
    group.push(unit);
    equipmentByKey.set(unit.catalogKey, group);
  }
  for (const task of request.workflow.tasks) {
    for (const key of task.requiredEquipment) {
      if ((equipmentByKey.get(key)?.length ?? 0) === 0) {
        return {
          kind: "blocked",
          incidentId: request.incidentId,
          code: "missing_equipment",
          detail: `No ${key.replaceAll("_", " ")} is available in the equipment catalog.`,
        };
      }
    }
  }

  const horizonEnd = Date.parse(request.now) + request.window.horizonHours * 60 * 60 * 1000;
  let candidate = nextSlot(Date.parse(request.now));
  while (candidate < horizonEnd) {
    const window = dayWindow(new Date(candidate), request);
    if (candidate < window.start) candidate = window.start;
    if (candidate >= window.end) {
      candidate = nextSlot(window.start + 24 * 60 * 60 * 1000);
      continue;
    }

    const scheduled: PlannedTask[] = [];
    const localCrewBusy = new Map<string, BusyInterval[]>();
    const localEquipmentBusy = new Map<string, BusyInterval[]>();
    let cursor = candidate;
    let feasible = true;

    for (const definition of request.workflow.tasks) {
      const end = cursor + definition.estimatedMinutes * 60 * 1000;
      if (end > window.end) {
        feasible = false;
        break;
      }
      const eligibleCrew = request.crew
        .filter((member) => member.skills.includes(definition.requiredSkill))
        .sort((a, b) => a.distanceKm - b.distanceKm || a.name.localeCompare(b.name));
      const member = eligibleCrew.find((person) => {
        const combined = [...person.busy, ...(localCrewBusy.get(person.id) ?? [])];
        return !overlaps(cursor, end, combined);
      });
      if (!member) {
        feasible = false;
        break;
      }

      const equipmentIds: string[] = [];
      for (const key of definition.requiredEquipment) {
        const unit = equipmentByKey.get(key)?.find((item) => {
          const combined = [...item.busy, ...(localEquipmentBusy.get(item.id) ?? [])];
          return !equipmentIds.includes(item.id) && !overlaps(cursor, end, combined);
        });
        if (!unit) {
          feasible = false;
          break;
        }
        equipmentIds.push(unit.id);
      }
      if (!feasible) break;

      const interval = { start: new Date(cursor).toISOString(), end: new Date(end).toISOString() };
      localCrewBusy.set(member.id, [...(localCrewBusy.get(member.id) ?? []), interval]);
      for (const id of equipmentIds) {
        localEquipmentBusy.set(id, [...(localEquipmentBusy.get(id) ?? []), interval]);
      }
      scheduled.push({
        taskDefinitionId: definition.id,
        title: definition.name,
        crewMemberId: member.id,
        crewMemberName: member.name,
        equipmentIds,
        startAt: interval.start,
        endAt: interval.end,
      });
      cursor = end;
    }

    if (feasible && scheduled.length === request.workflow.tasks.length) {
      const crewMemberIds = [...new Set(scheduled.map((task) => task.crewMemberId))];
      const equipmentIds = [...new Set(scheduled.flatMap((task) => task.equipmentIds))];
      return {
        kind: "plan",
        incidentId: request.incidentId,
        startAt: scheduled[0]!.startAt,
        endAt: scheduled.at(-1)!.endAt,
        tasks: scheduled,
        crewMemberIds,
        equipmentIds,
        rationale: `Earliest complete sequence within ${request.window.horizonHours} hours; matched required skills, free/busy calendars, exclusive equipment, and dependency order. Distance broke equivalent crew ties.`,
      };
    }
    candidate += SLOT_MS;
  }

  return {
    kind: "blocked",
    incidentId: request.incidentId,
    code: "no_common_window",
    detail: `No complete crew and equipment sequence is feasible in the next ${request.window.horizonHours} hours.`,
  };
}
