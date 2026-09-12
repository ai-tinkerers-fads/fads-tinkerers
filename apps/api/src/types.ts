import type { ComplaintDraft } from "./ambiguous.service";

export interface Transcript {
  id: string;
  role: "user" | "assistant";
  text: string;
  startMs?: number;
  endMs?: number;
}
export interface Submission {
  status: "saving" | "saved" | "unknown" | "failed";
  id?: string;
  url?: string;
  mode?: "live" | "demo";
  error?: string;
  key: string;
}
export interface SessionState {
  id: string;
  mode: "demo" | "live";
  status: "connecting" | "active" | "ended" | "error";
  transcript: Transcript[];
  draft: ComplaintDraft | null;
  revision: number;
  confirmationRequested: boolean;
  submission: Submission | null;
  error?: string;
}
export interface StoredSession extends SessionState {
  tokenHash: string;
  createdAt: number;
  openaiId?: string;
  readback?: string;
  preparedDraftKey?: string;
  readbackAfter?: number;
  readbackCompleteAt?: number;
  readbackMinStartMs?: number;
  readbackEndMs?: number;
  demoStep?: "issue" | "location" | "contact" | "confirm" | "correction";
}
