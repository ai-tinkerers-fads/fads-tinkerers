import copy
import hashlib
import hmac
import json
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from fads_coordination.api import Hooks, deliver_webhooks
from fads_coordination.core import Coordination, Conflict, InvalidInput

FIXTURE = Path(__file__).parents[1] / "fixtures/branch-removal.json"


class HookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Coordination(Path(self.tmp.name) / 'test.sqlite')
        self.package = json.loads(FIXTURE.read_text())
        self.now = datetime.fromisoformat(self.package['startAt'])
        self.ws = self.package['workspaceId']
        self.incident = self.package['incident']['id']
        self.hooks = Hooks(self.app, self.ws, self.now)

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def load(self):
        return self.hooks.post('/hooks/assignments', dict(self.package, callerId='fixture-dispatcher'))

    def items(self, kind=None, after=0):
        return self.app.outbox(self.ws, after, [kind] if kind else None)['items']

    def test_phase2_assignments_outbox_cursor_and_inbox_sink(self):
        self.load()
        page = self.hooks.get('/hooks/outbox', {'callerId': 'fixture-reader'})
        self.assertEqual(5, len(page['items']))
        self.assertTrue(all(i['type'] == 'schedule_entry' for i in page['items']))
        self.load()
        self.assertEqual([], self.items(after=page['nextCursor']))
        self.app.tick(self.ws, self.incident, self.now)
        new = self.items(after=page['nextCursor'])
        self.assertTrue(new)
        self.assertTrue(all(i['type'] == 'reminder' for i in new))
        inbox = self.app.state(self.ws, self.incident, self.now)['notifications']
        self.assertEqual({i['id'] for i in new}, {i['id'] for i in inbox})
        self.assertEqual('state', self.hooks.get('/hooks/state/'+self.incident, {'callerId':'reader'})['type'])
        with self.assertRaises(InvalidInput):
            self.hooks.post('/hooks/assignments', self.package)
        with self.assertRaises(InvalidInput):
            self.hooks.get('/hooks/outbox', {})

    def receiver(self, status=200, delay=0):
        received = []
        class Receiver(BaseHTTPRequestHandler):
            def do_POST(inner):
                raw = inner.rfile.read(int(inner.headers['Content-Length']))
                received.append((raw, dict(inner.headers)))
                if delay:
                    time.sleep(delay)
                inner.send_response(status)
                inner.send_header('X-Response-Id', 'fixture-receipt')
                inner.send_header('Content-Length', '0')
                inner.end_headers()
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Receiver)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f'http://127.0.0.1:{server.server_port}/receive', received

    def test_phase2_local_webhook_signatures_and_no_duplicate_acceptance(self):
        self.load()
        url, received = self.receiver()
        deliver_webhooks(self.app, url, 'fixture-secret', now=100)
        deliver_webhooks(self.app, url, 'fixture-secret', now=1000)
        self.assertEqual(5, len(received))
        for raw, headers in received:
            signature = hmac.new(b'fixture-secret', headers['X-FADS-Timestamp'].encode()+b'.'+raw, hashlib.sha256).hexdigest()
            self.assertEqual('sha256='+signature, headers['X-FADS-Signature'])
            self.assertEqual(json.loads(raw)['id'], headers['Idempotency-Key'])
        states = list(self.app.db.execute('SELECT state,attempt,provider_response_id FROM webhook_deliveries'))
        self.assertTrue(all(tuple(r)==('accepted',1,'fixture-receipt') for r in states))
        with self.assertRaises(InvalidInput):
            deliver_webhooks(self.app, 'https://example.invalid/hook', 'fixture-secret')

    def test_phase2_500_bounded_retries_then_failed(self):
        self.load()
        url, received = self.receiver(500)
        for now in (100, 110, 120, 130):
            deliver_webhooks(self.app, url, 'fixture-secret', now=now)
        self.assertEqual(15, len(received))
        self.assertTrue(all(tuple(r)==('failed',3) for r in self.app.db.execute('SELECT state,attempt FROM webhook_deliveries')))

    def test_phase2_timeout_unknown_never_resent(self):
        self.load()
        url, received = self.receiver(delay=0.1)
        deliver_webhooks(self.app, url, 'fixture-secret', timeout=0.02)
        deliver_webhooks(self.app, url, 'fixture-secret', now=time.time()+100)
        self.assertEqual(5, len(received))
        self.assertTrue(all(tuple(r)==('unknown',1) for r in self.app.db.execute('SELECT state,attempt FROM webhook_deliveries')))

    def availability(self, employee, kind, start=None, end=None, source="fixture-override"):
        return self.hooks.post(f"/hooks/employees/{employee}/availability", {
            "employeeId": employee, "kind": kind, "incidentId": self.incident,
            "window": {"start": start or self.package["startAt"], "end": end or (self.now+timedelta(hours=1)).isoformat()},
            "reason": "Fixture schedule update", "sourceId": source})

    def test_phase3_day_off_blocks_dependencies_and_survives_upstream_revision(self):
        self.load()
        first = self.availability('sam', 'day_off')
        self.assertEqual(first, self.availability('sam', 'day_off'))
        self.assertEqual(1, self.app.db.execute('SELECT COUNT(*) FROM availability_overrides').fetchone()[0])
        conflicts = self.items('conflict')
        self.assertEqual(1, len(conflicts))
        body = conflicts[0]['body']
        self.assertEqual(('sam', 'transport', 'absence'), (body['employeeId'], body['taskId'], body['cause']))
        self.assertEqual(['transport', 'verify'], body['affectedTasks'])
        self.assertIn('Sam', body['plainText'])
        state = self.app.state(self.ws, self.incident, self.now)
        self.assertEqual(1, state['package']['revision'])
        self.assertEqual(['transport', 'verify'], [t['taskId'] for t in state['schedule'] if t['state']=='blocked'])
        replacement = copy.deepcopy(next(e for e in self.package['employees'] if e['id']=='sam'))
        replacement.update(id='pat', name='Pat')
        self.package['employees'].append(replacement)
        self.package['assignments'][3]['employeeId']='pat'
        self.package['revision']=2
        self.load()
        state = self.app.state(self.ws, self.incident, self.now)
        self.assertTrue(all(t['state']=='scheduled' for t in state['schedule']))
        self.assertEqual(1, len(self.items('conflict')))
        self.assertFalse(any(r['employeeId']=='sam' and r['status']=='scheduled' for r in state['reminders']))
        sam = next(e for e in self.package['employees'] if e['id']=='sam')
        self.assertEqual([], self.app.available_windows(self.package, sam, self.now))

    def test_phase3_late_tolerance_and_schedule_upsert(self):
        for tolerance, expected in ((0,1),(30,0)):
            with self.subTest(tolerance=tolerance):
                self.package['incident']['id']=self.incident='late-'+str(tolerance)
                for a in self.package['assignments']:
                    a['incidentId']=self.incident
                self.package['conflictToleranceMinutes']=tolerance
                self.package['employees'][2]['availability'][0]['start']=self.package['startAt']
                self.load()
                before=self.app.state(self.ws,self.incident,self.now)['estimatedResolutionAt']
                result=self.availability('alex','late',(self.now+timedelta(minutes=20)).isoformat(),source='late-'+str(tolerance))
                state=self.app.state(self.ws,self.incident,self.now)
                self.assertTrue(all(t['state']=='scheduled' for t in state['schedule']))
                self.assertEqual(timedelta(minutes=20), datetime.fromisoformat(state['estimatedResolutionAt'])-datetime.fromisoformat(before))
                self.assertEqual(expected,len(result['conflicts']))
                self.assertEqual(1,state['package']['revision'])
                self.assertTrue(any(i['body']['overrideSequence'] for i in self.items('schedule_entry') if i['incidentId']==self.incident))

    def test_phase3_snooze_past_feasible_window_signals_and_stays_blocked(self):
        state=self.load()
        reminder=next(r for r in state['reminders'] if r['taskId']=='transport' and r['kind']=='prepare')
        result=self.hooks.post('/hooks/reminders/'+reminder['id']+'/snooze', {'employeeId':'sam','until':(self.now+timedelta(hours=9)).isoformat()})
        self.assertEqual('snooze',result['conflict']['body']['cause'])
        state=self.app.tick(self.ws,self.incident,self.now)
        self.assertEqual(['transport','verify'],[t['taskId'] for t in state['schedule'] if t['state']=='blocked'])

    def test_phase3_custom_subtraction_scope_and_recipient_validation(self):
        self.load()
        self.availability('sam','custom','2026-09-14T11:00:00-07:00','2026-09-14T11:15:00-07:00')
        sam=next(e for e in self.package['employees'] if e['id']=='sam')
        windows=self.app.available_windows(self.package,sam,self.now)
        self.assertEqual('2026-09-14T18:15:00+00:00',windows[0]['start'])
        other=copy.deepcopy(self.package);other['incident']['id']='other'
        self.assertEqual(sam['availability'][0]['start'],datetime.fromisoformat(self.app.available_windows(other,sam,self.now)[0]['start']).astimezone(self.now.tzinfo).isoformat())
        with self.assertRaises(InvalidInput):
            self.hooks.post('/hooks/employees/sam/availability', {'employeeId':'alex'})

    def done(self, task='secure', employee='alex', source='done-fixture', **data):
        return self.hooks.post(f'/hooks/tasks/{self.incident}/{task}/done', {
            'employeeId':employee, 'checklist':[{'item':'Assigned work done','done':True}],
            'sourceId':source, **data})

    def test_phase4_unknown_actual_completion_proof_and_idempotency(self):
        self.load()
        data={'employeeId':'alex','sourceId':'fixture-proof','proof':{'kind':'image','ref':'fixture://proof/unread-image.png','sha256':'a'*64,'note':'Reference only'}}
        route=f'/hooks/tasks/{self.incident}/secure/proof'
        first=self.hooks.post(route,data)
        self.assertEqual(first,self.hooks.post(route,data))
        self.assertEqual(1,self.app.db.execute('SELECT COUNT(*) FROM proofs').fetchone()[0])
        completed=self.done()
        self.assertEqual(completed,self.done())
        self.assertEqual('completion',completed['type'])
        self.assertIsNone(completed['body']['actualMinutes'])
        self.assertEqual(data['proof']['ref'],completed['body']['proofs'][0]['ref'])
        self.assertEqual(1,len(self.items('completion')))
        state=self.app.state(self.ws,self.incident,self.now)
        self.assertIsNone(state['outcomes'][0]['actual'])
        self.assertEqual('complete',state['schedule'][0]['status'])
        self.assertEqual(1,state['package']['revision'])
        profile=self.app.estimate(self.ws,'branch-removal',1,'secure','standard',10)
        self.assertEqual(0,profile['sampleCount'])
        self.load()  # Replayed upstream snapshot must not undo local completion.
        self.package['revision']=2
        self.load()
        self.assertEqual('complete',self.app.state(self.ws,self.incident,self.now)['schedule'][0]['status'])

    def test_phase4_known_actuals_and_checklist_employee_guards(self):
        self.load()
        for fields in ({'employee':'sam'}, {'checklist':[{'item':'Unchecked','done':False}]}, {'actualMinutes':-1}):
            with self.assertRaises(InvalidInput):
                self.done(**fields)
        self.assertEqual(0,self.app.db.execute('SELECT COUNT(*) FROM outcomes').fetchone()[0])
        result=self.done(actualMinutes=12,waitingMinutes=3,note='Fixture actual observation')
        self.assertEqual((12,3),(result['body']['actualMinutes'],result['body']['waitingMinutes']))
        self.assertEqual(1,self.app.estimate(self.ws,'branch-removal',1,'secure','standard',10)['sampleCount'])
        with self.assertRaises(Conflict):
            self.done(source='another-done')
        with self.assertRaises(Conflict):
            self.hooks.post(f'/hooks/tasks/{self.incident}/secure/proof',{'employeeId':'alex','sourceId':'done-fixture','proof':{'kind':'link','ref':'fixture://unused'}})

    def test_phase5_csv_and_saved_sheet_map_without_external_calls(self):
        from fads_coordination.intake import load_document
        mapping=json.loads((FIXTURE.parent/'field-map.json').read_text())
        source={'kind':'csv','ref':'assignments.csv'}
        result=self.hooks.post('/hooks/assignments/from-document', {'callerId':'fixture-reader','source':source,'fieldMap':mapping})
        self.assertEqual(self.package['workflow'],result['package']['workflow'])
        self.assertEqual(self.package['assignments'],result['package']['assignments'])
        self.assertEqual(5,len(self.items('schedule_entry')))
        self.hooks.post('/hooks/assignments/from-document', {'callerId':'fixture-reader','source':source,'fieldMap':mapping})
        self.assertEqual(5,len(self.items('schedule_entry')))
        sheet,_=load_document({'kind':'ambiguous_sheet','ref':'sheet-response.json'},mapping)
        self.assertEqual(self.package['workflow'],sheet['workflow'])
        with self.assertRaises(InvalidInput):
            load_document({'kind':'csv','ref':'../../core.py'},mapping)

    def test_phase5_changed_row_supersedes_only_its_task(self):
        from fads_coordination.intake import read_rows, map_rows
        mapping=json.loads((FIXTURE.parent/'field-map.json').read_text())
        source={'kind':'csv','ref':'assignments.csv'}
        rows=read_rows(source)
        package,digest=map_rows(rows,mapping,source)
        self.app.put_document(package,json.dumps(source),digest,self.now)
        old=self.app.state(self.ws,self.incident,self.now)['reminders']
        row=next(r for r in rows if r['Step']=='transport')
        row.update({'Worker':'pat','Worker name':'Pat','Assignee':'pat'})
        changed,new_digest=map_rows(rows,mapping,source)
        self.assertNotEqual(package['revision'],changed['revision'])
        self.app.put_document(changed,json.dumps(source),new_digest,self.now)
        state=self.app.state(self.ws,self.incident,self.now)
        current={r['id']:r for r in state['reminders']}
        for reminder in old:
            self.assertEqual('superseded' if reminder['taskId']=='transport' else 'scheduled',current[reminder['id']]['status'])
        self.assertEqual('pat',state['schedule'][3]['employeeId'])
        self.app.put_document(changed,json.dumps(source),new_digest,self.now)
        with self.assertRaises(Conflict):
            self.app.put_document(package,json.dumps(source),digest,self.now)

    def test_phase5_missing_column_named_and_no_guessed_mapping(self):
        from fads_coordination.intake import read_rows, map_rows
        mapping=json.loads((FIXTURE.parent/'field-map.json').read_text())
        source={'kind':'csv','ref':'assignments.csv'}
        rows=read_rows(source)
        del rows[0]['Assignee']
        with self.assertRaisesRegex(InvalidInput,'Assignee'):
            map_rows(rows,mapping,source)
        del mapping['assignments']['employeeId']
        with self.assertRaisesRegex(InvalidInput,'assignments.employeeId'):
            map_rows(rows,mapping,source)

    def test_phase6_pending_catalog_confirmation_and_immutable_version(self):
        self.load()
        catalog=self.app.workflow_catalog(self.ws)
        self.assertEqual(1,len(catalog))
        self.assertEqual('pending',catalog[0]['status'])
        self.assertEqual('fixture-dispatcher',catalog[0]['provenance']['createdBy'])
        self.assertIn('createdAt',catalog[0]['provenance'])
        self.assertIn('sourceRef',catalog[0]['provenance'])
        self.assertIn('howBuilt',catalog[0]['provenance'])
        route='/hooks/workflows/branch-removal/1/confirm'
        first=self.hooks.post(route,{'confirmedBy':'fixture-reviewer'})
        self.assertEqual('active',first['status'])
        self.assertEqual(first,self.hooks.post(route,{'confirmedBy':'second-reviewer'}))
        self.load()
        self.assertEqual(1,len(self.app.workflow_catalog(self.ws)))
        self.package['incident']['id']='different-case'
        for a in self.package['assignments']:
            a['incidentId']='different-case'
        self.package['workflow']['tasks'][0]['estimatedMinutes']=11
        with self.assertRaises(Conflict):
            self.load()
        self.assertIsNone(self.app.get_package(self.ws,'different-case'))
        self.package['workflow']['version']=2
        self.load()
        self.assertEqual(['active','pending'],[w['status'] for w in self.app.workflow_catalog(self.ws)])

    def test_phase6_catalog_workspace_and_confirmation_guards(self):
        self.load()
        with self.assertRaises(InvalidInput):
            self.hooks.post('/hooks/workflows/branch-removal/1/confirm',{})
        with self.assertRaises(InvalidInput):
            self.app.confirm_workflow('another-workspace','branch-removal',1,'reviewer',self.now)
        self.assertEqual('pending',self.app.workflow_catalog(self.ws)[0]['status'])

    def test_phase7_override_does_not_reopen_or_block_completed_work(self):
        self.load()
        self.done()
        self.availability('alex','absence')
        state=self.app.state(self.ws,self.incident,self.now)
        self.assertEqual('complete',state['schedule'][0]['status'])
        self.assertEqual('scheduled',state['schedule'][0]['state'])
        self.assertEqual('blocked',state['schedule'][1]['state'])
        self.assertEqual('cut',self.items('conflict')[0]['body']['taskId'])
        self.assertFalse(any(r['taskId']=='secure' and r['status']=='scheduled' for r in state['reminders']))

    def test_phase7_day_off_uses_full_dst_day(self):
        from zoneinfo import ZoneInfo
        self.now=datetime(2026,11,1,0,tzinfo=ZoneInfo('America/Los_Angeles'))
        self.hooks.now=self.now
        self.package['startAt']=self.now.isoformat()
        for e in self.package['employees']:
            e['availability']=[{'start':self.now.isoformat(),'end':(self.now+timedelta(days=1)).isoformat()}]
        self.load()
        self.availability('sam','day_off')
        row=self.app.db.execute('SELECT start_at,end_at FROM availability_overrides').fetchone()
        self.assertEqual(timedelta(hours=25),datetime.fromisoformat(row['end_at'])-datetime.fromisoformat(row['start_at']))

    def test_phase7_in_progress_work_respects_new_absence(self):
        self.package['assignments'][0].update(status='in_progress',startedAt=self.package['startAt'])
        self.load()
        result=self.availability('alex','absence')
        self.assertEqual('secure',result['conflicts'][0]['body']['taskId'])
        self.assertEqual('blocked',self.app.state(self.ws,self.incident,self.now)['schedule'][0]['state'])

    def test_phase7_new_hook_shapes_rejected_without_partial_writes(self):
        self.load()
        with self.assertRaises(InvalidInput):
            self.hooks.post('/hooks/employees/sam/availability', {'employeeId':'sam','kind':'late','sourceId':'bad-window','window':[]})
        with self.assertRaises(InvalidInput):
            self.hooks.post(f'/hooks/tasks/{self.incident}/secure/proof',{'employeeId':'alex','sourceId':'bad-proof','proof':[]})
        self.assertEqual(0,self.app.db.execute('SELECT COUNT(*) FROM hook_requests').fetchone()[0])
