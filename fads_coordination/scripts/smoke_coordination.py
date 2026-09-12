"""Exercise a real disposable HTTP demo; never contacts external services."""

import json
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
        server = subprocess.Popen([sys.executable, "-m", "fads_coordination.demo", "--port", "0", "--db", str(Path(folder) / "demo.sqlite")], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
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
