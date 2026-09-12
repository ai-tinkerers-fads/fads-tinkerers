import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fads_coordination.core import Coordination, InvalidInput, stamp
from fads_coordination.demo import FIXTURE, action, initialize, reset_testing, settings


class ResetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'demo.sqlite'
        initialize(self.path)
        self.app=Coordination(self.path)
        self.package=json.loads(FIXTURE.read_text())
        self.ws=self.package['workspaceId']
        self.now=stamp(self.package['startAt'])

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def test_phase7_reset_clears_workspace_and_restores_fixture(self):
        action(self.app,{'action':'seed_history'})
        action(self.app,{'action':'complete','taskId':'secure','actualMinutes':None,'revision':1})
        self.app.add_proof(self.ws,'pine-street-001','cut',{'employeeId':'alex','sourceId':'proof','proof':{'kind':'text','ref':'fixture://proof'}},self.now)
        other=copy.deepcopy(self.package);other['workspaceId']='other-workspace'
        self.app.put_package(other,self.now)
        before=self.app.outbox(self.ws)
        state=reset_testing(self.app,'fixture-tester')
        self.assertEqual(self.package,state['package'])
        self.assertEqual('assigned',state['incidentStatus'])
        self.assertEqual(self.now,stamp(state['now']))
        self.assertEqual([],state['outcomes'])
        self.assertEqual([],state['lessons'])
        self.assertEqual([],state['proofs'])
        self.assertEqual(1,len(state['notifications']))
        self.assertEqual(1,len(state['workflows']))
        for table in ('task_completions','proofs','hook_requests','availability_overrides','outcomes','document_versions','suppressed'):
            self.assertEqual(0,self.app.db.execute(f'SELECT COUNT(*) FROM {table} WHERE workspace=?',(self.ws,)).fetchone()[0])
        self.assertIsNotNone(self.app.get_package('other-workspace','pine-street-001'))
        after=self.app.outbox(self.ws,after=before['nextCursor'])
        self.assertEqual(11,len(after['items']))
        self.assertFalse({i['id'] for i in before['items']} & {i['id'] for i in after['items']})
        self.assertEqual(10,len(self.app.outbox('other-workspace')['items']))
        self.app.close();self.app=Coordination(self.path)
        self.assertEqual(self.package,self.app.state(self.ws,'pine-street-001',self.now)['package'])
        self.assertIn('reset_epoch:'+self.ws,settings(self.app))

    def test_phase7_reset_rolls_back_on_failure_and_requires_caller(self):
        action(self.app,{'action':'seed_history'})
        with self.assertRaises(InvalidInput):
            reset_testing(self.app,None)
        with patch.object(self.app,'_put',side_effect=InvalidInput('fixture failure')):
            with self.assertRaises(InvalidInput):
                reset_testing(self.app,'tester')
        self.assertEqual(5,self.app.db.execute('SELECT COUNT(*) FROM outcomes').fetchone()[0])
        self.assertEqual(self.package,self.app.get_package(self.ws,'pine-street-001'))
