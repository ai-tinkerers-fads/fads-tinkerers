import { createHash, randomBytes, randomUUID } from "node:crypto";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import type { IncidentStatus, ReportAccepted, ResidentReportInput, SafeIncidentStatus } from "@/src/contracts";
import { toMilestone } from "@/src/contracts";

export type StoredIncident = {
  id: string;
  trackingToken: string;
  idempotencyKey: string;
  report: ResidentReportInput;
  imagePath: string;
  status: IncidentStatus;
  progressMessage: string;
  queuePosition: number | null;
  estimatedResolutionAt: string | null;
  fallbackUsed: boolean;
  ambiguousTaskId: string | null;
  fileId: string | null;
  documentId: string | null;
  approvalTaskId: string | null;
  eventId: string | null;
  progressCommentId: string | null;
  planJson: string | null;
  leaseOwner: string | null;
  leaseUntil: string | null;
  lastProgressAt: string;
  progressMisses: number;
  createdAt: string;
  updatedAt: string;
};

type IncidentRow = Record<string, string | number | null>;

let database: DatabaseSync | undefined;
function db(): DatabaseSync {
  if (database) return database;
  const path = process.env.FADS_DB_PATH ?? join(process.cwd(), "data", "fads.sqlite");
  mkdirSync(dirname(path), { recursive: true });
  database = new DatabaseSync(path);
  database.exec(`
    PRAGMA journal_mode=WAL;
    PRAGMA busy_timeout=5000;
    CREATE TABLE IF NOT EXISTS incidents (
      id TEXT PRIMARY KEY,
      tracking_token_hash TEXT UNIQUE NOT NULL,
      tracking_token TEXT UNIQUE NOT NULL,
      idempotency_key TEXT UNIQUE NOT NULL,
      report_json TEXT NOT NULL,
      image_path TEXT NOT NULL,
      status TEXT NOT NULL,
      progress_message TEXT NOT NULL,
      queue_position INTEGER,
      estimated_resolution_at TEXT,
      fallback_used INTEGER NOT NULL DEFAULT 0,
      ambiguous_task_id TEXT,
      file_id TEXT,
      document_id TEXT,
      approval_task_id TEXT,
      event_id TEXT,
      progress_comment_id TEXT,
      plan_json TEXT,
      lease_owner TEXT,
      lease_until TEXT,
      last_progress_at TEXT NOT NULL,
      progress_misses INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS incidents_queue ON incidents(status, created_at);
  `);
  return database;
}

function mapRow(row: IncidentRow): StoredIncident {
  return {
    id: String(row.id),
    trackingToken: String(row.tracking_token),
    idempotencyKey: String(row.idempotency_key),
    report: JSON.parse(String(row.report_json)) as ResidentReportInput,
    imagePath: String(row.image_path),
    status: String(row.status) as IncidentStatus,
    progressMessage: String(row.progress_message),
    queuePosition: row.queue_position === null ? null : Number(row.queue_position),
    estimatedResolutionAt: row.estimated_resolution_at === null ? null : String(row.estimated_resolution_at),
    fallbackUsed: Boolean(row.fallback_used),
    ambiguousTaskId: row.ambiguous_task_id === null ? null : String(row.ambiguous_task_id),
    fileId: row.file_id === null ? null : String(row.file_id),
    documentId: row.document_id === null ? null : String(row.document_id),
    approvalTaskId: row.approval_task_id === null ? null : String(row.approval_task_id),
    eventId: row.event_id === null ? null : String(row.event_id),
    progressCommentId: row.progress_comment_id === null ? null : String(row.progress_comment_id),
    planJson: row.plan_json === null ? null : String(row.plan_json),
    leaseOwner: row.lease_owner === null ? null : String(row.lease_owner),
    leaseUntil: row.lease_until === null ? null : String(row.lease_until),
    lastProgressAt: String(row.last_progress_at),
    progressMisses: Number(row.progress_misses),
    createdAt: String(row.created_at),
    updatedAt: String(row.updated_at),
  };
}

export function createIncident(report: ResidentReportInput, imagePath: string, idempotencyKey: string): ReportAccepted {
  const existing = db().prepare("SELECT * FROM incidents WHERE idempotency_key = ?").get(idempotencyKey) as IncidentRow | undefined;
  if (existing) {
    const incident = mapRow(existing);
    return { incidentId: incident.id, trackingToken: incident.trackingToken, statusUrl: `/track/${incident.trackingToken}` };
  }
  const id = `INC-${randomUUID().slice(0, 8).toUpperCase()}`;
  const token = randomBytes(24).toString("base64url");
  const hash = createHash("sha256").update(token).digest("hex");
  const now = new Date().toISOString();
  db().prepare(`INSERT INTO incidents (
    id, tracking_token_hash, tracking_token, idempotency_key, report_json, image_path,
    status, progress_message, last_progress_at, created_at, updated_at
  ) VALUES (?, ?, ?, ?, ?, ?, 'reported', ?, ?, ?, ?)`)
    .run(id, hash, token, idempotencyKey, JSON.stringify(report), imagePath, "Report received and queued for assessment.", now, now, now);
  return { incidentId: id, trackingToken: token, statusUrl: `/track/${token}` };
}

