# Voice intake implementation

Approved scope: a resident has a live conversation about road damage, repairs,
or a road-related question. The agent collects the report, reads it back, obtains
verbal confirmation, and logs a task in Ambiguous.ai. A customer service agent
will contact the resident if necessary. This increment does not answer repair
status questions or dispatch crews.

## Implementation sequence

1. Scaffold a Next.js/TypeScript frontend and Node.js/NestJS backend in npm workspaces.
2. Connect GPT-Live-1 browser audio over WebRTC, with server-owned credentials and session controls.
3. Add structured intake and verbal confirmation of the current draft.
4. Create Ambiguous.ai tasks; preserve save outcomes and prevent duplicate writes.
5. Verify corrections, missing information, declined confirmation, disconnects, and successful logging.

## Record and confirmation rules

- Capture complaint/question, description, location, and offered contact details.
- Preserve transcript evidence and distinguish demo conversations from real calls.
- Read back the draft before requesting confirmation. A changed draft requires a new confirmation.
- Only acknowledge successful logging after the integration returns a valid task ID.
- A timeout may mean a task was created; do not blindly retry uncertain writes.
- Demo mode must identify simulated records and must not claim to have saved to Ambiguous.ai.

## Technical references

- [GPT-Live](https://developers.openai.com/api/docs/guides/live)
- [Browser WebRTC](https://developers.openai.com/api/docs/guides/voice-webrtc?api=live)
- [Delegation and tools](https://developers.openai.com/api/docs/guides/live-delegation)
- [Ambiguous.ai API](https://www.ambiguous.ai/agents/api)
- [Ambiguous.ai task recipes](https://www.ambiguous.ai/agents/recipes)

Ambiguous.ai documents `POST /api/tasks` and a `{ task: { id, ... } } response.
Workspace access is determined by a server-side bearer token. No credentials or
customer data belong in the repository.
