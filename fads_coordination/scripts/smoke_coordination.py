"""Exercise a real disposable HTTP demo; never contacts external services."""

import copy
import json
import os
import selectors
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]


def main():
    with tempfile.TemporaryDirectory(prefix="fads-smoke-") as folder:
        server = subprocess.Popen([sys.executable, "-m", "fads_coordination.demo", "--port", "0", "--db", str(Path(folder) / "demo.sqlite")], cwd=ROOT, env={k:v for k,v in os.environ.items() if k not in ("FADS_WEBHOOK_URL","FADS_WEBHOOK_SECRET")}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(server.stdout, selectors.EVENT_READ)
                if not selector.select(timeout=10):
                    raise AssertionError("Demo did not start in ten seconds")
                line = server.stdout.readline().strip()
            if "http://127.0.0.1:" not in line:
                raise AssertionError("Server failed to start: " + server.stderr.read(2000))
            url = line.split("http://", 1)[1]
            base = "http://" + url

            def request(path, data=None, expected=200, headers=None):
                body = json.dumps(data).encode() if data is not None else None
                req = Request(base + path, data=body, headers={"Content-Type": "application/json", **(headers or {})})
                try:
                    with urlopen(req, timeout=10) as response:
                        status, result = response.status, json.loads(response.read())
                except HTTPError as exc:
                    status, result = exc.code, json.loads(exc.read())
                assert status == expected, (path, status, result)
                return result

            def action(name, **fields):
                return request("/demo/action", {"action": name, **fields})

            assert request("/health")["mode"] == "fixture"
            state = action("advance", minutes=1)
            note = state["notifications"][0]
            state = action("acknowledge", reminderId=note["reminderId"], employeeId=note["employeeId"])
            assert state["incidentStatus"] == "assigned"
            print("PASS HTTP: ready reminder and explicit acknowledgement; task remains unfinished")
            state = action("seed_history")
            cut = next(t for t in state["schedule"] if t["taskId"] == "cut")
            assert cut["estimatedMinutes"] == 30 and cut["nextEstimate"]["recommendedMinutes"] == 42
            state = action("replan", revision=state["package"]["revision"])
            assert next(t for t in state["schedule"] if t["taskId"] == "cut")["estimatedMinutes"] == 42
            eta = state["estimatedResolutionAt"]
            state = action("delay_driver", minutes=30, revision=state["package"]["revision"])
            assert state["estimatedResolutionAt"] > eta
            print("PASS HTTP: learned estimate requires explicit replan; availability changes ETA")
            lesson = {"key": "equipment-review", "workflowId": "branch-removal", "workflowVersion": 1,
                      "taskId": "cut", "context": "standard", "text": "Review assigned equipment before departure.",
                      "evidence": "Synthetic confirmed dispatcher feedback", "sourceId": "smoke-feedback", "confirmed": True}
            state = action("remember", lesson=lesson)
            assert len(next(t for t in state["schedule"] if t["taskId"] == "cut")["lessons"]) == 1
            assert not next(t for t in state["schedule"] if t["taskId"] == "load")["lessons"]
            request("/demo/action", {"action": "complete", "taskId": "cut", "actualMinutes": 40, "evidence": "test", "revision": state["package"]["revision"]}, expected=400)
            for task_id, actual in (("secure", 10), ("cut", 48), ("load", 20), ("transport", 30), ("verify", 10)):
                state = action("complete", taskId=task_id, actualMinutes=actual, waitingMinutes=0, scopeChanged=False,
                               evidence="Synthetic observed effort in HTTP test", revision=state["package"]["revision"])
            assert state["incidentStatus"] == "resolved"
            assert not any(r["status"] == "scheduled" for r in state["reminders"])
            outcome = next(o for o in state["outcomes"] if o["incident"] == "pine-street-001" and o["task"] == "cut")
            assert outcome["predicted"] == 42 and outcome["actual"] == 48
            print("PASS HTTP: prerequisite gate, all five completions, actual effort and resolution")
            lesson_id = state["lessons"][0]["id"]
            previous_time = state["now"]
            state = action("next_incident")
            assert state["now"] > previous_time, "Next incident must not reverse the clock"
            assert next(t for t in state["schedule"] if t["taskId"] == "cut")["lessons"]
            state = action("forget_lesson", id=lesson_id)
            assert not state["lessons"]
            request("/demo/action", {"action": "remember", "lesson": lesson}, expected=409)
            state = action("forget_outcome", id="demo-history-0")
            request("/demo/action", {"action": "seed_history"}, expected=409)
            print("PASS HTTP: next incident recalls scope; forgetting removes content and suppresses replay")
            request("/demo/action", {"action": "advance", "minutes": 1}, expected=403, headers={"Origin": "https://unrelated.example"})
            request("/hooks/assignments", {"schemaVersion": 1, "workflow": "bad"}, expected=400)
            request("/demo/action", {"action": "replan", "revision": 999}, expected=409)
            print("PASS HTTP: cross-origin writes, malformed input and stale revisions rejected")
            state = action("cancel", revision=state["package"]["revision"])
            assert state["incidentStatus"] == "cancelled"
            print("PASS: disposable HTTP integration complete; no external messages")

            # Phase 7: complete worker hook contract, using a fresh fixture case.
            reset = request("/demo/reset", {"callerId": "fixture-tester"})
            assert not reset["outcomes"] and not reset["lessons"] and not reset["proofs"]
            fixture = json.loads((ROOT / "fads_coordination/fixtures/branch-removal.json").read_text())
            fixture["incident"]["id"] = case = "hook-fixture-case"
            for assignment in fixture["assignments"]:
                assignment["incidentId"] = case
            cursor = request("/hooks/outbox?callerId=fixture-reader")["nextCursor"]
            request("/hooks/assignments", {"callerId": "fixture-dispatcher", **fixture})
            entries = request(f"/hooks/outbox?callerId=fixture-reader&after={cursor}&types=schedule_entry")["items"]
            assert len(entries) == 5 and all(i["incidentId"] == case for i in entries)
            request("/hooks/assignments", {"callerId": "fixture-dispatcher", **fixture})
            assert len(request(f"/hooks/outbox?callerId=fixture-reader&after={cursor}&types=schedule_entry")["items"]) == 5
            # A GET lets the local server's next service tick process the new case.
            request("/health")
            snapshot = request(f"/hooks/state/{case}?callerId=fixture-reader")["body"]
            # Existing recipient cooldown may defer this new case; move fixture clock.
            for _ in range(4):
                if snapshot["notifications"]:
                    break
                action("advance", minutes=5)
                request("/health")
                snapshot = request(f"/hooks/state/{case}?callerId=fixture-reader")["body"]
            notification = snapshot["notifications"][0]
            request(f"/hooks/reminders/{notification['reminderId']}/acknowledge", {"employeeId": notification["employeeId"]})
            assert request(f"/hooks/state/{case}?callerId=fixture-reader")["body"]["incidentStatus"] == "assigned"
            print("PASS FIXTURE hooks: package in, five schedules, reminder out, acknowledgement without completion")
            override = {"employeeId":"sam", "kind":"day_off", "incidentId":case,
                        "window":{"start":fixture["startAt"],"end":"2026-09-14T17:00:00-07:00"},
                        "reason":"Fixture day off", "sourceId":"fixture-dayoff"}
            conflict = request("/hooks/employees/sam/availability", override)
            assert conflict == request("/hooks/employees/sam/availability", override)
            assert len(conflict["conflicts"]) == 1
            assert conflict["conflicts"][0]["body"]["affectedTasks"] == ["transport", "verify"]
            blocked = request(f"/hooks/state/{case}?callerId=fixture-reader")["body"]
            assert blocked["estimatedResolutionAt"] is None and blocked["package"]["revision"] == 1
            replacement = copy.deepcopy(fixture["employees"][2]); replacement.update(id="pat",name="Pat")
            fixture["employees"].append(replacement)
            fixture["assignments"][3]["employeeId"] = "pat"
            fixture["revision"] = 2
            restored = request("/hooks/assignments", {"callerId":"fixture-dispatcher",**fixture})
            assert all(t["state"] == "scheduled" for t in restored["schedule"])
            print("PASS FIXTURE hooks: day off, conflict out, upstream replacement in; override retained")
            proof = {"employeeId":"alex", "sourceId":"fixture-proof", "proof":{"kind":"image","ref":"fixture://unread-proof.png"}}
            receipt = request(f"/hooks/tasks/{case}/secure/proof", proof)
            assert receipt == request(f"/hooks/tasks/{case}/secure/proof", proof)
            done = {"employeeId":"alex", "sourceId":"fixture-done", "checklist":[{"item":"Assigned work done","done":True}]}
            completion = request(f"/hooks/tasks/{case}/secure/done", done)
            assert completion == request(f"/hooks/tasks/{case}/secure/done", done)
            assert completion["body"]["actualMinutes"] is None
            assert completion["body"]["proofs"][0]["ref"] == proof["proof"]["ref"]
            page = request("/hooks/outbox?callerId=fixture-reader&types=completion")
            assert [i["id"] for i in page["items"]] == [completion["id"]]
            confirm = request("/hooks/workflows/branch-removal/1/confirm", {"confirmedBy":"fixture-reviewer"})
            assert confirm["status"] == "active"
            print("PASS FIXTURE hooks: proof reference, unknown actual, completion out, catalog confirmation")
            latest = request("/hooks/outbox?callerId=fixture-reader")["nextCursor"]
            reset = request("/demo/reset", {"callerId":"fixture-tester"})
            assert reset["package"]["revision"] == 1 and reset["incidentStatus"] == "assigned"
            assert not reset["outcomes"] and not reset["proofs"]
            assert len(request(f"/hooks/outbox?callerId=fixture-reader&after={latest}")["items"]) == 6
            print("PASS FIXTURE reset: cleared local test state and memory, restored fixture, retained forward cursor")
            print("PASS PHASE 7: complete fixture/local-sink hook walkthrough; no external service calls")
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
            server.stdout.close()
            server.stderr.close()


if __name__ == "__main__":
    main()
