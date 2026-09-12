# Operations model

## System roles

| Component | Role |
| --- | --- |
| Resident web app | Accepts photo, location, and optional issue description; displays status and ETA. |
| Incident service | Stores reports, status, evidence, chosen workflow, work plan, and updates. |
| Agent coordinator | Classifies incident, selects a predefined workflow, finds a qualified available crew, calculates an estimate, and explains its choices. |
| Dispatcher workspace | Lets staff inspect, override, and track incident plans. |
| Field workboard | Shows each employee their assigned tasks, location, dependencies, and completion controls. |

## Core contracts

```ts
type Incident = {
  id: string;
  status: "reported" | "assessed" | "assigned" | "in_progress" | "resolved";
  location: { address?: string; latitude: number; longitude: number };
  report: { description?: string; imageUrl?: string; reportedAt: string };
  classification?: "fallen_branches" | "pothole" | "vehicle_or_debris";
  workflowId?: string;
  estimatedResolutionAt?: string;
  rationale?: string;
};

type Employee = {
  id: string;
  name: string;
  skills: string[]; // e.g. chainsaw, loader, pothole_repair, transport
  availability: Array<{ start: string; end: string }>;
  equipmentAccess?: string[];
};

type Workflow = {
  id: string;
  incidentType: Incident["classification"];
  requiredRoles: Array<{ skill: string; count: number }>;
  tasks: Array<{
    id: string;
    name: string;
    requiredSkill?: string;
    dependsOn?: string[];
    estimatedMinutes: number;
  }>;
};

type WorkAssignment = {
  incidentId: string;
  taskId: string;
  employeeId: string;
  status: "pending" | "ready" | "in_progress" | "complete";
};
```

## Workflow definitions

| Workflow | Required capabilities | Core task sequence |
| --- | --- | --- |
| Remove branches | site safety, chainsaw, loader, transport/disposal | Secure → cut → load → transport → verify clear |
| Fix pothole | site safety, pothole repair, materials/vehicle | Secure → prepare → repair → verify/reopen |
| Remove vehicle/debris | site safety, recovery/removal, transport | Secure → recover/remove → transport → verify clear |

## Assignment policy for the prototype

1. Match each workflow role to an employee with the required skill.
2. Exclude employees unavailable during the task window.
3. Verify necessary equipment access.
4. Prefer a crew whose availability allows the earliest completed dependent
   sequence; use distance only as a simple tie-breaker if modeled.
5. Present the decision rationale and allow dispatcher override.

## Safety boundaries

- The demo uses simulated people, equipment, maps, and notifications.
- The agent may only select from approved workflow data.
- A human can override classification, workflow, assignment, and ETA.
- Never describe the demo as a real emergency-response or public-safety system.
