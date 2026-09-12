"""Loopback-only, simulated demo server. Run: python3 -m fads_coordination.demo."""

import argparse
import json
import sys
import uuid
from datetime import datetime, timedelta
from http.server import HTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

from .api import HookHandler, deliver_webhooks
from .core import Coordination, Conflict, InvalidInput, canonical, iso, number, stamp

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).parent / "fixtures" / "branch-removal.json"


def settings(app):
    return {r[0]: r[1] for r in app.db.execute("SELECT key,value FROM settings")}


def set_values(app, **values):
    with app.db:
        app.db.executemany("INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", ((name, str(value)) for name, value in values.items()))


def initialize(path):
    app = Coordination(path)
    try:
        if "incident" not in settings(app):
            package = json.loads(FIXTURE.read_text())
            app.put_package(package, stamp(package["startAt"]))
            set_values(app, workspace=package["workspaceId"], incident=package["incident"]["id"], clock=iso(package["startAt"]))
    finally:
        app.close()


def action(app, data):
    config = settings(app)
    workspace, incident, now = config["workspace"], config["incident"], stamp(config["clock"])
    name = data.get("action")
    package = app._package(workspace, incident)
    if name == "advance":
        now += timedelta(minutes=number(data.get("minutes"), "minutes", 1, 480))
    elif name == "acknowledge":
        app.acknowledge(workspace, data.get("reminderId"), data.get("employeeId"), now)
    elif name == "snooze":
        app.snooze(workspace, data.get("reminderId"), data.get("employeeId"), data.get("until"), now)
    elif name == "complete":
        actual = number(data.get("actualMinutes"), "actualMinutes", 1, 480)
        waiting = number(data.get("waitingMinutes", 0), "waitingMinutes", 0, 480)
        task = next((t for t in app.plan(package, now) if t["taskId"] == data.get("taskId")), None)
        if task is None or task["state"] == "blocked":
            raise InvalidInput("Task has no feasible work window")
        # Explicitly simulate performing this task; actual effort is supplied by
        # the dispatcher, never inferred from elapsed wall-clock time.
        started_at = max(now, stamp(task["startAt"]))
        completed_at = started_at + timedelta(minutes=actual + waiting)
        app.complete(workspace, incident, data.get("taskId"), actual, waiting,
                     data.get("scopeChanged", False), data.get("evidence", ""), completed_at, data.get("revision"), started_at)
        now = completed_at
    elif name == "replan":
        app.replan(workspace, incident, now, data.get("revision"))
    elif name == "cancel":
        app.cancel(workspace, incident, now, data.get("revision"))
    elif name == "delay_driver":
        if data.get("revision") != package["revision"]:
            raise Conflict("Plan changed; refresh first")
        driver = next((e for e in package["employees"] if "transport" in e["skills"]), None)
        if not driver or not driver["availability"]:
            raise InvalidInput("No driver availability to change")
        delta = timedelta(minutes=number(data.get("minutes", 30), "minutes", 1, 240))
        for window in driver["availability"]:
            window["start"] = iso(stamp(window["start"]) + delta)
        package["revision"] += 1
        app.put_package(package, now)
    elif name == "remember":
        app.remember(workspace, data.get("lesson", {}), now)
    elif name == "forget_lesson":
        app.forget_lesson(workspace, data.get("id"))
    elif name == "forget_outcome":
        app.forget_outcome(workspace, data.get("id"))
    elif name == "seed_history":
        # Fixed, labeled mechanism fixtures; never presented as actual employee
        # performance or evidence of real-world predictive accuracy.
        for index, minutes in enumerate((42, 54, 48, 66, 60)):
            app.record_outcome(workspace, {
                "id": f"demo-history-{index}", "incidentId": f"synthetic-{index}",
                "taskId": "cut", "workflowId": "branch-removal", "workflowVersion": 1,
                "context": "standard", "baselineMinutes": 30, "actualMinutes": minutes,
                "waitingMinutes": 0, "scopeChanged": False,
                "evidence": "Synthetic mechanism fixture; not observed crew performance",
            }, now)
    elif name == "next_incident":
        if any(a["status"] != "complete" for a in package["assignments"]):
            raise InvalidInput("Resolve this incident before starting the next demo")
        package = json.loads(FIXTURE.read_text())
        zone = ZoneInfo(package["timeZone"])
        baseline = stamp(package["startAt"]).astimezone(zone)
        next_start = datetime.combine(now.astimezone(zone).date() + timedelta(days=1), baseline.timetz(), zone)
        shift = next_start - baseline
        package["startAt"] = iso(next_start)
        for employee in package["employees"]:
            for window in employee["availability"]:
                for bound in ("start", "end"):
                    window[bound] = iso(stamp(window[bound]).astimezone(zone) + shift)
        incident = "pine-street-" + uuid.uuid4().hex[:8]
        package["incident"]["id"] = incident
        for assignment in package["assignments"]:
            assignment["incidentId"] = incident
        now = stamp(package["startAt"])
        app.put_package(package, now)
    else:
        raise InvalidInput("Unknown demo action")
    set_values(app, incident=incident, clock=iso(now))
    return app.tick(workspace, incident, now)


class DemoServer(HTTPServer):
    # Single request dispatcher; library transactions also protect concurrent
    # callers. A real deployment needs its own authentication and worker host.
    def service_actions(self):
        app = Coordination(self.database)
        try:
            config = settings(app)
            app.tick(config["workspace"], config["incident"], stamp(config["clock"]))
            deliver_webhooks(app)
        except (InvalidInput, Conflict) as exc:
            print(f"Scheduler needs attention: {exc}", file=sys.stderr)
        finally:
            app.close()


class Handler(HookHandler):
    def demo_get(self, path, app):
        if path == "/":
            body = (Path(__file__).parent / "web" / "index.html").read_bytes()
            self.send_response(200)
            for name, value in (("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(body))),
                                ("Cache-Control", "no-store"), ("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'")):
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)
            return True
        if path == "/demo/state":
            config = settings(app)
            self.reply(200, app.state(config["workspace"], config["incident"], stamp(config["clock"])))
            return True
        return False

    def demo_post(self, path, app, data):
        if path == "/demo/action":
            return action(app, data)
        raise InvalidInput("Unknown demo endpoint")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--db", type=Path, default=ROOT / ".fads" / "demo.sqlite")
    args = parser.parse_args()
    initialize(args.db)
    server = DemoServer(("127.0.0.1", args.port), Handler)
    server.database = args.db
    print(f"FADS simulated coordination: http://127.0.0.1:{server.server_port}", flush=True)
    print("Demo clock advances only through the controls. No external messages are sent.", flush=True)
    try:
        server.serve_forever(poll_interval=2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