export function incidentByToken(token: string): StoredIncident | null {
  const hash = createHash("sha256").update(token).digest("hex");
  const row = db().prepare("SELECT * FROM incidents WHERE tracking_token_hash = ?").get(hash) as IncidentRow | undefined;
  return row ? mapRow(row) : null;
}

export function incidentById(id: string): StoredIncident | null {
  const row = db().prepare("SELECT * FROM incidents WHERE id = ?").get(id) as IncidentRow | undefined;
  return row ? mapRow(row) : null;
}

export function safeStatus(incident: StoredIncident): SafeIncidentStatus {
  return {
    incidentId: incident.id,
    status: incident.status,
    milestone: toMilestone(incident.status),
    issueLabel: incident.report.issueType.replaceAll("_", " "),
    address: incident.report.address,
    progressMessage: incident.progressMessage,
    queuePosition: incident.queuePosition,
    estimatedResolutionAt: incident.estimatedResolutionAt,
    fallbackUsed: incident.fallbackUsed,
    updatedAt: incident.updatedAt,
  };
}

export function claimIncidents(owner: string, limit: number): StoredIncident[] {
  const now = new Date();
  const leaseUntil = new Date(now.getTime() + 4 * 60_000).toISOString();
  const candidates = db().prepare(`SELECT id FROM incidents
    WHERE status = 'reported' AND (lease_until IS NULL OR lease_until < ?)
    ORDER BY created_at LIMIT ?`).all(now.toISOString(), limit) as { id: string }[];
  const claimed: StoredIncident[] = [];
  for (const candidate of candidates) {
    const result = db().prepare(`UPDATE incidents SET lease_owner=?, lease_until=?, status='assessing',
      progress_message='Assessing image and selected workflow.', last_progress_at=?, updated_at=?
      WHERE id=? AND status='reported' AND (lease_until IS NULL OR lease_until < ?)`).run(
      owner, leaseUntil, now.toISOString(), now.toISOString(), candidate.id, now.toISOString(),
    );
    if (result.changes === 1) {
      const incident = incidentById(candidate.id);
      if (incident) claimed.push(incident);
    }
  }
  refreshQueuePositions();
  return claimed;
}

export function updateIncident(id: string, fields: Partial<{
  status: IncidentStatus;
  progressMessage: string;
  estimatedResolutionAt: string | null;
  fallbackUsed: boolean;
  ambiguousTaskId: string;
  fileId: string;
  documentId: string;
  approvalTaskId: string;
  eventId: string;
  progressCommentId: string;
  planJson: string;
  leaseOwner: null;
  leaseUntil: null;
}>): void {
  const columns: string[] = [];
  const values: Array<string | number | null> = [];
  const names: Record<string, string> = {
    status: "status", progressMessage: "progress_message", estimatedResolutionAt: "estimated_resolution_at",
    fallbackUsed: "fallback_used", ambiguousTaskId: "ambiguous_task_id", fileId: "file_id",
    documentId: "document_id", approvalTaskId: "approval_task_id", eventId: "event_id",
    progressCommentId: "progress_comment_id", planJson: "plan_json", leaseOwner: "lease_owner", leaseUntil: "lease_until",
  };
  for (const [key, value] of Object.entries(fields)) {
    if (value === undefined) continue;
    columns.push(`${names[key]}=?`);
    values.push(typeof value === "boolean" ? Number(value) : value);
  }
  const now = new Date().toISOString();
  columns.push("updated_at=?", "last_progress_at=?", "progress_misses=0");
  values.push(now, now, id);
  db().prepare(`UPDATE incidents SET ${columns.join(", ")} WHERE id=?`).run(...values);
  refreshQueuePositions();
}

export function activeIncidents(): StoredIncident[] {
  return (db().prepare(`SELECT * FROM incidents WHERE status NOT IN ('resolved','cancelled') ORDER BY created_at`).all() as IncidentRow[]).map(mapRow);
}

export function releaseExpiredLeases(): void {
  const now = new Date().toISOString();
  db().prepare(`UPDATE incidents SET status='reported', lease_owner=NULL, lease_until=NULL,
    progress_message='Worker interrupted; safely requeued.', updated_at=?
    WHERE status='assessing' AND lease_until < ?`).run(now, now);
  refreshQueuePositions();
}

export function markOverdueProgress(): void {
  const cutoff = new Date(Date.now() - 45_000).toISOString();
  db().prepare(`UPDATE incidents SET progress_message='Worker delayed — retrying the current action.',
    progress_misses=progress_misses+1, updated_at=?
    WHERE status IN ('assessing','in_progress') AND last_progress_at < ?`).run(new Date().toISOString(), cutoff);
  const twice = db().prepare(`SELECT id FROM incidents WHERE progress_misses >= 2 AND status='assessing'`).all() as { id: string }[];
  for (const row of twice) {
    updateIncident(row.id, { status: "reported", progressMessage: "Worker stalled twice; requeued for recovery.", leaseOwner: null, leaseUntil: null });
  }
}

function refreshQueuePositions(): void {
  db().exec("UPDATE incidents SET queue_position=NULL WHERE status <> 'reported'");
  const queued = db().prepare("SELECT id FROM incidents WHERE status='reported' ORDER BY created_at").all() as { id: string }[];
  queued.forEach((row, index) => db().prepare("UPDATE incidents SET queue_position=? WHERE id=?").run(index + 1, row.id));
}
