"""Acceptance smoke for the hooks contract (handoff Phases 2-4) against a disposable local server.

Starts its own demo server and a local signed-webhook receiver, exercises the
real HTTP hooks, and inspects the SQLite ledger. Never contacts external services.
Run from the repository root: python3 fads_coordination/scripts/smoke_hooks.py
"""

import copy
import hashlib
import hmac
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
SECRET = "smoke-secret"
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok or not detail else f"  [{detail}]"))


class Receiver(BaseHTTPRequestHandler):
    mode = "ok"
    seen = []

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        stamp, signature = self.headers.get("X-FADS-Timestamp", ""), self.headers.get("X-FADS-Signature", "")
        expected = "sha256=" + hmac.new(SECRET.encode(), stamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
        Receiver.seen.append({"key": self.headers.get("Idempotency-Key"), "valid": hmac.compare_digest(signature, expected), "mode": Receiver.mode})
        if Receiver.mode == "hang":
            time.sleep(2)  # longer than the sender's timeout
        self.send_response(500 if Receiver.mode == "fail" else 200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


def main():
    receiver = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    threading.Thread(target=receiver.serve_forever, daemon=True).start()
    with tempfile.TemporaryDirectory(prefix="fads-hooks-") as folder:
        db = Path(folder) / "demo.sqlite"
        env = {**os.environ, "FADS_WEBHOOK_URL": f"http://127.0.0.1:{receiver.server_port}/hook", "FADS_WEBHOOK_SECRET": SECRET}
        server = subprocess.Popen([sys.executable, "-m", "fads_coordination.demo", "--port", "0", "--db", str(db)], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            line = server.stdout.readline().strip()
            assert "http://127.0.0.1:" in line, "Server failed to start: " + server.stderr.read(500)
            base = "http://" + line.split("http://", 1)[1]

            def req(path, data=None):
                body = json.dumps(data).encode() if data is not None else None
                request = Request(base + path, data=body, headers={"Content-Type": "application/json"})
                try:
                    with urlopen(request, timeout=10) as response:
                        return response.status, json.loads(response.read())
                except HTTPError as exc:
                    return exc.code, json.loads(exc.read())

            def rows(sql, *args):
                connection = sqlite3.connect(db)
                connection.row_factory = sqlite3.Row
                try:
                    return [dict(r) for r in connection.execute(sql, args)]
                finally:
                    connection.close()

            def count(sql, *args):
                return rows(sql, *args)[0]["n"]

            def state():
                return req("/hooks/state/pine-street-001?callerId=smoke")[1]["body"]

            fixture = json.loads((ROOT / "fads_coordination/fixtures/branch-removal.json").read_text())
            time.sleep(2)  # let the tick loop deliver the initially due reminder

            # Phase 2: outbox, idempotent load, paging, signed webhook, retry and timeout states.
            entries = req("/hooks/outbox?callerId=smoke&after=0&types=schedule_entry")[1]["items"]
            check("outbox: fixture load emits five schedule_entry packages", len(entries) == 5, str(len(entries)))
            before = count("SELECT COUNT(*) n FROM outbox WHERE type='schedule_entry'")
            status, _ = req("/hooks/assignments", {"callerId": "smoke", **fixture})
            after = count("SELECT COUNT(*) n FROM outbox WHERE type='schedule_entry'")
            check("outbox: reposting an identical package emits nothing", status == 200 and before == after, f"{before}->{after}")
            page = req("/hooks/outbox?callerId=smoke&after=0")[1]
            tail = req(f"/hooks/outbox?callerId=smoke&after={page['nextCursor']}")[1]
            check("outbox: paging after nextCursor returns nothing new", tail["items"] == [] and tail["nextCursor"] == page["nextCursor"])
            time.sleep(2)
            ok = [s for s in Receiver.seen if s["mode"] == "ok"]
            check("webhook: each package delivered once with a valid signature", len(ok) >= 5 and all(s["valid"] for s in ok) and len({s["key"] for s in ok}) == len(ok), f"seen={len(ok)}")
            check("webhook: accepted state recorded", count("SELECT COUNT(*) n FROM webhook_deliveries WHERE state='accepted'") >= 5)

            Receiver.mode = "fail"
            req("/hooks/employees/jordan/availability", {"employeeId": "jordan", "kind": "late", "window": {"start": "2026-09-14T09:10:00-07:00", "end": "2026-09-14T09:11:00-07:00"}, "reason": "smoke", "sourceId": "smoke-jordan-late"})
            deadline = time.time() + 15
            while time.time() < deadline and not count("SELECT COUNT(*) n FROM webhook_deliveries WHERE state='failed'"):
                time.sleep(0.5)
            failed = rows("SELECT attempt FROM webhook_deliveries WHERE state='failed'")
            check("webhook: receiver 500 -> bounded retries then failed", failed and all(r["attempt"] <= 3 for r in failed), str(failed)[:120])

            Receiver.mode = "hang"
            Receiver.seen.clear()
            req("/hooks/employees/jordan/availability", {"employeeId": "jordan", "kind": "late", "window": {"start": "2026-09-14T09:15:00-07:00", "end": "2026-09-14T09:16:00-07:00"}, "reason": "smoke", "sourceId": "smoke-jordan-later"})
            time.sleep(7)
            unknown = rows("SELECT attempt FROM webhook_deliveries WHERE state='unknown'")
            keys = [s["key"] for s in Receiver.seen]
            check("webhook: receiver timeout -> unknown on first attempt, never resent", unknown and all(r["attempt"] == 1 for r in unknown) and len(keys) == len(set(keys)), f"unknown={len(unknown)} sends={len(keys)}")
            Receiver.mode = "ok"

            # Phase 3: employee availability overrides and conflict signals.
            top = count("SELECT MAX(cursor) n FROM outbox")
            day_off = {"employeeId": "sam", "kind": "day_off", "window": {"start": "2026-09-14T09:00:00-07:00", "end": "2026-09-14T10:00:00-07:00"}, "reason": "smoke day off", "sourceId": "smoke-sam-dayoff"}
            status, first = req("/hooks/employees/sam/availability", day_off)
            conflicts = first.get("conflicts", [])
            check("conflict: Sam's day off returns one conflict naming sam, transport, absence", status == 200 and len(conflicts) == 1 and (conflicts[0]["body"]["employeeId"], conflicts[0]["body"]["taskId"], conflicts[0]["body"]["cause"]) == ("sam", "transport", "absence"), str(conflicts)[:160])
            blocked = {t["taskId"] for t in state()["schedule"] if t["state"] == "blocked"}
            check("conflict: transport and verify are blocked", {"transport", "verify"} <= blocked, str(blocked))
            status, second = req("/hooks/employees/sam/availability", day_off)
            check("conflict: same sourceId twice -> one override and the same receipt", status == 200 and second == first and count("SELECT COUNT(*) n FROM availability_overrides WHERE employee='sam'") == 1)
            check("conflict: exactly one conflict package emitted", count("SELECT COUNT(*) n FROM outbox WHERE type='conflict' AND cursor>?", top) == 1)

            top = count("SELECT MAX(cursor) n FROM outbox")
            package = copy.deepcopy(fixture)
            package["revision"] = 2
            package["employees"].append({"id": "taylor", "name": "Taylor", "skills": ["transport"], "equipmentAccess": ["truck"], "availability": [{"start": "2026-09-14T11:00:00-07:00", "end": "2026-09-14T17:00:00-07:00"}]})
            for assignment in package["assignments"]:
                if assignment["taskId"] == "transport":
                    assignment["employeeId"] = "taylor"
            status, _ = req("/hooks/assignments", {"callerId": "smoke", **package})
            snapshot = state()
            stale = [r for r in snapshot["reminders"] if r["taskId"] == "transport" and r["employeeId"] == "sam" and r["status"] in ("scheduled", "delivered")]
            check("reassignment: accepted, Sam's transport reminders superseded", status == 200 and not stale)
            check("reassignment: transport scheduled for Taylor", any(t["taskId"] == "transport" and t["employeeId"] == "taylor" and t["state"] == "scheduled" for t in snapshot["schedule"]))
            check("reassignment: Sam's override still in force", count("SELECT COUNT(*) n FROM availability_overrides WHERE employee='sam'") == 1)
            check("reassignment: no new conflict", count("SELECT COUNT(*) n FROM outbox WHERE type='conflict' AND cursor>?", top) == 0)

            # Phase 4: done checklist with unknown actuals, idempotency, proof relay.
            top = count("SELECT MAX(cursor) n FROM outbox")
            samples = next(t for t in snapshot["schedule"] if t["taskId"] == "secure")["nextEstimate"]["sampleCount"]
            done = {"employeeId": "alex", "checklist": [{"item": "Barriers placed", "done": True}], "sourceId": "smoke-done-secure"}
            status, _ = req("/hooks/tasks/pine-street-001/secure/done", done)
            completions = rows("SELECT body FROM outbox WHERE type='completion' AND cursor>?", top)
            body = json.loads(completions[0]["body"])["body"] if completions else {}
            check("done: without actuals -> completion package with actualMinutes null", status == 200 and len(completions) == 1 and body.get("actualMinutes") is None)
            check("done: outcome stored with actual NULL, never zero", rows("SELECT actual FROM outcomes WHERE task='secure'") == [{"actual": None}])
            check("done: estimate sample count unchanged by unknown actual", next(t for t in state()["schedule"] if t["taskId"] == "secure")["nextEstimate"]["sampleCount"] == samples)
            status, _ = req("/hooks/tasks/pine-street-001/secure/done", done)
            check("done: same sourceId twice -> one completion package", status == 200 and count("SELECT COUNT(*) n FROM outbox WHERE type='completion' AND cursor>?", top) == 1)
            proof = {"employeeId": "alex", "proof": {"kind": "image", "ref": "app://uploads/cut-1.jpg", "note": "after cut"}, "sourceId": "smoke-proof-cut"}
            first_status, _ = req("/hooks/tasks/pine-street-001/cut/proof", proof)
            second_status, _ = req("/hooks/tasks/pine-street-001/cut/proof", proof)
            check("proof: accepted; same sourceId twice -> one proof row", first_status == 200 and second_status == 200 and count("SELECT COUNT(*) n FROM proofs") == 1)
            top = count("SELECT MAX(cursor) n FROM outbox")
            status, _ = req("/hooks/tasks/pine-street-001/cut/done", {"employeeId": "alex", "checklist": [{"item": "Branches cut", "done": True}], "actualMinutes": 30, "waitingMinutes": 0, "sourceId": "smoke-done-cut"})
            body = json.loads(rows("SELECT body FROM outbox WHERE type='completion' AND cursor>?", top)[0]["body"])["body"]
            check("proof: posted before done appears in the completion package", status == 200 and len(body.get("proofs", [])) == 1 and body.get("actualMinutes") == 30)
            status, _ = req("/hooks/tasks/pine-street-001/load/done", {"employeeId": "jordan", "checklist": [{"item": "x", "done": False}], "sourceId": "smoke-bad"})
            check("done: unchecked checklist item rejected", status == 400)
        finally:
            server.terminate()
            try:
                server.wait(5)
            except subprocess.TimeoutExpired:
                server.kill()
            receiver.shutdown()
    print(f"{sum(RESULTS)}/{len(RESULTS)} hook checks passed; fixture run, no external messages")
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
