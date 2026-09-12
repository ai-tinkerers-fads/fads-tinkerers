import { claimIncidents, markOverdueProgress, releaseExpiredLeases } from "@/src/db/store";
import { processIncident, reconcileApprovals } from "@/src/orchestration/worker";

const workerId = `dispatcher-${process.pid}`;
const running = new Set<Promise<void>>();

async function tick(): Promise<void> {
  releaseExpiredLeases();
  markOverdueProgress();
  try { await reconcileApprovals(); } catch (error) { console.error("approval reconciliation failed", error); }
  const capacity = Math.max(0, 4 - running.size);
  for (const incident of claimIncidents(workerId, capacity)) {
    const work = processIncident(incident.id).finally(() => running.delete(work));
    running.add(work);
  }
}

console.log(`FADS dispatcher ${workerId} started with four worker slots.`);
await tick();
setInterval(() => void tick(), 5_000);
