import {
  createHash,
  randomBytes,
  randomUUID,
  timingSafeEqual,
} from "node:crypto";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  writeFileSync,
} from "node:fs";
import { resolve } from "node:path";
import { NotFoundException, UnauthorizedException } from "@nestjs/common";
import type { SessionState, StoredSession } from "./types";

/** Single-process, local prototype store. Atomic writes happen before external actions. */
export class SessionStore {
  private sessions = new Map<string, StoredSession>();
  private readonly file: string;
  constructor(
    directory = process.env.DATA_DIR ?? resolve(process.cwd(), ".data"),
  ) {
    mkdirSync(directory, { recursive: true, mode: 0o700 });
    this.file = resolve(directory, "sessions.json");
    if (existsSync(this.file)) {
      for (const session of JSON.parse(
        readFileSync(this.file, "utf8"),
      ) as StoredSession[]) {
        // A process crash after submission is an uncertain remote result, never permission to retry.
        if (session.submission?.status === "saving")
          session.submission = {
            ...session.submission,
            status: "unknown",
            error:
              "Server restarted during submission. Check Ambiguous.ai before retrying.",
          };
        if (session.status === "active" || session.status === "connecting")
          session.status = "ended";
        this.sessions.set(session.id, session);
      }
      this.flush();
    }
  }
  create(mode: "demo" | "live") {
    const token = randomBytes(32).toString("hex");
    const session: StoredSession = {
      id: randomUUID(),
      tokenHash: this.hash(token),
      createdAt: Date.now(),
      mode,
      status: mode === "demo" ? "active" : "connecting",
      transcript: [],
      draft: null,
      revision: 0,
      confirmationRequested: false,
      submission: null,
      demoStep: "issue",
    };
    this.sessions.set(session.id, session);
    this.save(session);
    return { session, token };
  }
  get(id: string) {
    const session = this.sessions.get(id);
    if (!session) throw new NotFoundException("Conversation not found");
    return session;
  }
  authorized(id: string, authorization?: string) {
    const session = this.get(id);
    const hash = this.hash(authorization?.replace(/^Bearer /, "") ?? "");
    if (!timingSafeEqual(Buffer.from(hash), Buffer.from(session.tokenHash)))
      throw new UnauthorizedException("Invalid conversation token");
    return session;
  }
  save(session: StoredSession) {
    this.sessions.set(session.id, session);
    this.flush();
  }
  public(session: StoredSession): SessionState {
    const {
      id,
      mode,
      status,
      transcript,
      draft,
      revision,
      confirmationRequested,
      submission,
      error,
    } = session;
    return {
      id,
      mode,
      status,
      transcript,
      draft,
      revision,
      confirmationRequested,
      submission,
      ...(error ? { error } : {}),
    };
  }
  private hash(token: string) {
    return createHash("sha256").update(token).digest("hex");
  }
  private flush() {
    const temp = `${this.file}.tmp`;
    writeFileSync(temp, JSON.stringify([...this.sessions.values()]), {
      mode: 0o600,
    });
    renameSync(temp, this.file);
  }
}
