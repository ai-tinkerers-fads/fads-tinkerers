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
