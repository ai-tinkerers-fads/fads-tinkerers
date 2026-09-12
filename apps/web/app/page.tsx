"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/voice-api";
type Session = {
  id: string;
  token?: string;
  mode: "demo" | "live";
  status: "connecting" | "active" | "ended" | "error";
  transcript: { id: string; role: "user" | "assistant"; text: string }[];
  draft: {
    kind: string;
    category?: string;
    description: string;
    location: string;
    contact?: string;
    name?: string;
    impact?: string;
  } | null;
  revision: number;
  confirmationRequested: boolean;
  error?: string;
  submission: {
    status: "saving" | "saved" | "unknown" | "failed";
    id?: string;
    url?: string;
    mode?: string;
    error?: string;
    key: string;
  } | null;
  transport?: { type: "webrtc"; sdp: string };
};
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.message === "string"
        ? body.message
        : `Request failed (${response.status}). Please try again.`,
    );
  }
  return response.json();
}
function safeUrl(url?: string) {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" ? parsed.href : null;
  } catch {
    return null;
  }
}

export default function Home() {
  const [session, setSession] = useState<Session | null>(null);
  const [demo, setDemo] = useState(false);
  const [available, setAvailable] = useState<boolean | null>(null);
  const [recordMode, setRecordMode] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [muted, setMuted] = useState(false);
  const [error, setError] = useState("");
  const [text, setText] = useState("");
  const [configError, setConfigError] = useState("");
  const [checkingConfig, setCheckingConfig] = useState(false);
  const attempt = useRef(0);
  const token = useRef("");
  const currentSession = useRef<{ id: string; token: string } | null>(null);
  const pc = useRef<RTCPeerConnection | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const transcript = useRef<HTMLDivElement | null>(null);
  const active =
    session?.status === "active" || session?.status === "connecting";
  const awaitingSave = session?.submission?.status === "saving";
  const cleanup = () => {
    pc.current?.close();
    pc.current = null;
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
    if (audio.current) audio.current.srcObject = null;
  };
  const loadConfig = useCallback(async () => {
    setCheckingConfig(true);
    setConfigError("");
    try {
      const config = await request<{
        liveAvailable: boolean;
        recordMode?: string;
      }>("/config");
      setAvailable(config.liveAvailable);
      setRecordMode(config.recordMode ?? null);
      setDemo(!config.liveAvailable);
    } catch {
      setConfigError(
        "The intake service is unavailable. Start the backend, then retry the connection.",
      );
    } finally {
      setCheckingConfig(false);
    }
  }, []);
  useEffect(() => {
    void loadConfig();
    const terminate = () => {
      attempt.current += 1;
      const current = currentSession.current;
      if (current) {
        void fetch(`${API}/sessions/${current.id}/end`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${current.token}`,
            "Content-Type": "application/json",
          },
          keepalive: true,
        }).catch(() => {});
        currentSession.current = null;
      }
      cleanup();
    };
    window.addEventListener("pagehide", terminate);
    return () => {
      window.removeEventListener("pagehide", terminate);
      terminate();
    };
  }, [loadConfig]);
  useEffect(() => {
    if (transcript.current)
      transcript.current.scrollTop = transcript.current.scrollHeight;
  }, [session?.transcript]);
  useEffect(() => {
    if (!session?.id || (!active && !awaitingSave) || busy) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await request<Session>(`/sessions/${session!.id}`, {
          headers: { Authorization: `Bearer ${token.current}` },
        });
        if (!cancelled) {
          setSession(next);
          if (next.status === "ended" || next.status === "error") cleanup();
        }
      } catch (cause) {
        if (!cancelled)
          setError(
            cause instanceof Error ? cause.message : "Connection interrupted.",
          );
      }
      if (!cancelled) timer = setTimeout(poll, 1000);
    }
    timer = setTimeout(poll, 1000);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [session?.id, active, awaitingSave, busy]);

  async function start() {
    const currentAttempt = ++attempt.current;
    setBusy(true);
    setError("");
    setSession(null);
    setMuted(false);
    token.current = "";
    cleanup();
    try {
      let sdp: string | undefined;
      if (!demo) {
        const microphone = await navigator.mediaDevices.getUserMedia({
          audio: true,
        });
        if (currentAttempt !== attempt.current) {
          microphone.getTracks().forEach((track) => track.stop());
          return;
        }
        stream.current = microphone;
        const connection = new RTCPeerConnection();
        pc.current = connection;
        connection.ontrack = (event) => {
          if (audio.current) {
            audio.current.srcObject = event.streams[0];
            void audio.current
              .play()
              .catch(() =>
                setError(
                  "Audio playback was blocked. Use the audio player below to hear the agent.",
                ),
              );
          }
        };
        connection.onconnectionstatechange = () => {
          if (connection.connectionState === "failed") {
            setError(
              "Voice connection failed. End the conversation and try again.",
            );
            stream.current?.getTracks().forEach((track) => track.stop());
          }
        };
        stream.current
          .getTracks()
          .forEach((track) => connection.addTrack(track, stream.current!));
        connection.createDataChannel("oai-events");
        await connection.setLocalDescription(await connection.createOffer());
        sdp = connection.localDescription?.sdp;
      }
      const next = await request<Session>("/sessions", {
        method: "POST",
        body: JSON.stringify({ mode: demo ? "demo" : "live", sdp }),
      });
      if (currentAttempt !== attempt.current) {
        await request(`/sessions/${next.id}/end`, {
          method: "POST",
          headers: { Authorization: `Bearer ${next.token}` },
        }).catch(() => {});
        return;
      }
      token.current = next.token ?? "";
      currentSession.current = { id: next.id, token: token.current };
      setSession(next);
      if (!demo) {
        if (!next.transport?.sdp)
          throw new Error("The voice service did not return a connection.");
        await pc.current!.setRemoteDescription({
          type: "answer",
          sdp: next.transport.sdp,
        });
      }
    } catch (cause) {
      const current = currentSession.current;
      if (current) {
        await request(`/sessions/${current.id}/end`, {
          method: "POST",
          headers: { Authorization: `Bearer ${current.token}` },
        }).catch(() => {});
        currentSession.current = null;
      }
      cleanup();
      setSession((previous) =>
        previous ? { ...previous, status: "error" } : null,
      );
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not start the conversation.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function end() {
    if (!session) return;
    setBusy(true);
    cleanup();
    try {
      setSession(
        await request<Session>(`/sessions/${session.id}/end`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token.current}` },
        }),
      );
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not end session.",
      );
      setSession((previous) =>
        previous ? { ...previous, status: "ended" } : null,
      );
    } finally {
      currentSession.current = null;
      setBusy(false);
    }
  }
  async function send(event: FormEvent) {
    event.preventDefault();
    if (!text.trim() || !session || busy) return;
    setBusy(true);
    setError("");
    try {
      setSession(
        await request<Session>(`/sessions/${session.id}/demo-message`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token.current}` },
          body: JSON.stringify({ text: text.trim() }),
        }),
      );
      setText("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Message failed.");
    } finally {
      setBusy(false);
    }
  }
  function toggleMute() {
    stream.current
      ?.getAudioTracks()
      .forEach((track) => (track.enabled = muted));
    setMuted(!muted);
  }
  const draft = session?.draft;
  const saved = session?.submission?.status === "saved";
  const simulatedRecord = session?.submission?.mode === "demo";
  const recordUrl = safeUrl(session?.submission?.url);
  const fields = [
    ["Report type", draft?.kind],
    ["Issue or question", draft?.description],
    ["Road / location", draft?.location],
    ["Contact details", draft?.contact],
    ["Reported impact", draft?.impact],
  ];
  return (
    <>
      <header>
        <div className="brand">
          <span className="brand-icon" aria-hidden="true">
            ↗
          </span>{" "}
          FADS <span>ROAD SUPPORT</span>
        </div>
        <nav className="report-modes" aria-label="Report mode">
          <a href="/">Photo report</a>
          <span aria-current="page">Voice report</span>
        </nav>
      </header>
      <main>
        <p className="eyebrow">A better way to report</p>
        <h1>Tell us what’s happening.</h1>
        <p className="intro">
          Report road damage or ask about a repair. Our assistant will capture
          the details, check them with you, and log your request.
        </p>
        <div className="grid">
          <section className="panel" aria-label="Conversation">
            <div className="panel-head">
              <h2>Your conversation</h2>
              <span className="status" role="status">
                <span className={`dot ${active ? "active" : ""}`} />
                {busy && !active
                  ? "Connecting…"
                  : active
                    ? demo
                      ? "Demo session"
                      : muted
                        ? "Microphone muted"
                        : "Connected"
                    : session?.status === "error"
                      ? "Connection error"
                      : session
                        ? "Conversation ended"
                        : "Ready when you are"}
              </span>
            </div>
            <div className="voice-stage">
              <div
                className={`orb ${active && !muted ? "active" : ""}`}
                aria-hidden="true"
              >
                <i />
                <i />
                <i />
                <i />
                <i />
              </div>
              <h2>
                {active
                  ? saved
                    ? "Your report is logged"
                    : demo
                      ? "Try a sample conversation"
                      : "We’re listening"
                  : "Road support, one conversation away"}
              </h2>
              <p>
                {active
                  ? demo
                    ? "Type as the resident below. The demo simulates voice intake and record creation."
                    : "Describe the road issue in your own words. You’ll confirm the details before we log it."
                  : "Have the road name or a nearby landmark ready. Contact details help us follow up if needed."}
              </p>
              <div className="controls">
                {active ? (
                  <>
                    {!demo && (
                      <button
                        className="secondary"
                        onClick={toggleMute}
                        aria-pressed={muted}
                      >
                        {muted ? "Unmute" : "Mute microphone"}
                      </button>
                    )}
                    <button className="end" onClick={end} disabled={busy}>
                      End conversation
                    </button>
                  </>
                ) : (
                  <button
                    className="primary"
                    onClick={start}
                    disabled={
                      busy || available === null || (!demo && !available)
                    }
                  >
                    {busy
                      ? "Starting…"
                      : session
                        ? "Start another conversation"
                        : demo
                          ? "Start demo"
                          : "Start conversation"}
                  </button>
                )}
              </div>
            </div>
            <label className="mode">
              <input
                type="checkbox"
                checked={demo}
                disabled={!!active || busy || available === false}
                onChange={(event) => setDemo(event.target.checked)}
              />
              Use text demo · simulated records
            </label>
            {available === false && (
              <div className="notice">
                Live voice is not configured. The text demo is available; it
                does not create a real Ambiguous.ai record.
              </div>
            )}
            {!demo && recordMode === "demo" && (
              <div className="notice">
                Live voice is enabled with simulated records. No real request or
                follow-up will be created.
              </div>
            )}
            {configError && (
              <div className="notice error" role="alert">
                {configError}
                <br />
                <button
                  className="secondary"
                  onClick={loadConfig}
                  disabled={checkingConfig}
                >
                  {checkingConfig ? "Checking…" : "Retry connection"}
                </button>
              </div>
            )}
            {(error || session?.error) && (
              <div className="notice error" role="alert">
                {error || session?.error}
              </div>
            )}
            <audio
              ref={audio}
              autoPlay
              controls={!!error && !demo}
              aria-label="Agent audio"
            />
            <div className="transcript">
              <div className="transcript-label">
                <h2>Transcript</h2>
                <span>{demo ? "TEXT DEMO" : "LIVE"}</span>
              </div>
              <div
                className="messages"
                ref={transcript}
                role="log"
                aria-label="Conversation transcript"
                aria-live="polite"
              >
                {session?.transcript.length ? (
                  session.transcript.map((message) => (
                    <div key={message.id} className={`message ${message.role}`}>
                      <div className="speaker">
                        {message.role === "user" ? "You" : "Road support"}
                      </div>
                      <p>{message.text}</p>
                    </div>
                  ))
                ) : (
                  <div className="empty">
                    Your conversation will appear here.
                    <br />
                    Nothing is logged until you confirm.
                  </div>
                )}
              </div>
            </div>
            {demo && active && (
              <form className="composer" onSubmit={send}>
                <input
                  aria-label="Your demo message"
                  placeholder="e.g. There’s a pothole on my street…"
                  value={text}
                  onChange={(event) => setText(event.target.value)}
                  disabled={busy || saved}
                />
                <button
                  className="primary"
                  disabled={busy || !text.trim() || saved}
                >
                  Send
                </button>
              </form>
            )}
          </section>
          <aside>
            <section className="panel" aria-label="Captured report">
              <div className="panel-head">
                <h2>Report details</h2>
                <span className="badge">
                  {saved
                    ? "Logged"
                    : session?.confirmationRequested
                      ? demo
                        ? "Confirm in demo"
                        : "Confirm by voice"
                      : "Draft"}
                </span>
              </div>
              <div className="draft">
                <p className="draft-heading">
                  Details captured from your conversation. Tell the assistant if
                  anything needs correcting.
                </p>
                <dl>
                  {fields.map(([label, value]) => (
                    <div className="field" key={label}>
                      <dt>{label}</dt>
                      <dd className={value ? "" : "placeholder"}>
                        {value || "Not provided yet"}
                      </dd>
                    </div>
                  ))}
                </dl>
                {session?.submission && (
                  <div className="result" role="status">
                    {saved ? (
                      <>
                        <strong>
                          {simulatedRecord
                            ? "Demo record created"
                            : "Request logged"}
                        </strong>
                        <br />
                        Reference: {session.submission.id || "Created"}
                        <br />
                        {recordUrl && (
                          <>
                            <a
                              href={recordUrl}
                              target="_blank"
                              rel="noreferrer"
                            >
                              Open record ↗
                            </a>
                            <br />
                          </>
                        )}
                        A customer service agent will contact you if necessary.
                        {simulatedRecord && (
                          <>
                            <br />
                            This is a simulation. No actual follow-up is
                            arranged.
                          </>
                        )}
                      </>
                    ) : session.submission.status === "saving" ? (
                      "Logging your confirmed request…"
                    ) : session.submission.status === "unknown" ? (
                      <>
                        Submission outcome is uncertain. Your request may have
                        been logged; do not submit a duplicate. Customer service
                        can check using this intake reference:
                        <br />
                        {session.submission.key}
                      </>
                    ) : (
                      session.submission.error ||
                      "The request could not be logged. Tell the assistant to try again."
                    )}
                  </div>
                )}
              </div>
              <div className="confirmation">
                {saved
                  ? "Your confirmed details have been logged. Start another conversation to report a different issue."
                  : session?.confirmationRequested
                    ? demo
                      ? "The assistant is checking these details. Type “yes, log it” to simulate confirmation, or explain what needs changing."
                      : "The assistant is checking these details. Say “yes, log it” to confirm, or explain what needs changing."
                    : "You stay in control. The assistant will read back your report and ask for your confirmation before logging it."}
              </div>
            </section>
            <section className="how">
              <h2>What happens next</h2>
              <ol>
                <li>Describe your road complaint or repair question.</li>
                <li>Check the details and confirm with the assistant.</li>
                <li>
                  Your request is logged. A customer service agent will contact
                  you if necessary.
                </li>
              </ol>
            </section>
          </aside>
        </div>
        <footer>
          <span>Road support · Resident intake</span>
          <span>
            This service logs road requests for customer service follow-up.
          </span>
        </footer>
      </main>
    </>
  );
}
