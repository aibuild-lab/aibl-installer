"""Synthetic CLI status responses; no account or browser operations."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import course_setup as setup
import family_setup_handoff as handoff


class SelectedAppLoginStatus(unittest.TestCase):
    def classify(self,args,code,stdout='',stderr=''):
        result=subprocess.CompletedProcess(args,code,stdout,stderr)
        with patch.object(setup.subprocess,'run',return_value=result):
            with self.assertRaises(setup.SetupError) as raised:
                setup.command(args)
        return raised.exception.reason

    def test_explicit_signed_out_selected_app_status(self):
        self.assertEqual(self.classify(['codex','login','status'],1,stderr='Not logged in\n'),'authentication_missing')
        self.assertEqual(self.classify(['codex','login','status'],1,stdout='Not logged in\n'),'authentication_missing')
        self.assertEqual(self.classify(['claude','auth','status','--json'],1,stdout=json.dumps({'loggedIn':False,'authMethod':'none'})),'authentication_missing')

    def test_other_failures_keep_their_boundary(self):
        codex=['codex','login','status']
        self.assertEqual(self.classify(codex,1,stderr='error connecting: connection refused'),'network')
        self.assertEqual(self.classify(codex,1,stderr='HTTP 403'),'permission')
        self.assertEqual(self.classify(codex,1,stderr='Could not read login storage'),'operation')
        self.assertEqual(self.classify(codex,2,stderr='Not logged in'),'operation')
        self.assertEqual(self.classify(['codex','exec','task'],1,stderr='Not logged in'),'operation')
        self.assertEqual(self.classify(['claude','auth','status','--json'],1,stdout='{"loggedIn":false}',stderr='connection refused'),'network')
        self.assertEqual(self.classify(['claude','auth','status','--json'],1,stdout='invalid JSON'),'operation')
        self.assertEqual(self.classify(['claude','auth','status','--json'],1,stdout='{"loggedIn":false,"error":"storage unavailable"}'),'operation')

    def test_official_handoff_opens_selected_login_then_rechecks(self):
        for harness in ('codex','claude'):
            with self.subTest(harness=harness),tempfile.TemporaryDirectory() as directory:
                home=Path(directory).resolve();revision='a'*40
                engine=home/'.aibl/installers'/revision
                calls=[];logged_in=False
                def process(args,**kwargs):
                    nonlocal logged_in
                    calls.append(args)
                    if args==['gh','api','user']:
                        return subprocess.CompletedProcess(args,0,'{"login":"synthetic","id":1}','')
                    if args==setup.HARNESSES[harness]['status']:
                        if harness=='codex':
                            return subprocess.CompletedProcess(args,0 if logged_in else 1,'','Logged in using ChatGPT' if logged_in else 'Not logged in')
                        return subprocess.CompletedProcess(args,0 if logged_in else 1,json.dumps({'loggedIn':logged_in}),'')
                    if args==setup.HARNESSES[harness]['login']:
                        self.assertFalse(kwargs['capture_output'])
                        logged_in=True
                        return subprocess.CompletedProcess(args,0,None,None)
                    raise AssertionError('Unexpected operation '+repr(args))
                distribution={'installer':{'revision':revision},'family_lock':{}}
                with patch.object(handoff,'__file__',str(engine/'scripts/family_setup_handoff.py')), \
                     patch.object(Path,'home',return_value=home), \
                     patch.object(handoff,'load_distribution',return_value=distribution), \
                     patch.object(setup.subprocess,'run',side_effect=process), \
                     patch.object(handoff,'acquire',return_value={'family_bundles':'synthetic bundles'}), \
                     patch.object(handoff,'setup_standalone',return_value={'status':'synthetic_files_ready'}):
                    result=handoff.setup('synthetic distribution','b'*64,harness,no_launch=True)
                self.assertEqual(result['status'],'synthetic_files_ready')
                self.assertEqual(calls.count(setup.HARNESSES[harness]['login']),1)
                self.assertEqual(calls.count(setup.HARNESSES[harness]['status']),2)


if __name__=='__main__':unittest.main()
