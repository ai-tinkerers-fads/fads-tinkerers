"""A deterministic, local-only coordination slice; no model or messaging credentials.

Callers supply approved workflow data and confirmed assignments. This module
forecasts those assignments, delivers simulated in-app reminders, and records
explicit feedback. It never invents procedures or chooses a different employee.
"""

import hashlib
import json
import math
import sqlite3
import statistics
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class InvalidInput(ValueError):
    pass


class Conflict(ValueError):
    pass


def stamp(value):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise InvalidInput("Expected an ISO timestamp with an offset") from exc
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise InvalidInput("A timestamp needs an explicit time-zone offset; dates alone are unresolved")
    return value.astimezone(timezone.utc)


def iso(value):
    return stamp(value).isoformat()


def required(data, key, limit=200):
    if not isinstance(data, dict):
        raise InvalidInput("Expected a JSON object")
    value = data.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise InvalidInput(f"{key} must be nonempty text of at most {limit} characters")
    return value.strip()


def number(value, name, minimum=0, maximum=100000):
    if type(value) is not int or not minimum <= value <= maximum:
        raise InvalidInput(f"{name} must be an integer from {minimum} to {maximum}")
    return value


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def key(*parts):
    return hashlib.sha256(canonical(parts).encode()).hexdigest()[:32]


def validate(package):
    """Return topological task order. Reject malformed snapshots before writes."""
    if not isinstance(package, dict) or type(package.get("schemaVersion")) is not int or package.get("schemaVersion") != 1:
        raise InvalidInput("schemaVersion must be 1")
    required(package, "workspaceId")
    number(package.get("revision"), "revision", 1)
    stamp(package.get("startAt"))
    try:
        ZoneInfo(required(package, "timeZone"))
    except ZoneInfoNotFoundError as exc:
        raise InvalidInput("timeZone must be an IANA zone") from exc
    required(package, "context")
    if type(package.get("cancelled", False)) is not bool:
        raise InvalidInput("cancelled must be boolean")
    incident = package.get("incident", {})
    incident_id = required(incident, "id")
    required(incident.get("location", {}), "address", 500)
    workflow = package.get("workflow", {})
    required(workflow, "id")
    number(workflow.get("version"), "workflow.version", 1)
    for data, field in ((workflow, "tasks"), (package, "employees"), (package, "assignments")):
        if not isinstance(data.get(field), list):
            raise InvalidInput(f"{field} must be an array")
    tasks, employees, assignments = {}, {}, {}
    for task in workflow.get("tasks", []):
        task_id = required(task, "id")
        if task_id in tasks:
            raise InvalidInput("Duplicate workflow task")
        required(task, "name", 300)
        number(task.get("estimatedMinutes"), "estimatedMinutes", 1, 10080)
        number(task.get("preparationLeadMinutes", 15), "preparationLeadMinutes", 0, 1440)
        deps = task.get("dependsOn", [])
        if not isinstance(deps, list) or any(not isinstance(d, str) for d in deps):
            raise InvalidInput("dependsOn must be a list of task IDs")
        tasks[task_id] = task
    if not tasks or len(tasks) > 100:
        raise InvalidInput("Provide between 1 and 100 approved workflow tasks")
    for employee in package.get("employees", []):
        employee_id = required(employee, "id")
        if employee_id in employees:
            raise InvalidInput("Duplicate employee")
        required(employee, "name")
        for field in ("skills", "equipmentAccess"):
            if not isinstance(employee.get(field, []), list) or any(not isinstance(v, str) for v in employee.get(field, [])):
                raise InvalidInput(f"{field} must be a list of strings")
        if not isinstance(employee.get("availability"), list):
            raise InvalidInput("availability must be an array of work windows")
        for window in employee["availability"]:
            if not isinstance(window, dict):
                raise InvalidInput("Expected an availability window")
            if stamp(window.get("start")) >= stamp(window.get("end")):
                raise InvalidInput("Availability start must precede end")
        employees[employee_id] = employee
    for assignment in package.get("assignments", []):
        task_id = required(assignment, "taskId")
        employee_id = required(assignment, "employeeId")
        if assignment.get("incidentId") != incident_id or task_id not in tasks or employee_id not in employees:
            raise InvalidInput("Assignment references an unknown incident, task or employee")
        if task_id in assignments:
            raise InvalidInput("Each task needs exactly one confirmed assignee in this prototype")
        if assignment.get("status") not in ("pending", "ready", "in_progress", "complete"):
            raise InvalidInput("Unknown assignment status")
        if assignment["status"] == "complete":
            stamp(assignment.get("completedAt"))
        if assignment["status"] == "in_progress":
            stamp(assignment.get("startedAt"))
        if "remainingMinutes" in assignment:
            number(assignment["remainingMinutes"], "remainingMinutes", 1, 10080)
            stamp(assignment.get("remainingUpdatedAt"))
        task, employee = tasks[task_id], employees[employee_id]
        if task.get("requiredSkill") and task["requiredSkill"] not in employee.get("skills", []):
            raise InvalidInput(f"{employee_id} lacks required skill for {task_id}")
        equipment = task.get("requiredEquipment", [])
        if not isinstance(equipment, list) or any(not isinstance(e, str) for e in equipment):
            raise InvalidInput("requiredEquipment must be a list of equipment capabilities")
        if not set(equipment).issubset(employee.get("equipmentAccess", [])):
            raise InvalidInput(f"{employee_id} lacks required equipment for {task_id}")
        assignments[task_id] = assignment
    if set(assignments) != set(tasks):
        raise InvalidInput("Every approved task needs an assignment")
    ordered, visiting, visited = [], set(), set()

    def visit(task_id):
        if task_id not in tasks:
            raise InvalidInput("Unknown dependency")
        if task_id in visiting:
            raise InvalidInput("Workflow dependencies contain a cycle")
        if task_id in visited:
            return
        visiting.add(task_id)
        for dep in tasks[task_id].get("dependsOn", []):
            visit(dep)
        visiting.remove(task_id)
        visited.add(task_id)
        ordered.append(tasks[task_id])

    for task_id in tasks:
        visit(task_id)
    for task_id, assignment in assignments.items():
        if assignment["status"] in ("in_progress", "complete"):
            deps = tasks[task_id].get("dependsOn", [])
            if any(assignments[d]["status"] != "complete" for d in deps):
                raise InvalidInput("Started or completed work needs completed prerequisites")
            event_time = assignment.get("startedAt", assignment.get("completedAt"))
            if any(stamp(assignments[d]["completedAt"]) > stamp(event_time) for d in deps):
                raise InvalidInput("Work cannot precede its prerequisites")
            if assignment["status"] == "complete" and stamp(event_time) > stamp(assignment["completedAt"]):
                raise InvalidInput("Work cannot finish before it starts")
    return ordered


