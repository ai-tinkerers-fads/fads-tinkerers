# Incident reports and crew profiles

## Resident report: minimum viable form

Make location mandatory. Require at least one of typed text, image, or voice
note. Do not ask residents to classify the incident—the agent should do that.

| Field | Required | Purpose |
| --- | --- | --- |
| Location pin | Yes | Latitude/longitude, plus resolved address if available. |
| Typed description | No | The resident's own description of the issue. |
| Photo | No | Visual evidence for classification and dispatcher review. |
| Voice note | No | Spoken description; transcribed before dispatch. |
| Can traffic pass? | Yes | Simple impact signal: `yes`, `partially`, or `no`. |
| Contact preference | No | Demo-only acknowledgement/status channel if desired. |

The form should allow any useful combination: a voice note and map pin is
valid; an image, text, and map pin is also valid.

## Canonical report contract

```ts
type RoadIncidentReport = {
  id: string;
  submittedAt: string;
  reporter: {
    displayName?: string;
    contact?: string; // optional; omit from agent prompt unless needed
  };
  location: {
    latitude: number;
    longitude: number;
    address?: string;
    landmark?: string;
  };
  trafficPassability: "yes" | "partially" | "no";
  inputs: {
    text?: { value: string };
    image?: { fileUrl: string; mimeType: string };
    voice?: { fileUrl: string; mimeType: string; transcript?: string };
  };
  status: "reported" | "awaiting_dispatch" | "assigned" | "in_progress" | "resolved";
};
```

Keep the original image/audio reference. A transcript or visual description is
derived evidence, not a replacement for the original input.

## Channel message for OpenClaw

When the resident submits a report, post one compact message to the channel
OpenClaw already monitors. Put large assets in Ambiguous Drive and include
their links/references rather than binary content.

```text
NEW ROAD INCIDENT — INC-104
Status: awaiting_dispatch
Location: Pine Street & 5th Ave (47.6097, -122.3331)
Traffic passability: no
Resident text: "Traffic cannot get through."
Voice transcript: "Large branches are across both lanes."
Image evidence: <Drive link or file ID>

Dispatch required: classify, choose an approved workflow, assign crew,
create tasks, and post ETA.
```

## OpenClaw dispatch response contract

Ask OpenClaw to reply with this exact structure before it creates tasks. It
keeps its output easy for the dashboard and humans to check.

```text
DISPATCH PLAN — INC-104
Classification: fallen_branches | pothole | vehicle_or_debris
Workflow: <approved workflow ID>
Confidence: high | medium | low
Reason: <one sentence grounded in report evidence>

Assignments:
- <task> — <workspace member> — <scheduled start>

ETA: <time>
Review required: yes | no
```

If a complete qualified crew is not available, OpenClaw must post `Review
required: yes` and explain the missing role. It must not invent a worker.

## Using existing workspace members as simulated crew

Create a small profile record for each person who is already in Ambiguous.
Use their Ambiguous user ID for assigning tasks, but give each person a
temporary **demo role**, not a real-world job qualification.

```ts
type DemoCrewProfile = {
  workspaceUserId: string;
  displayName: string;
  simulatedSkills: string[];
  simulatedAvailability: Array<{ start: string; end: string }>;
  equipmentAccess: string[];
};
```

For the branch-removal demo, choose one team member for each role:

| Simulated role | Required capability | Task ownership |
| --- | --- | --- |
| Field lead / chainsaw operator | `site_safety`, `chainsaw` | Secure site, cut branches, verify clear |
| Loader operator | `loader` | Load branches |
| Transport driver | `transport` | Haul/dispose branches |
| Dispatcher (optional) | `dispatch` | Review override and status updates |

With four workspace members, use three as the crew and one as dispatcher, or
let the agent act as dispatcher and use all four as available simulated crew.
Record the final role mapping in fixture data, then have OpenClaw read it from
a single `Crew Roster & Availability` document or sheet.
