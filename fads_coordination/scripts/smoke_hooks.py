"""Acceptance smoke for the hooks contract (handoff Phases 2-8) against a disposable local server.

Starts its own demo server and a local signed-webhook receiver, exercises the
real HTTP hooks, and inspects the SQLite ledger. Never contacts external services.
Run from the repository root: python3 fads_coordination/scripts/smoke_hooks.py
"""

import copy
import hashlib
import hmac
import json
import os
import queue
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

            # Phases 5-6: same existing script; fixture document and catalog hooks.
            mapping = json.loads((ROOT / "fads_coordination/fixtures/field-map.json").read_text())
            document = {"callerId":"smoke", "source":{"kind":"csv","ref":"assignments.csv"}, "fieldMap":mapping}
            before = count("SELECT COUNT(*) n FROM outbox WHERE type='schedule_entry'")
            status, imported = req("/hooks/assignments/from-document", document)
            after = count("SELECT COUNT(*) n FROM outbox WHERE type='schedule_entry'")
            check("document: fixture CSV maps to five schedule entries", status == 200 and after-before == 5)
            status, repeated = req("/hooks/assignments/from-document", document)
            check("document: unchanged source emits no new schedule entries", status == 200 and imported["documentRevision"] == repeated["documentRevision"] and count("SELECT COUNT(*) n FROM outbox WHERE type='schedule_entry'") == after)
            bad = copy.deepcopy(document)
            del bad["fieldMap"]["assignments"]["employeeId"]
            status, error = req("/hooks/assignments/from-document", bad)
            check("document: missing assignee mapping is named", status == 400 and "assignments.employeeId" in error.get("error", ""))
            status, confirmed = req("/hooks/workflows/branch-removal/1/confirm", {"confirmedBy":"smoke-reviewer"})
            check("catalog: confirm activates existing workflow", status == 200 and confirmed.get("status") == "active")
            status, repeated = req("/hooks/workflows/branch-removal/1/confirm", {"confirmedBy":"another-reviewer"})
            check("catalog: repeat confirm retains original provenance", status == 200 and repeated == confirmed)
            page = req("/hooks/outbox?callerId=smoke&types=schedule_entry")[1]
            first = page["items"][0]
            rest = req(f"/hooks/outbox?callerId=smoke&types=schedule_entry&after={first['cursor']}")[1]
            check("outbox: resume after an individual item cursor", rest["items"] and rest["items"][0]["id"] == page["items"][1]["id"] and all(item["cursor"] > first["cursor"] for item in rest["items"]))

            # Phase 8: local HTTP transport checks; browser acceptance belongs to Claude.
            req("/demo/reset", {"callerId": "smoke-phase8"})
            assignments = req("/hooks/outbox?callerId=smoke&types=assignment")[1]["items"]
            check("notifications: five assigned packages with implemented actions", len(assignments) == 5 and all(
                item["body"]["kind"] == "assigned" and [a["id"] for a in item["body"]["actions"]] == ["accept", "snooze", "delay", "open"] for item in assignments))
            req("/hooks/assignments", {"callerId": "smoke", **fixture})
            check("notifications: identical repost emits no assignments", count("SELECT COUNT(*) n FROM outbox WHERE type='assignment'") == 5)
            alex = next(item for item in assignments if item["body"]["employeeId"] == "alex")
            buttons = {a["id"]: a for a in alex["body"]["actions"]}
            accept = {**buttons["accept"]["body"], "sourceId": "phase8-accept"}
            status, accepted = req(buttons["accept"]["url"], accept)
            again, repeated = req(buttons["accept"]["url"], accept)
            check("accept: timestamp, one event, replay, work remains incomplete", status == again == 200 and accepted == repeated and
                  count("SELECT COUNT(*) n FROM outbox WHERE type='acceptance'") == 1 and
                  state()["package"]["assignments"][0].get("acceptedAt") == accepted["body"]["acceptedAt"] and state()["schedule"][0]["status"] != "complete")
            check("accept: wrong employee rejected", req(buttons["accept"]["url"], {"employeeId": "sam", "sourceId": "wrong"})[0] == 400)
            status, _ = req(buttons["snooze"]["url"], {**buttons["snooze"]["body"], "sourceId": "phase8-snooze"})
            req("/demo/action", {"action": "advance", "minutes": 4})
            repeats = lambda: [i for i in req("/hooks/outbox?callerId=smoke&types=assignment")[1]["items"] if i.get("repeatOf") == alex["id"]]
            check("notification snooze: no repeat before five simulated minutes", status == 200 and not repeats())
            req("/demo/action", {"action": "advance", "minutes": 1})
            check("notification snooze: repeat at five minutes", len(repeats()) == 1)
            for index in (2, 3):
                req(buttons["snooze"]["url"], {**buttons["snooze"]["body"], "sourceId": "phase8-snooze-" + str(index)})
            status, error = req(buttons["snooze"]["url"], {**buttons["snooze"]["body"], "sourceId": "phase8-snooze-4"})
            check("notification snooze: fourth refused with delay guidance", status == 409 and "delay" in error.get("error", ""))
            sam = next(item for item in assignments if item["body"]["employeeId"] == "sam")
            delay = next(a for a in sam["body"]["actions"] if a["id"] == "delay")
            check("delay: missing note rejected", req(delay["url"], {**delay["body"], "minutes": 30, "sourceId": "no-note"})[0] == 400)
            old_ids = [r["id"] for r in state()["reminders"] if r["taskId"] == "transport" and r["status"] == "scheduled"]
            data = {**delay["body"], "minutes": 30, "note": "truck in the shop", "sourceId": "phase8-delay"}
            status, delayed = req(delay["url"], data)
            again, repeated = req(delay["url"], data)
            check("delay: one Phase 3 override, conflict includes note, reminders superseded", status == again == 200 and delayed == repeated and
                  count("SELECT COUNT(*) n FROM availability_overrides") == 1 and
                  any("truck in the shop" in i["body"]["plainText"] for i in delayed.get("conflicts", [])) and
                  all(r["status"] == "superseded" for r in state()["reminders"] if r["id"] in old_ids))

            # A background reader holds the real stream open while ordinary hooks run.
            def open_stream(after, last_id=None):
                headers = {"Last-Event-ID": str(last_id)} if last_id is not None else {}
                response = urlopen(Request(base + f"/hooks/stream?callerId=smoke&employeeId=alex&after={after}", headers=headers), timeout=20)
                events = queue.Queue()
                def read():
                    try:
                        with response:
                            for line in response:
                                if line.startswith(b"data: "):
                                    events.put(json.loads(line[6:]))
                    except (OSError, ValueError):
                        pass  # Disposable server shutdown closes the readers.
                threading.Thread(target=read, daemon=True).start()
                return events, response.headers.get_content_type()

            def await_assignment(events, seconds=3):
                deadline = time.monotonic() + seconds
                seen = []
                while time.monotonic() < deadline:
                    try:
                        item = events.get(timeout=max(0.01, deadline-time.monotonic()))
                    except queue.Empty:
                        break
                    seen.append(item)
                    if item["type"] == "assignment":
                        break
                return seen

            top = count("SELECT MAX(cursor) n FROM outbox")
            events, content_type = open_stream(top)
            began = time.monotonic()
            health = req("/health")[0]
            check("stream: text/event-stream; health responds within one second", content_type == "text/event-stream" and health == 200 and time.monotonic()-began < 1)
            changed = copy.deepcopy(fixture)
            changed["revision"] = 2
            changed["employees"][0]["availability"][0]["start"] = "2026-09-14T09:20:00-07:00"
            began = time.monotonic()
            req("/hooks/assignments", {"callerId": "smoke", **changed})
            received = await_assignment(events)
            check("stream: new assignment arrives within three seconds, Alex only", time.monotonic()-began < 3 and
                  any(i["type"] == "assignment" for i in received) and all(i["body"]["employeeId"] == "alex" for i in received))
            last_id = count("SELECT MAX(cursor) n FROM outbox")
            changed["revision"] = 3
            changed["employees"][0]["availability"][0]["start"] = "2026-09-14T09:25:00-07:00"
            req("/hooks/assignments", {"callerId": "smoke", **changed})
            resumed, _ = open_stream(0, last_id=last_id)
            replayed = await_assignment(resumed)
            check("stream: Last-Event-ID overrides after and replays only unseen events", bool(replayed) and all(i["cursor"] > last_id for i in replayed) and any(i["type"] == "assignment" for i in replayed))
            jordan_only = copy.deepcopy(fixture)
            jordan_only["incident"]["id"] = "jordan-only"
            jordan_only["workflow"].update(id="single-load", tasks=[{**fixture["workflow"]["tasks"][2], "dependsOn": []}])
            jordan_only["employees"] = [e for e in fixture["employees"] if e["id"] == "jordan"]
            jordan_only["assignments"] = [{**a, "incidentId": "jordan-only"} for a in fixture["assignments"] if a["taskId"] == "load"]
            top = count("SELECT MAX(cursor) n FROM outbox")
            isolated, _ = open_stream(top)
            req("/hooks/assignments", {"callerId": "smoke", **jordan_only})
            check("stream: Jordan-only incident sends nothing to Alex", not await_assignment(isolated, seconds=1.2) and
                  req(f"/hooks/outbox?callerId=smoke&employeeId=alex&after={top}")[1]["items"] == [])
            notification_items = req("/hooks/outbox?callerId=smoke&types=assignment,reminder,conflict")[1]["items"]
            from urllib.parse import parse_qs, urlparse
            links_ok = True
            for item in notification_items:
                action = next((a for a in item["body"]["actions"] if a["id"] == "open"), {})
                url = urlparse(action.get("url", ""))
                links_ok &= action.get("kind") == "link" and url.path == "/web/employee.html" and parse_qs(url.query) == {"employeeId": [item["body"]["employeeId"]], "package": [item["id"]]}
            with urlopen(base + buttons["open"]["url"], timeout=3) as response:
                check("open web: every notification links to its employee card; URL serves page", links_ok and response.status == 200 and response.headers.get_content_type() == "text/html")
            for path, mime in (("/web/employee.html?employeeId=alex", "text/html"), ("/web/sw.js", "text/javascript")):
                with urlopen(base + path, timeout=3) as response:
                    check("client: " + path + " served with correct type", response.status == 200 and response.headers.get_content_type() == mime and bool(response.read()))
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
