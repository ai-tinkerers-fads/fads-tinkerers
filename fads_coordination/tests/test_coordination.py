import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from fads_coordination.core import Coordination, Conflict, InvalidInput


FIXTURE = Path(__file__).parents[1] / "fixtures" / "branch-removal.json"


class CoordinationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "test.sqlite"
        self.app = Coordination(self.db)
        self.package = json.loads(FIXTURE.read_text())
        self.now = datetime.fromisoformat(self.package["startAt"])
        self.workspace = self.package["workspaceId"]
        self.incident = self.package["incident"]["id"]

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def load(self):
        return self.app.put_package(self.package, self.now)

    def state(self):
        return self.app.state(self.workspace, self.incident, self.now)

    def test_plan_respects_dependencies_driver_availability_and_skills(self):
        self.load()
        tasks = {t["taskId"]: t for t in self.state()["schedule"]}
        self.assertGreaterEqual(tasks["transport"]["startAt"], tasks["load"]["endAt"])
        self.assertEqual(tasks["transport"]["startAt"], "2026-09-14T18:00:00+00:00")
        self.assertEqual(self.state()["incidentStatus"], "assigned")

    def test_duplicate_and_outdated_package(self):
        self.load()
        before = self.state()["reminders"]
        self.load()
        self.assertEqual(before, self.state()["reminders"])
        changed = copy.deepcopy(self.package)
        changed["incident"]["report"]["text"] = "Changed report"
        with self.assertRaises(Conflict):
            self.app.put_package(changed, self.now)
        changed["revision"] = 0
        with self.assertRaises(InvalidInput):
            self.app.put_package(changed, self.now)

    def test_dependency_cycle_and_naive_date_rejected_without_write(self):
        self.package["workflow"]["tasks"][0]["dependsOn"] = ["verify"]
        with self.assertRaises(InvalidInput):
            self.load()
        self.assertIsNone(self.app.get_package(self.workspace, self.incident))
        self.package = json.loads(FIXTURE.read_text())
        self.package["startAt"] = "2026-09-14T09:00:00"
        with self.assertRaises(InvalidInput):
            self.load()

    def test_unqualified_assignee_rejected(self):
        self.package["assignments"][1]["employeeId"] = "sam"
        with self.assertRaises(InvalidInput):
            self.load()

    def test_missing_capacity_blocks_downstream(self):
        self.package["employees"][2]["availability"] = []
        self.load()
        tasks = {t["taskId"]: t for t in self.state()["schedule"]}
        self.assertEqual(tasks["transport"]["state"], "blocked")
        self.assertEqual(tasks["verify"]["state"], "blocked")
        self.assertIsNone(self.state()["estimatedResolutionAt"])

    def test_in_app_delivery_is_durable_and_ack_is_not_completion(self):
        self.load()
        self.app.tick(self.workspace, self.incident, self.now)
        note = self.state()["notifications"][0]
        count = len(self.state()["notifications"])
        self.app.close()
        self.app = Coordination(self.db)
        self.app.tick(self.workspace, self.incident, self.now)
        self.assertEqual(len(self.state()["notifications"]), count)
        self.app.acknowledge(self.workspace, note["reminderId"], note["employeeId"], self.now)
        self.assertNotEqual(self.state()["incidentStatus"], "resolved")
        with self.assertRaises(InvalidInput):
            self.app.acknowledge(self.workspace, note["reminderId"], "sam", self.now)

    def test_ready_notification_waits_for_completed_dependency(self):
        self.load()
        self.app.tick(self.workspace, self.incident, self.now + timedelta(minutes=12))
        self.assertFalse(any(n["taskId"] == "cut" and n["kind"] == "ready"
                             for n in self.state()["notifications"]))

    def test_reassignment_supersedes_old_reminders(self):
        self.load()
        changed = copy.deepcopy(self.package)
        replacement = copy.deepcopy(changed["employees"][1])
        replacement["id"] = "taylor"
        replacement["name"] = "Taylor"
        changed["employees"].append(replacement)
        changed["assignments"][2]["employeeId"] = "taylor"
        changed["revision"] += 1
        self.app.put_package(changed, self.now)
        active = [r for r in self.state()["reminders"] if r["status"] == "scheduled"]
        self.assertTrue(any(r["taskId"] == "load" and r["employeeId"] == "taylor" for r in active))
        self.assertFalse(any(r["taskId"] == "load" and r["employeeId"] == "jordan" for r in active))

    def test_complete_requires_dependencies_and_actual_effort(self):
        self.load()
        with self.assertRaises(InvalidInput):
            self.app.complete(self.workspace, self.incident, "cut", 30, 0, False, "test", self.now, 1)
        self.app.complete(self.workspace, self.incident, "secure", 10, 0, False,
                          "Confirmed by fixture dispatcher", self.now + timedelta(minutes=10), 1)
        self.assertEqual(self.state()["package"]["assignments"][0]["status"], "complete")
        self.assertEqual(len(self.state()["outcomes"]), 1)
        self.assertFalse(any(r["taskId"] == "secure" and r["status"] == "scheduled"
                             for r in self.state()["reminders"]))
        with self.assertRaises(Conflict):
            self.app.complete(self.workspace, self.incident, "secure", 10, 0, False, "test", self.now, 1)

    def test_snooze_and_invalid_deadline(self):
        self.load()
        reminder = next(r for r in self.state()["reminders"] if r["taskId"] == "load" and r["kind"] == "prepare")
        until = datetime.fromisoformat(reminder["dueAt"]) + timedelta(minutes=2)
        self.app.snooze(self.workspace, reminder["id"], "jordan", until, self.now)
        self.app.tick(self.workspace, self.incident, until - timedelta(seconds=1))
        self.assertFalse(any(n["reminderId"] == reminder["id"] for n in self.state()["notifications"]))
        with self.assertRaises(InvalidInput):
            self.app.snooze(self.workspace, reminder["id"], "jordan", until + timedelta(days=1), self.now)

    def add_outcome(self, index, actual=60, scope_changed=False):
        return self.app.record_outcome(self.workspace, {
            "id": f"history-{index}", "incidentId": f"old-{index}", "taskId": "cut",
            "workflowId": "branch-removal", "workflowVersion": 1, "context": "standard",
            "baselineMinutes": 30, "actualMinutes": actual, "waitingMinutes": 120,
            "scopeChanged": scope_changed, "evidence": "Synthetic measured active effort",
        }, self.now)

    def test_estimates_need_independent_comparable_actuals_and_deletion_recomputes(self):
        self.load()
        for i in range(4):
            self.add_outcome(i)
        cut = lambda: next(t for t in self.state()["schedule"] if t["taskId"] == "cut")
        self.assertEqual(cut()["estimatedMinutes"], 30)
        self.add_outcome(4)
        self.add_outcome(4)
        self.assertEqual(cut()["estimatedMinutes"], 30)  # Active plan does not silently change.
        self.app.replan(self.workspace, self.incident, self.now, 1)
        self.assertEqual(cut()["estimateEvidence"]["sampleCount"], 5)
        self.assertEqual(cut()["estimatedMinutes"], 45)
        self.assertEqual(next(t for t in self.state()["schedule"] if t["taskId"] == "load")["estimatedMinutes"], 20)
        self.app.forget_outcome(self.workspace, "history-4")
        self.app.replan(self.workspace, self.incident, self.now, 2)
        self.assertEqual(cut()["estimatedMinutes"], 30)
        with self.assertRaises(Conflict):
            self.add_outcome(4)

    def test_changed_scope_is_not_used_as_duration_training(self):
        self.load()
        for i in range(5):
            self.add_outcome(i, scope_changed=True)
        cut = next(t for t in self.state()["schedule"] if t["taskId"] == "cut")
        self.assertEqual(cut["estimatedMinutes"], 30)

    def test_lesson_is_scoped_deduplicated_expirable_and_forgettable(self):
        self.load()
        lesson = {"key": "equipment-check", "workflowId": "branch-removal", "workflowVersion": 1,
                  "taskId": "cut", "context": "standard", "text": "Review the assigned equipment list before departure.",
                  "evidence": "Dispatcher correction", "sourceId": "feedback-1", "confirmed": True}
        self.app.remember(self.workspace, lesson, self.now)
        self.app.remember(self.workspace, lesson, self.now)
        self.assertEqual(len(self.state()["lessons"]), 1)
        cut = next(t for t in self.state()["schedule"] if t["taskId"] == "cut")
        self.assertEqual(len(cut["lessons"]), 1)
        self.assertFalse(next(t for t in self.state()["schedule"] if t["taskId"] == "load")["lessons"])
        self.assertEqual(self.app.lessons("other-workspace", "branch-removal", 1, "cut", "standard", self.now), [])
        lesson["sourceId"] = "feedback-2"
        lesson["text"] = "Review equipment with the dispatcher."
        lesson["expiresAt"] = (self.now + timedelta(days=1)).isoformat()
        self.app.remember(self.workspace, lesson, self.now)
        self.assertEqual(len(self.state()["lessons"]), 1)
        self.assertEqual(self.app.lessons(self.workspace, "branch-removal", 1, "cut", "standard", self.now + timedelta(days=2)), [])
        self.app.forget_lesson(self.workspace, self.state()["lessons"][0]["id"])
        with self.assertRaises(Conflict):
            self.app.remember(self.workspace, lesson, self.now)

    def test_unconfirmed_lesson_cannot_modify_memory(self):
        with self.assertRaises(InvalidInput):
            self.app.remember(self.workspace, {"confirmed": False}, self.now)

    def test_future_completion_and_malformed_collections_are_rejected(self):
        self.package["assignments"][0].update(status="complete", completedAt=(self.now + timedelta(hours=1)).isoformat())
        with self.assertRaises(InvalidInput):
            self.load()
        self.package["employees"] = "bad"
        with self.assertRaises(InvalidInput):
            self.load()

    def test_offset_and_dst_are_compared_as_instants(self):
        self.package["startAt"] = "2026-11-01T01:30:00-07:00"
        for employee in self.package["employees"]:
            employee["availability"] = [{"start": "2026-11-01T01:00:00-07:00", "end": "2026-11-01T04:00:00-08:00"}]
        now = datetime.fromisoformat(self.package["startAt"])
        self.app.put_package(self.package, now)
        plan = self.app.state(self.workspace, self.incident, now)["schedule"]
        self.assertEqual(plan[0]["startAt"], "2026-11-01T08:30:00+00:00")
        self.assertTrue(all(t["endAt"] > t["startAt"] for t in plan))

    def test_no_notifications_outside_available_hours(self):
        self.load()
        self.app.tick(self.workspace, self.incident, self.now + timedelta(hours=10))
        self.assertEqual(self.state()["notifications"], [])

    def test_completion_preserves_forecast_and_waiting_separately(self):
        self.load()
        self.app.complete(self.workspace, self.incident, "secure", 15, 90, False, "Manual actuals", self.now + timedelta(hours=2), 1)
        outcome = self.state()["outcomes"][0]
        self.assertEqual(outcome["predicted"], 10)
        self.assertEqual(outcome["actual"], 15)
        self.assertEqual(outcome["waiting"], 90)

    def test_completing_prerequisite_does_not_apply_unapproved_estimates(self):
        self.load()
        for i in range(5):
            self.add_outcome(i)
        self.app.complete(self.workspace, self.incident, "secure", 10, 0, False, "Reported effort", self.now + timedelta(minutes=10), 1)
        cut = next(t for t in self.state()["schedule"] if t["taskId"] == "cut")
        self.assertEqual(cut["estimatedMinutes"], 30)
        self.assertEqual(cut["nextEstimate"]["recommendedMinutes"], 45)

    def test_snooze_cannot_move_a_reminder_earlier(self):
        self.load()
        reminder = next(r for r in self.state()["reminders"] if r["taskId"] == "load" and r["kind"] == "prepare")
        with self.assertRaises(InvalidInput):
            self.app.snooze(self.workspace, reminder["id"], "jordan", self.now + timedelta(minutes=5), self.now)

    def test_independent_completion_counts_cannot_be_inflated_by_new_ids(self):
        self.load()
        self.add_outcome(1)
        self.app.forget_outcome(self.workspace, "history-1")
        with self.assertRaises(Conflict):
            self.app.record_outcome(self.workspace, {
                "id": "different-id", "incidentId": "old-1", "taskId": "cut",
                "workflowId": "branch-removal", "workflowVersion": 1, "context": "standard",
                "baselineMinutes": 30, "actualMinutes": 60, "evidence": "Same forgotten task",
            }, self.now)

    def test_cancellation_prevents_further_notifications_and_completion(self):
        self.load()
        self.app.cancel(self.workspace, self.incident, self.now, 1)
        self.app.tick(self.workspace, self.incident, self.now + timedelta(minutes=30))
        self.assertEqual(self.state()["incidentStatus"], "cancelled")
        self.assertEqual(self.state()["notifications"], [])
        self.assertFalse(any(r["status"] == "scheduled" for r in self.state()["reminders"]))
        with self.assertRaises(Conflict):
            self.app.complete(self.workspace, self.incident, "secure", 10, 0, False, "test", self.now, 2)

    def test_remaining_estimate_does_not_slide_forward_on_every_poll(self):
        self.package["assignments"][0].update(status="in_progress", startedAt=self.now.isoformat(),
            remainingMinutes=5, remainingUpdatedAt=self.now.isoformat())
        self.load()
        later = self.app.state(self.workspace, self.incident, self.now + timedelta(minutes=6))
        self.assertEqual(later["schedule"][0]["state"], "blocked")
        self.assertIsNone(later["estimatedResolutionAt"])

    def test_upstream_cannot_start_a_task_before_its_prerequisites(self):
        self.package["assignments"][1].update(status="in_progress", startedAt=self.now.isoformat())
        with self.assertRaises(InvalidInput):
            self.load()

    def test_workspace_and_workflow_version_isolate_estimate_profiles(self):
        for i in range(5):
            self.add_outcome(i)
        self.assertEqual(self.app.estimate("different", "branch-removal", 1, "cut", "standard", 30)["sampleCount"], 0)
        self.assertEqual(self.app.estimate(self.workspace, "branch-removal", 2, "cut", "standard", 30)["sampleCount"], 0)

    def test_context_budget_and_duplicate_note_guard(self):
        base = {"workflowId": "branch-removal", "workflowVersion": 1, "taskId": "cut", "context": "standard",
                "text": "Check the assigned equipment list.", "evidence": "Dispatcher", "confirmed": True}
        self.app.remember(self.workspace, dict(base, key="first", sourceId="one"), self.now)
        with self.assertRaises(InvalidInput):
            self.app.remember(self.workspace, dict(base, key="duplicate", sourceId="two"), self.now)
        for i in range(4):
            self.app.remember(self.workspace, dict(base, key=f"note-{i}", sourceId=f"source-{i}", text=f"Confirmed task note {i}"), self.now)
        with self.assertRaises(InvalidInput):
            self.app.remember(self.workspace, dict(base, key="overflow", sourceId="overflow", text="A sixth note"), self.now)
        self.assertEqual(len(self.app.lessons(self.workspace, "branch-removal", 1, "cut", "standard", self.now)), 5)


if __name__ == "__main__":
    unittest.main()