class Coordination:
    """SQLite owns local truth. A single service instance is used per HTTP request.

    SQLite transactions serialize mutations. Remote transports must implement
    reconciliation separately; the built-in sink is atomic simulated delivery.
    """

    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS packages (
            workspace TEXT, incident TEXT, revision INTEGER NOT NULL, body TEXT NOT NULL,
            PRIMARY KEY(workspace,incident));
        CREATE TABLE IF NOT EXISTS forecasts (
            workspace TEXT, incident TEXT, task TEXT, revision INTEGER, body TEXT,
            PRIMARY KEY(workspace,incident,task,revision));
        CREATE TABLE IF NOT EXISTS reminders (
            id TEXT PRIMARY KEY, workspace TEXT, incident TEXT, task TEXT, employee TEXT,
            revision INTEGER, kind TEXT, due_at TEXT, start_at TEXT, end_at TEXT,
            status TEXT, snooze_until TEXT, reason TEXT, acknowledged_at TEXT);
        CREATE INDEX IF NOT EXISTS reminders_due ON reminders(workspace,incident,status,due_at);
        CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY, reminder_id TEXT UNIQUE REFERENCES reminders(id),
            workspace TEXT, employee TEXT, body TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS outcomes (
            workspace TEXT, id TEXT, incident TEXT, task TEXT, workflow TEXT,
            workflow_version INTEGER, context TEXT, baseline INTEGER, predicted INTEGER, actual INTEGER,
            waiting INTEGER, scope_changed INTEGER, evidence TEXT, created_at TEXT,
            PRIMARY KEY(workspace,id), UNIQUE(workspace,incident,task));
        CREATE TABLE IF NOT EXISTS lessons (
            workspace TEXT, id TEXT, rule_key TEXT, workflow TEXT, workflow_version INTEGER,
            task TEXT, context TEXT, text TEXT, evidence TEXT, source_id TEXT,
            version INTEGER, expires_at TEXT, updated_at TEXT,
            PRIMARY KEY(workspace,id));
        CREATE TABLE IF NOT EXISTS lesson_sources (
            workspace TEXT, lesson_id TEXT, source_id TEXT,
            PRIMARY KEY(workspace,source_id));
        CREATE TABLE IF NOT EXISTS suppressed (
            workspace TEXT, kind TEXT, source_id TEXT, PRIMARY KEY(workspace,kind,source_id));
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
        """)

    def close(self):
        self.db.close()

    def _begin(self):
        self.db.execute("BEGIN IMMEDIATE")

    def get_package(self, workspace, incident):
        row = self.db.execute("SELECT body FROM packages WHERE workspace=? AND incident=?", (workspace, incident)).fetchone()
        return json.loads(row[0]) if row else None

    def _package(self, workspace, incident):
        package = self.get_package(workspace, incident)
        if package is None:
            raise InvalidInput("Unknown incident")
        return package

    def put_package(self, package, now):
        validate(package)
        stamp(now)
        with self.db:
            self._begin()
            self._put(package, now)
        return self.state(package["workspaceId"], package["incident"]["id"], now)

    def _put(self, package, now, refresh_estimates=False):
        workspace, incident = package["workspaceId"], package["incident"]["id"]
        old = self.get_package(workspace, incident)
        if any(a["status"] == "complete" and stamp(a["completedAt"]) > stamp(now) for a in package["assignments"]):
            raise InvalidInput("Completed work cannot have a future completion timestamp")
        if any(stamp(a[field]) > stamp(now) for a in package["assignments"] for field in ("startedAt", "remainingUpdatedAt") if field in a):
            raise InvalidInput("Observed work timestamps cannot be in the future")
        if old:
            if package["revision"] < old["revision"]:
                raise Conflict("Stale assignment revision")
            if package["revision"] == old["revision"]:
                if canonical(package) != canonical(old):
                    raise Conflict("Same revision has different content")
                return
            if (old["workflow"]["id"], old["workflow"]["version"]) == (package["workflow"]["id"], package["workflow"]["version"]) and canonical(old["workflow"]) != canonical(package["workflow"]):
                raise Conflict("Change the workflow version when changing its approved definition")
            self.db.execute("UPDATE reminders SET status=?,reason=? WHERE workspace=? AND incident=? AND status IN ('scheduled','delivered')", ("cancelled" if package.get("cancelled") else "superseded", "Incident cancelled" if package.get("cancelled") else "Assignment or plan changed", workspace, incident))
        self.db.execute("INSERT INTO packages VALUES (?,?,?,?) ON CONFLICT(workspace,incident) DO UPDATE SET revision=excluded.revision,body=excluded.body", (workspace, incident, package["revision"], canonical(package)))
        workflow = package["workflow"]
        assignments = {a["taskId"]: a for a in package["assignments"]}
        for task in workflow["tasks"]:
            profile = self.estimate(workspace, workflow["id"], workflow["version"], task["id"], package["context"], task["estimatedMinutes"])
            same_workflow = old and (old["workflow"]["id"], old["workflow"]["version"]) == (workflow["id"], workflow["version"])
            if same_workflow and (not refresh_estimates or assignments[task["id"]]["status"] in ("in_progress", "complete")):
                prior = self.db.execute("SELECT body FROM forecasts WHERE workspace=? AND incident=? AND task=? AND revision=?", (workspace, incident, task["id"], old["revision"])).fetchone()
                if prior:
                    profile = json.loads(prior[0])
            self.db.execute("INSERT INTO forecasts VALUES (?,?,?,?,?)", (workspace, incident, task["id"], package["revision"], canonical(profile)))
        self._refresh(package, now)

    def replan(self, workspace, incident, now, expected_revision):
        with self.db:
            self._begin()
            package = self._package(workspace, incident)
            if package["revision"] != expected_revision:
                raise Conflict("Plan changed; refresh before replanning")
            package["revision"] += 1
            self._put(package, now, refresh_estimates=True)
        return self.state(workspace, incident, now)

    def cancel(self, workspace, incident, now, expected_revision):
        with self.db:
            self._begin()
            package = self._package(workspace, incident)
            if package["revision"] != expected_revision:
                raise Conflict("Plan changed; refresh before cancelling")
            package["cancelled"] = True
            package["revision"] += 1
            self._put(package, now)
        return self.state(workspace, incident, now)

    def estimate(self, workspace, workflow, version, task, context, baseline):
        rows = self.db.execute("SELECT id,baseline,actual FROM outcomes WHERE workspace=? AND workflow=? AND workflow_version=? AND task=? AND context=? AND scope_changed=0 ORDER BY created_at DESC,id DESC LIMIT 50", (workspace, workflow, version, task, context)).fetchall()
        ratios = [r["actual"] / r["baseline"] for r in rows]
        count = len(ratios)
        # Five baseline-equivalent observations temper small samples. This is
        # a transparent heuristic, not a confidence interval or causal model.
        factor = 1 + (statistics.median(ratios) - 1) * count / (count + 5) if count >= 5 else 1
        return {"baselineMinutes": baseline, "recommendedMinutes": max(1, math.ceil(baseline * factor)),
                "sampleCount": count, "minimumSamples": 5, "applied": count >= 5,
                "observedRangeMinutes": [math.floor(baseline * min(ratios)), math.ceil(baseline * max(ratios))] if ratios else None,
                "evidenceIds": [r["id"] for r in rows[:10]], "sampleWindow": 50, "method": "Median effort ratio, shrunk toward template; not calibrated"}

    def lessons(self, workspace, workflow, version, task, context, now):
        rows = self.db.execute("SELECT * FROM lessons WHERE workspace=? AND workflow=? AND workflow_version=? AND task=? AND context=? AND (expires_at IS NULL OR expires_at>?) ORDER BY updated_at DESC,id LIMIT 5", (workspace, workflow, version, task, context, iso(now))).fetchall()
        return [dict(r) for r in rows]

    def plan(self, package, now):
        ordered = validate(package)
        now = stamp(now)
        employees = {e["id"]: e for e in package["employees"]}
        assignments = {a["taskId"]: a for a in package["assignments"]}
        scheduled, busy = {}, {}
        workflow, workspace = package["workflow"], package["workspaceId"]
        for task in ordered:
            task_id = task["id"]
            assignment = assignments[task_id]
            employee = employees[assignment["employeeId"]]
            next_profile = self.estimate(workspace, workflow["id"], workflow["version"], task_id, package["context"], task["estimatedMinutes"])
            frozen = self.db.execute("SELECT body FROM forecasts WHERE workspace=? AND incident=? AND task=? AND revision=?", (workspace, package["incident"]["id"], task_id, package["revision"])).fetchone()
            profile = json.loads(frozen[0]) if frozen else next_profile
            result = {"taskId": task_id, "name": task["name"], "employeeId": employee["id"], "employeeName": employee["name"],
                      "status": assignment["status"], "dependsOn": task.get("dependsOn", []),
                      "estimatedMinutes": profile["recommendedMinutes"], "estimateEvidence": profile, "nextEstimate": next_profile,
                      "lessons": self.lessons(workspace, workflow["id"], workflow["version"], task_id, package["context"], now),
                      "state": "scheduled", "startAt": None, "endAt": None, "prepareAt": None, "reason": None}
            if assignment["status"] == "complete":
                end = stamp(assignment["completedAt"])
                start = stamp(assignment.get("startedAt", assignment["completedAt"]))
            elif package.get("cancelled"):
                result.update(state="blocked", reason="Incident cancelled")
                scheduled[task_id] = result
                continue
            elif any(scheduled[d]["endAt"] is None for d in result["dependsOn"]):
                result.update(state="blocked", reason="A prerequisite has no feasible schedule")
                scheduled[task_id] = result
                continue
            else:
                earliest = max([stamp(package["startAt"]), now] + [stamp(scheduled[d]["endAt"]) for d in result["dependsOn"]])
                duration = timedelta(minutes=profile["recommendedMinutes"])
                if assignment["status"] == "in_progress":
                    start = stamp(assignment["startedAt"])
                    remaining = assignment.get("remainingMinutes")
                    end = stamp(assignment["remainingUpdatedAt"]) + timedelta(minutes=remaining) if remaining is not None else start + duration
                    if end <= now:
                        result.update(state="blocked", reason="Work is overdue; report remaining minutes or completion")
                        scheduled[task_id] = result
                        continue
                else:
                    slot = self._slot(employee.get("availability", []), earliest, duration, busy.get(employee["id"], []))
                    if slot is None:
                        result.update(state="blocked", reason="No available work window fits this task")
                        scheduled[task_id] = result
                        continue
                    start, window_start = slot
                    end = start + duration
                    lead = timedelta(minutes=task.get("preparationLeadMinutes", 15))
                    result["prepareAt"] = iso(max(window_start, start - lead))
            result.update(startAt=iso(start), endAt=iso(end))
            if assignment["status"] != "complete":
                busy.setdefault(employee["id"], []).append((start, end))
            scheduled[task_id] = result
        return list(scheduled.values())

    @staticmethod
    def _slot(windows, earliest, duration, busy):
        for window in sorted(windows, key=lambda w: stamp(w["start"])):
            window_start, window_end = stamp(window["start"]), stamp(window["end"])
            start = max(earliest, window_start)
            for busy_start, busy_end in sorted(busy):
                if start < busy_end and start + duration > busy_start:
                    start = busy_end
            if start + duration <= window_end:
                return start, window_start
        return None

    def _refresh(self, package, now):
        workspace, incident, revision = package["workspaceId"], package["incident"]["id"], package["revision"]
        for task in self.plan(package, now):
            if task["state"] == "blocked" or task["status"] in ("complete", "in_progress"):
                self.db.execute("UPDATE reminders SET status='cancelled',reason=? WHERE workspace=? AND incident=? AND task=? AND revision=? AND status IN ('scheduled','delivered')", (task["reason"] or "Task started or completed", workspace, incident, task["taskId"], revision))
                continue
            for kind, due in (("prepare", task["prepareAt"]), ("ready", task["startAt"])):
                reminder_id = key(workspace, incident, revision, task["taskId"], kind)
                self.db.execute("""INSERT INTO reminders VALUES (?,?,?,?,?,?,?,?,?,?,'scheduled',NULL,NULL,NULL)
                    ON CONFLICT(id) DO UPDATE SET due_at=excluded.due_at,start_at=excluded.start_at,end_at=excluded.end_at
                    WHERE reminders.status='scheduled'""", (reminder_id, workspace, incident, task["taskId"], task["employeeId"], revision, kind, due, task["startAt"], task["endAt"]))

    def tick(self, workspace, incident, now):
        now = stamp(now)
        with self.db:
            self._begin()
            package = self._package(workspace, incident)
            self._refresh(package, now)
            assignments = {a["taskId"]: a for a in package["assignments"]}
            tasks = {t["taskId"]: t for t in self.plan(package, now)}
            due = self.db.execute("SELECT * FROM reminders WHERE workspace=? AND incident=? AND status='scheduled' AND due_at<=? AND (snooze_until IS NULL OR snooze_until<=?) ORDER BY CASE kind WHEN 'ready' THEN 0 ELSE 1 END,due_at,id", (workspace, incident, iso(now), iso(now))).fetchall()
            for reminder in due:
                task, assignment = tasks[reminder["task"]], assignments[reminder["task"]]
                if reminder["revision"] != package["revision"] or reminder["employee"] != assignment["employeeId"] or assignment["status"] not in ("pending", "ready") or task["state"] == "blocked":
                    continue
                dependencies_done = all(assignments[d]["status"] == "complete" for d in task["dependsOn"])
                if reminder["kind"] == "ready" and not dependencies_done:
                    continue
                if reminder["kind"] == "prepare" and dependencies_done and stamp(task["startAt"]) <= now:
                    self.db.execute("UPDATE reminders SET status='superseded',reason='Ready reminder covers preparation' WHERE id=?", (reminder["id"],))
                    continue
                employee = next(e for e in package["employees"] if e["id"] == reminder["employee"])
                if not any(stamp(w["start"]) <= now < stamp(w["end"]) for w in employee["availability"]):
                    continue  # Only explicit available work windows permit notifications.
                recent = self.db.execute("SELECT created_at FROM notifications WHERE workspace=? AND employee=? AND created_at>? ORDER BY created_at DESC", (workspace, reminder["employee"], iso(now - timedelta(hours=1)))).fetchall()
                if len(recent) >= 4 or (recent and stamp(recent[0][0]) > now - timedelta(minutes=5)):
                    continue
                zone = ZoneInfo(package["timeZone"])
                time_text = stamp(task["startAt"]).astimezone(zone).strftime("%a %H:%M %Z")
                body = f"{'Ready' if reminder['kind'] == 'ready' else 'Prepare'}: {task['name']} · {time_text} · about {task['estimatedMinutes']} min. {package['incident']['location']['address']}."
                if reminder["kind"] == "prepare" and not dependencies_done:
                    body += " Preparation only; wait for prerequisite completion before starting."
                # Notes are retrieved by the UI at read time, never copied into
                # notification history, so forgetting a note actually removes it.
                # The simulated inbox and send receipt commit together. This is
                # intentionally NOT a remote sender with exactly-once claims.
                self.db.execute("INSERT OR IGNORE INTO notifications VALUES (?,?,?,?,?,?)", (str(uuid.uuid4()), reminder["id"], workspace, reminder["employee"], body, iso(now)))
                self.db.execute("UPDATE reminders SET status='delivered' WHERE id=?", (reminder["id"],))
        return self.state(workspace, incident, now)

    def _owned_reminder(self, workspace, reminder_id, employee):
        row = self.db.execute("SELECT * FROM reminders WHERE workspace=? AND id=? AND employee=?", (workspace, reminder_id, employee)).fetchone()
        if not row:
            raise InvalidInput("Reminder is not assigned to this recipient")
        if row["status"] not in ("scheduled", "delivered", "acknowledged"):
            raise Conflict("Reminder is no longer active")
        return row

    def acknowledge(self, workspace, reminder_id, employee, now):
        with self.db:
            self._begin()
            row = self._owned_reminder(workspace, reminder_id, employee)
            if row["status"] == "scheduled":
                raise InvalidInput("Only a delivered reminder can be acknowledged")
            self.db.execute("UPDATE reminders SET status='acknowledged',acknowledged_at=COALESCE(acknowledged_at,?) WHERE id=?", (iso(now), reminder_id))

    def snooze(self, workspace, reminder_id, employee, until, now):
        until, now = stamp(until), stamp(now)
        with self.db:
            self._begin()
            row = self._owned_reminder(workspace, reminder_id, employee)
            if row["status"] != "scheduled":
                raise InvalidInput("Snooze a pending reminder; acknowledge one already delivered")
            if until <= max(now, stamp(row["due_at"]), stamp(row["snooze_until"]) if row["snooze_until"] else now) or until > stamp(row["start_at"]):
                raise InvalidInput("Snooze must delay the existing reminder and be no later than planned start")
            self.db.execute("UPDATE reminders SET snooze_until=?,reason='Recipient snoozed' WHERE id=?", (iso(until), reminder_id))

    def complete(self, workspace, incident, task_id, actual, waiting, scope_changed, evidence, now, expected_revision, started_at=None):
        number(actual, "actualMinutes")
        number(waiting, "waitingMinutes")
        required({"evidence": evidence}, "evidence", 1000)
        now = stamp(now)
        with self.db:
            self._begin()
            package = self._package(workspace, incident)
            if package["revision"] != expected_revision:
                raise Conflict("Plan changed; refresh before completing")
            if package.get("cancelled"):
                raise Conflict("Incident is cancelled")
            tasks = {t["id"]: t for t in package["workflow"]["tasks"]}
            assignments = {a["taskId"]: a for a in package["assignments"]}
            if task_id not in tasks:
                raise InvalidInput("Unknown task")
            if assignments[task_id]["status"] == "complete":
                raise Conflict("Task already complete")
            if any(assignments[d]["status"] != "complete" for d in tasks[task_id].get("dependsOn", [])):
                raise InvalidInput("Complete prerequisites first")
            if any(stamp(assignments[d]["completedAt"]) > now for d in tasks[task_id].get("dependsOn", [])):
                raise InvalidInput("Completion cannot precede its prerequisites")
            if started_at is not None:
                start = stamp(started_at)
                if start > now or any(stamp(assignments[d]["completedAt"]) > start for d in tasks[task_id].get("dependsOn", [])):
                    raise InvalidInput("Recorded start must follow prerequisites and precede completion")
                assignments[task_id]["startedAt"] = iso(start)
            assignments[task_id]["status"] = "complete"
            assignments[task_id]["completedAt"] = iso(now)
            workflow = package["workflow"]
            forecast = json.loads(self.db.execute("SELECT body FROM forecasts WHERE workspace=? AND incident=? AND task=? AND revision=?", (workspace, incident, task_id, package["revision"])).fetchone()[0])
            self._outcome(workspace, {"id": key(incident, task_id), "incidentId": incident, "taskId": task_id,
                         "workflowId": workflow["id"], "workflowVersion": workflow["version"], "context": package["context"],
                         "baselineMinutes": tasks[task_id]["estimatedMinutes"], "predictedMinutes": forecast["recommendedMinutes"], "actualMinutes": actual,
                         "waitingMinutes": waiting, "scopeChanged": scope_changed, "evidence": evidence}, now)
            package["revision"] += 1
            self._put(package, now)
        return self.state(workspace, incident, now)

    def record_outcome(self, workspace, outcome, now):
        with self.db:
            self._begin()
            self._outcome(workspace, outcome, now)

    def _outcome(self, workspace, outcome, now):
        oid, incident, task, workflow, context, evidence = (required(outcome, field, 1000 if field == "evidence" else 200) for field in ("id", "incidentId", "taskId", "workflowId", "context", "evidence"))
        version = number(outcome.get("workflowVersion"), "workflowVersion", 1)
        baseline = number(outcome.get("baselineMinutes"), "baselineMinutes", 1)
        predicted = number(outcome.get("predictedMinutes", baseline), "predictedMinutes", 1)
        actual = number(outcome.get("actualMinutes"), "actualMinutes")
        waiting = number(outcome.get("waitingMinutes", 0), "waitingMinutes")
        changed = outcome.get("scopeChanged", False)
        if type(changed) is not bool:
            raise InvalidInput("scopeChanged must be boolean")
        if self.db.execute("SELECT 1 FROM suppressed WHERE workspace=? AND kind='outcome' AND source_id=?", (workspace, oid)).fetchone():
            raise Conflict("This outcome was forgotten and cannot be reimported")
        if self.db.execute("SELECT 1 FROM suppressed WHERE workspace=? AND kind='outcome-task' AND source_id=?", (workspace, key(incident, task))).fetchone():
            raise Conflict("This task's outcome was forgotten")
        record = (workspace, oid, incident, task, workflow, version, context, baseline, predicted, actual, waiting, int(changed), evidence)
        old = self.db.execute("SELECT * FROM outcomes WHERE workspace=? AND (id=? OR (incident=? AND task=?))", (workspace, oid, incident, task)).fetchone()
        if old:
            if tuple(old)[:-1] != record:
                raise Conflict("Outcome already exists with different evidence")
            return
        self.db.execute("INSERT INTO outcomes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", record + (iso(now),))

    def forget_outcome(self, workspace, outcome_id):
        with self.db:
            self._begin()
            old = self.db.execute("SELECT incident,task FROM outcomes WHERE workspace=? AND id=?", (workspace, outcome_id)).fetchone()
            if old:
                self.db.execute("INSERT OR IGNORE INTO suppressed VALUES (?,'outcome-task',?)", (workspace, key(old[0], old[1])))
            self.db.execute("INSERT OR IGNORE INTO suppressed VALUES (?,'outcome',?)", (workspace, outcome_id))
            self.db.execute("DELETE FROM outcomes WHERE workspace=? AND id=?", (workspace, outcome_id))
        # Profiles are derived from remaining rows on every query: no stale cache.

    def remember(self, workspace, lesson, now):
        if lesson.get("confirmed") is not True:
            raise InvalidInput("A preparation note requires explicit dispatcher confirmation")
        rule_key = required(lesson, "key")
        workflow, task, context = [required(lesson, f) for f in ("workflowId", "taskId", "context")]
        version = number(lesson.get("workflowVersion"), "workflowVersion", 1)
        text, evidence = required(lesson, "text", 500), required(lesson, "evidence", 1000)
        source = required(lesson, "sourceId")
        expires = iso(lesson["expiresAt"]) if lesson.get("expiresAt") else None
        if expires and stamp(expires) <= stamp(now):
            raise InvalidInput("A temporary note must expire in the future")
        lesson_id = key(workflow, version, task, context, rule_key)
        with self.db:
            self._begin()
            if self.db.execute("SELECT 1 FROM suppressed WHERE workspace=? AND kind='lesson' AND source_id=?", (workspace, source)).fetchone():
                raise Conflict("This feedback was forgotten")
            old = self.db.execute("SELECT * FROM lessons WHERE workspace=? AND id=?", (workspace, lesson_id)).fetchone()
            used = self.db.execute("SELECT lesson_id FROM lesson_sources WHERE workspace=? AND source_id=?", (workspace, source)).fetchone()
            if used:
                if used[0] == lesson_id and old and all(old[k] == v for k, v in (("text", text), ("evidence", evidence), ("expires_at", expires))):
                    return lesson_id
                raise Conflict("A feedback source cannot be reused for a different change")
            count = self.db.execute("SELECT COUNT(*) FROM lessons WHERE workspace=? AND workflow=? AND workflow_version=? AND task=? AND context=? AND (expires_at IS NULL OR expires_at>?)", (workspace, workflow, version, task, context, iso(now))).fetchone()[0]
            old_active = old and (not old["expires_at"] or stamp(old["expires_at"]) > stamp(now))
            if not old_active and count >= 5:
                raise InvalidInput("This scope already has five active notes; consolidate or forget one")
            duplicate = self.db.execute("SELECT id,text FROM lessons WHERE workspace=? AND workflow=? AND workflow_version=? AND task=? AND context=? AND id!=?", (workspace, workflow, version, task, context, lesson_id)).fetchall()
            if any(" ".join(r["text"].lower().split()) == " ".join(text.lower().split()) for r in duplicate):
                raise InvalidInput("This note already exists; reuse its topic to update it")
            self.db.execute("INSERT INTO lessons VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(workspace,id) DO UPDATE SET text=excluded.text,evidence=excluded.evidence,source_id=excluded.source_id,version=excluded.version,expires_at=excluded.expires_at,updated_at=excluded.updated_at", (workspace, lesson_id, rule_key, workflow, version, task, context, text, evidence, source, old["version"] + 1 if old else 1, expires, iso(now)))
            self.db.execute("INSERT INTO lesson_sources VALUES (?,?,?)", (workspace, lesson_id, source))
        return lesson_id

    def forget_lesson(self, workspace, lesson_id):
        with self.db:
            self._begin()
            self.db.execute("INSERT OR IGNORE INTO suppressed SELECT workspace,'lesson',source_id FROM lesson_sources WHERE workspace=? AND lesson_id=?", (workspace, lesson_id))
            self.db.execute("DELETE FROM lesson_sources WHERE workspace=? AND lesson_id=?", (workspace, lesson_id))
            self.db.execute("DELETE FROM lessons WHERE workspace=? AND id=?", (workspace, lesson_id))

    def state(self, workspace, incident, now):
        package = self._package(workspace, incident)
        schedule = self.plan(package, now)
        rows = self.db.execute("SELECT * FROM reminders WHERE workspace=? AND incident=? ORDER BY revision DESC,due_at", (workspace, incident)).fetchall()
        reminders = [{"id": r["id"], "taskId": r["task"], "employeeId": r["employee"], "revision": r["revision"],
                      "kind": r["kind"], "dueAt": r["due_at"], "startAt": r["start_at"], "status": r["status"],
                      "snoozeUntil": r["snooze_until"], "reason": r["reason"]} for r in rows]
        notes = self.db.execute("SELECT n.*,r.task,r.kind,r.status,r.incident FROM notifications n JOIN reminders r ON n.reminder_id=r.id WHERE n.workspace=? AND r.incident=? ORDER BY n.created_at DESC,n.id", (workspace, incident)).fetchall()
        statuses = [a["status"] for a in package["assignments"]]
        incident_status = "cancelled" if package.get("cancelled") else "resolved" if all(s == "complete" for s in statuses) else "in_progress" if any(s in ("complete", "in_progress") for s in statuses) else "assigned"
        return {"demo": True, "now": iso(now), "package": package, "incidentStatus": incident_status,
                "estimatedResolutionAt": max(t["endAt"] for t in schedule) if all(t["endAt"] for t in schedule) else None,
                "schedule": schedule, "reminders": reminders,
                "notifications": [{"id": n["id"], "reminderId": n["reminder_id"], "employeeId": n["employee"], "taskId": n["task"], "kind": n["kind"], "body": n["body"], "createdAt": n["created_at"], "status": n["status"], "delivery": "simulated_in_app"} for n in notes],
                "lessons": [dict(r) for r in self.db.execute("SELECT * FROM lessons WHERE workspace=? ORDER BY updated_at DESC", (workspace,))],
                "outcomes": [dict(r) for r in self.db.execute("SELECT * FROM outcomes WHERE workspace=? ORDER BY created_at DESC,id", (workspace,))]}
