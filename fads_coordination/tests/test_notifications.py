import copy
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from fads_coordination.api import Hooks
from fads_coordination.core import Coordination, Conflict, InvalidInput, stamp
from fads_coordination.demo import reset_testing, set_values


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Coordination(Path(self.tmp.name) / 'notifications.sqlite')
        self.package = json.loads((Path(__file__).parents[1] / 'fixtures/branch-removal.json').read_text())
        self.ws, self.incident = self.package['workspaceId'], self.package['incident']['id']
        self.now = stamp(self.package['startAt'])
        self.hooks = Hooks(self.app, self.ws, self.now)
        self.load()

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def load(self):
        return self.hooks.post('/hooks/assignments', {**self.package, 'callerId': 'fixture'})

    def items(self, kind, employee=None):
        return self.app.outbox(self.ws, types=[kind], employee_id=employee)['items']

    def task_hook(self, name, task='secure', employee='alex', source=None, **fields):
        return self.hooks.post(f'/hooks/tasks/{self.incident}/{task}/{name}',
                               {'employeeId': employee, 'sourceId': source or name, **fields})

    def snooze(self, item, source='snooze', **fields):
        return self.hooks.post('/hooks/notifications/' + item['id'] + '/snooze',
                               {'employeeId': item['body']['employeeId'], 'sourceId': source, 'minutes': 5, **fields})

    def test_assignment_lifecycle_and_employee_cursor_filter(self):
        assigned = self.items('assignment')
        self.assertEqual(5, len(assigned))
        self.assertTrue(all(i['body']['kind'] == 'assigned' for i in assigned))
        self.assertTrue(all([a['id'] for a in i['body']['actions']] == ['accept', 'snooze', 'delay', 'open'] for i in assigned))
        self.load()
        self.assertEqual(5, len(self.items('assignment')))
        jordan = copy.deepcopy(next(e for e in self.package['employees'] if e['id'] == 'jordan'))
        jordan.update(id='taylor', name='Taylor')
        self.package['employees'].append(jordan)
        next(a for a in self.package['assignments'] if a['taskId'] == 'load')['employeeId'] = 'taylor'
        self.package['revision'] += 1
        self.load()
        changes = self.items('assignment')[5:]
        self.assertEqual([('removed', 'jordan'), ('assigned', 'taylor')], [(i['body']['kind'], i['body']['employeeId']) for i in changes])
        self.assertEqual(['open'], [a['id'] for a in changes[0]['body']['actions']])
        self.assertEqual('jordan', changes[1]['body']['previousEmployeeId'])
        page = self.hooks.get('/hooks/outbox', {'callerId': 'jordan', 'employeeId': 'jordan'})
        self.assertTrue(all(i['body']['employeeId'] == 'jordan' for i in page['items']))
        self.assertEqual([], self.app.outbox(self.ws, page['nextCursor'], employee_id='jordan')['items'])
        self.assertEqual([], self.app.outbox('other-workspace', employee_id='jordan')['items'])

    def test_accept_is_durable_idempotent_and_does_not_complete(self):
        result = self.task_hook('accept')
        self.assertEqual(result, self.task_hook('accept'))
        self.assertEqual(result, self.task_hook('accept', source='another-click'))
        self.package['revision'] += 1
        self.load()
        self.assertEqual(result, self.task_hook('accept', source='after-revision'))
        self.assertEqual(1, len(self.items('acceptance')))
        assignment = self.app.state(self.ws, self.incident, self.now)['package']['assignments'][0]
        self.assertEqual(result['body']['acceptedAt'], assignment['acceptedAt'])
        self.assertNotEqual('complete', assignment['status'])
        self.app.tick(self.ws, self.incident, self.now)
        self.assertNotIn('accept', [a['id'] for a in self.items('reminder')[0]['body']['actions']])
        with self.assertRaises(InvalidInput):
            self.task_hook('accept', employee='sam')
        with self.assertRaises(Conflict):
            self.task_hook('delay', source='accept', note='different operation', minutes=5)
        self.app.close()
        self.app = Coordination(Path(self.tmp.name) / 'notifications.sqlite')
        self.assertEqual(assignment['acceptedAt'], self.app._package(self.ws, self.incident)['assignments'][0]['acceptedAt'])

    def test_snooze_delivery_clock_root_cap_and_fresh_actions(self):
        item = self.items('assignment', 'alex')[0]
        result = self.snooze(item)
        self.assertEqual(result, self.snooze(item))
        self.task_hook('accept')
        self.app.tick(self.ws, self.incident, self.now + timedelta(minutes=4))
        self.assertFalse(any(i.get('repeatOf') for i in self.items('assignment')))
        self.app.tick(self.ws, self.incident, self.now + timedelta(minutes=5))
        repeat = next(i for i in self.items('assignment') if i.get('repeatOf'))
        self.assertEqual(item['id'], repeat['repeatOf'])
        self.assertEqual(item['body']['plainText'], repeat['body']['plainText'])
        self.assertNotIn('accept', [a['id'] for a in repeat['body']['actions']])
        self.snooze(repeat, source='second')
        self.snooze(item, source='third')
        with self.assertRaisesRegex(Conflict, 'delay'):
            self.snooze(repeat, source='fourth')
        self.app.tick(self.ws, self.incident, self.now + timedelta(minutes=10))
        repeats = [i for i in self.items('assignment') if i.get('repeatOf')]
        self.assertEqual(3, len(repeats))
        self.assertNotIn('snooze', [a['id'] for a in repeats[-1]['body']['actions']])
        self.assertEqual(3, self.app.db.execute('SELECT COUNT(*) FROM notification_snoozes').fetchone()[0])

    def test_snooze_latest_start_and_input_guards(self):
        item = self.items('assignment', 'alex')[0]
        for minutes in (0, 61, True, '5'):
            with self.assertRaises(InvalidInput):
                self.snooze(item, minutes=minutes)
        with self.assertRaises(InvalidInput):
            self.snooze(item, employeeId='sam')
        with self.assertRaises(InvalidInput):
            self.snooze(self.items('schedule_entry')[0])
        self.package['employees'][0]['availability'][0]['end'] = '2026-09-14T09:40:00-07:00'
        self.package['revision'] += 1
        self.load()
        with self.assertRaisesRegex(Conflict, 'latest feasible start.*delay'):
            self.snooze(item)
        self.assertEqual(0, self.app.db.execute('SELECT COUNT(*) FROM notification_snoozes').fetchone()[0])

    def test_delay_uses_task_start_phase3_override_and_note(self):
        before = self.app.state(self.ws, self.incident, self.now)
        start = next(t['startAt'] for t in before['schedule'] if t['taskId'] == 'transport')
        result = self.task_hook('delay', task='transport', employee='sam', minutes=30, note='truck in the shop')
        self.assertEqual(result, self.task_hook('delay', task='transport', employee='sam', minutes=30, note='truck in the shop'))
        row = self.app.db.execute('SELECT * FROM availability_overrides').fetchone()
        self.assertEqual(('late', start, 'truck in the shop'), (row['kind'], row['start_at'], row['reason']))
        self.assertEqual(timedelta(minutes=30), stamp(row['end_at']) - stamp(start))
        self.assertEqual(1, len(result['conflicts']))
        self.assertIn('truck in the shop', result['conflicts'][0]['body']['plainText'])
        self.assertEqual('late', result['conflicts'][0]['body']['cause'])
        after = self.app.state(self.ws, self.incident, self.now)
        old_ids = {r['id'] for r in before['reminders'] if r['taskId'] == 'transport'}
        self.assertTrue(all(r['status'] == 'superseded' for r in after['reminders'] if r['id'] in old_ids))
        self.assertEqual(1, after['package']['revision'])
        self.assertTrue(any(i['body']['kind'] == 'rescheduled' for i in self.items('assignment', 'sam')))
        self.assertEqual(1, self.app.db.execute('SELECT COUNT(*) FROM availability_overrides').fetchone()[0])

    def test_delay_validation_until_and_started_action_guards(self):
        for fields in ({'minutes': 5}, {'minutes': 5, 'note': ' '}, {'minutes': 5, 'note': 'x' * 501},
                       {'minutes': 5, 'until': self.now.isoformat(), 'note': 'x'}, {'until': self.now.isoformat(), 'note': 'x'}):
            with self.assertRaises(InvalidInput):
                self.task_hook('delay', **fields)
        self.assertEqual(0, self.app.db.execute('SELECT COUNT(*) FROM availability_overrides').fetchone()[0])
        self.task_hook('delay', until=(self.now + timedelta(minutes=5)).isoformat(), note='traffic')
        self.package['assignments'][0].update(status='in_progress', startedAt=self.now.isoformat())
        self.package['revision'] += 1
        self.load()
        with self.assertRaisesRegex(Conflict, 'already started'):
            self.task_hook('delay', source='started', minutes=5, note='traffic')
        item = [i for i in self.items('assignment', 'alex') if i['body']['taskId'] == 'secure'][-1]
        self.assertNotIn('delay', [a['id'] for a in item['body']['actions']])

    def test_pending_repeat_does_not_revive_completed_task_and_reset_clears_state(self):
        item = self.items('assignment', 'alex')[0]
        self.snooze(item)
        self.task_hook('accept')
        self.task_hook('done', checklist=[{'item': 'done', 'done': True}])
        self.app.tick(self.ws, self.incident, self.now + timedelta(minutes=5))
        self.assertFalse(any(i.get('repeatOf') for i in self.items('assignment')))
        set_values(self.app, workspace=self.ws)
        reset_testing(self.app, 'fixture')
        for table in ('notification_snoozes', 'task_acceptances'):
            self.assertEqual(0, self.app.db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0])

    def test_reassignment_retires_acceptance_and_queued_notifications_even_if_returned(self):
        item = self.items('assignment', 'alex')[0]
        self.snooze(item)
        self.task_hook('accept')
        replacement = copy.deepcopy(self.package['employees'][0])
        replacement.update(id='taylor', name='Taylor')
        self.package['employees'].append(replacement)
        self.package['assignments'][0]['employeeId'] = 'taylor'
        self.package['revision'] = 2
        self.load()
        self.package['assignments'][0]['employeeId'] = 'alex'
        self.package['revision'] = 3
        self.load()
        self.assertNotIn('acceptedAt', self.app._package(self.ws, self.incident)['assignments'][0])
        with self.assertRaisesRegex(Conflict, 'removed assignment'):
            self.snooze(item, source='stale-click')
        self.app.tick(self.ws, self.incident, self.now + timedelta(minutes=5))
        self.assertFalse(any(i.get('repeatOf') for i in self.items('assignment')))
        self.task_hook('accept', source='new-ownership')
        self.assertEqual(2, len(self.items('acceptance')))

    def test_task_removal_emits_link_only_assignment(self):
        self.package['workflow']['version'] += 1
        self.package['workflow']['tasks'] = [t for t in self.package['workflow']['tasks'] if t['id'] != 'verify']
        self.package['assignments'] = [a for a in self.package['assignments'] if a['taskId'] != 'verify']
        self.package['revision'] += 1
        self.load()
        removed = [i for i in self.items('assignment') if i['body']['kind'] == 'removed']
        self.assertEqual(1, len(removed))
        self.assertEqual('verify', removed[0]['body']['taskId'])
        self.assertEqual(['open'], [a['id'] for a in removed[0]['body']['actions']])

    def test_open_links_on_assignments_reminders_conflicts_and_repeats(self):
        from urllib.parse import parse_qs, urlparse
        self.app.tick(self.ws, self.incident, self.now)
        self.task_hook('delay', task='transport', employee='sam', minutes=30, note='traffic')
        item = self.items('assignment', 'alex')[0]
        self.snooze(item)
        self.app.tick(self.ws, self.incident, self.now + timedelta(minutes=5))
        for kind in ('assignment', 'reminder', 'conflict'):
            self.assertTrue(self.items(kind))
            for item in self.items(kind):
                action = item['body']['actions'][-1]
                self.assertEqual(('open', 'Open web', 'link'), (action['id'], action['label'], action['kind']))
                self.assertNotIn('method', action)
                url = urlparse(action['url'])
                self.assertEqual('/web/employee.html', url.path)
                self.assertEqual({'employeeId': [item['body']['employeeId']], 'package': [item['id']]}, parse_qs(url.query))
