import contextlib,io,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import enroll,course_setup as setup

class FakeGh:
 """gh api repos/<publisher>: readable publishers answer, others 404. git pull is recorded, never run."""
 def __init__(self,readable=(),signed_in=True,network_down=False):self.readable=set(readable);self.signed_in=signed_in;self.network_down=network_down;self.calls=[]
 def __call__(self,args,cwd=None,interactive=False):
  self.calls.append(args)
  if args[:2]==['git','-C']:return ''
  if args[:2]==['gh','api']:
   if not self.signed_in:raise setup.SetupError('gh api failed','authentication_missing')
   if self.network_down:raise setup.SetupError('gh api failed','network')
   repo=args[2].removeprefix('repos/')
   if repo in self.readable:return json.dumps({'private':True,'full_name':repo})
   raise setup.SetupError('HTTP 404','not_found')
  return ''

def workbench(root,installed=()):
 wb=Path(root)/'my-workbench';(wb/'.aibl').mkdir(parents=True)
 for product,release in installed:(wb/'.aibl'/('installed-'+product+'.json')).write_text(json.dumps({'release_id':release}))
 return wb

class EnrollTests(unittest.TestCase):
 def run_enroll(self,wb,fake,**kw):
  with contextlib.redirect_stdout(io.StringIO()):return enroll.enroll(str(wb),runner=fake,ask=kw.pop('ask',lambda _:'y'),**kw)
 def test_registry_names_an_adoption_skill_per_program(self):
  reg=setup.registry();skills={p['id']:p.get('adopt_skill') for p in reg['programs']}
  self.assertEqual(skills,{'agent-essentials':None,'agent-workforce':'aibl-adopt-workforce','the-lab':None})
  self.assertEqual([p['id'] for p in enroll.programs(reg)],['agent-workforce','the-lab'])
 def test_not_invited_anywhere_records_and_enrolls_nothing(self):
  with tempfile.TemporaryDirectory() as d:
   wb=workbench(d);r=self.run_enroll(wb,FakeGh())
   self.assertEqual(r['status'],'nothing to enroll');self.assertEqual(r['chosen'],[])
   self.assertEqual({p['id']:p['access'] for p in r['programs']},{'agent-workforce':'not invited','the-lab':'not invited'})
   rec=json.loads((wb/'.aibl'/'enroll.json').read_text());self.assertEqual(rec['schema_version'],'aibl.enroll/v1');self.assertEqual(rec['chosen'],[])
 def test_joined_workforce_enrolls_and_names_the_adoption_skill(self):
  with tempfile.TemporaryDirectory() as d:
   wb=workbench(d);r=self.run_enroll(wb,FakeGh(readable={'aibuild-lab/agent-native-workforce'}))
   self.assertEqual(r['status'],'enrolled');self.assertEqual(r['chosen'],['agent-workforce'])
   self.assertEqual(r['next'],[{'id':'agent-workforce','do':'run aibl-adopt-workforce'}])
   rec=json.loads((wb/'.aibl'/'enroll.json').read_text());self.assertEqual(rec['chosen'],['agent-workforce']);self.assertIn('setup_sha256',rec['installer'])
 def test_bundled_lab_is_reported_as_included_not_missing(self):
  with tempfile.TemporaryDirectory() as d:
   wb=workbench(d);r=self.run_enroll(wb,FakeGh(readable={'aibuild-lab/agent-native-workforce'}))
   lab=next(p for p in r['programs'] if p['id']=='the-lab')
   self.assertEqual(lab['access'],'included, invitation pending');self.assertEqual(lab['included_by'],'Agent Workforce');self.assertNotIn('the-lab',r['chosen'])
 def test_joined_lab_without_an_adoption_route_says_so(self):
  with tempfile.TemporaryDirectory() as d:
   wb=workbench(d);r=self.run_enroll(wb,FakeGh(readable={'aibuild-lab/the-lab'}))
   self.assertEqual(r['chosen'],['the-lab']);self.assertEqual(r['next'][0]['do'],'no adoption route yet; clone beside the workbench for now')
 def test_already_installed_program_is_left_alone_and_rerun_is_a_noop(self):
  with tempfile.TemporaryDirectory() as d:
   wb=workbench(d,installed=[('agent-native-workforce','agent-native-workforce-v0.2.1')]);fake=FakeGh(readable={'aibuild-lab/agent-native-workforce'})
   r=self.run_enroll(wb,fake);self.assertEqual(r['status'],'nothing to enroll')
   wf=next(p for p in r['programs'] if p['id']=='agent-workforce');self.assertEqual(wf['installed'],'agent-native-workforce-v0.2.1');self.assertTrue(wf['next'].startswith('already in this workbench'))
   again=self.run_enroll(wb,fake);self.assertEqual(again['status'],'nothing to enroll');self.assertEqual(again['chosen'],[])
 def test_declining_the_confirmation_changes_nothing(self):
  with tempfile.TemporaryDirectory() as d:
   wb=workbench(d);r=self.run_enroll(wb,FakeGh(readable={'aibuild-lab/agent-native-workforce'}),ask=lambda _:'n')
   self.assertEqual(r['status'],'declined');self.assertEqual(r['chosen'],[]);self.assertEqual(json.loads((wb/'.aibl'/'enroll.json').read_text())['chosen'],[])
 def test_yes_skips_the_question(self):
  with tempfile.TemporaryDirectory() as d:
   wb=workbench(d);asked=[];r=self.run_enroll(wb,FakeGh(readable={'aibuild-lab/agent-native-workforce'}),yes=True,ask=lambda q:asked.append(q) or 'n')
   self.assertEqual(asked,[]);self.assertEqual(r['status'],'enrolled')
 def test_check_shows_and_writes_nothing(self):
  with tempfile.TemporaryDirectory() as d:
   wb=workbench(d);r=self.run_enroll(wb,FakeGh(readable={'aibuild-lab/agent-native-workforce'}),check=True)
   self.assertEqual(r['status'],'checked');self.assertFalse((wb/'.aibl'/'enroll.json').exists())
 def test_program_filter_limits_the_enrollment_and_rejects_unknown_ids(self):
  with tempfile.TemporaryDirectory() as d:
   wb=workbench(d);fake=FakeGh(readable={'aibuild-lab/agent-native-workforce','aibuild-lab/the-lab'})
   r=self.run_enroll(wb,fake,only=['the-lab']);self.assertEqual(r['chosen'],['the-lab'])
   with self.assertRaises(setup.SetupError):self.run_enroll(wb,fake,only=['legacy-workshop'])
 def test_signed_out_github_is_a_plain_stop_not_absence(self):
  with tempfile.TemporaryDirectory() as d:
   wb=workbench(d)
   with self.assertRaises(setup.SetupError) as cm:self.run_enroll(wb,FakeGh(signed_in=False))
   self.assertEqual(cm.exception.reason,'authentication_missing');self.assertIn('gh auth login',str(cm.exception));self.assertFalse((wb/'.aibl'/'enroll.json').exists())
 def test_network_failure_is_never_read_as_not_invited(self):
  with tempfile.TemporaryDirectory() as d:
   wb=workbench(d)
   with self.assertRaises(setup.SetupError) as cm:self.run_enroll(wb,FakeGh(network_down=True))
   self.assertEqual(cm.exception.reason,'network');self.assertFalse((wb/'.aibl'/'enroll.json').exists())
 def test_missing_workbench_names_where_it_looked(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(setup.SetupError) as cm:enroll.find_workbench(str(Path(d)/'nowhere'))
   self.assertIn('nowhere',str(cm.exception));self.assertEqual(cm.exception.reason,'local_state')
 def test_installer_refresh_is_best_effort(self):
  fake=FakeGh();self.assertIn(enroll.refresh_installer(fake)['refreshed'],(True,False))
  class Offline(FakeGh):
   def __call__(self,args,cwd=None,interactive=False):
    if args[:2]==['git','-C']:raise setup.SetupError('git pull failed','network')
    return super().__call__(args,cwd,interactive)
  r=enroll.refresh_installer(Offline())
  if (setup.ROOT/'.git').exists():self.assertEqual(r,{'refreshed':False,'reason':'network'})
 def test_cli_json_and_plain_output(self):
  with tempfile.TemporaryDirectory() as d:
   wb=workbench(d);fake=FakeGh(readable={'aibuild-lab/agent-native-workforce'})
   from unittest.mock import patch
   with patch.object(enroll,'command',fake),patch.object(sys,'argv',['enroll.py','--workbench',str(wb),'--yes','--json']),contextlib.redirect_stdout(io.StringIO()) as out:code=enroll.main()
   self.assertEqual(code,0);payload=json.loads(out.getvalue());self.assertEqual(payload['status'],'enrolled');self.assertEqual(payload['chosen'],['agent-workforce'])
   with patch.object(enroll,'command',fake),patch.object(sys,'argv',['enroll.py','--workbench',str(wb),'--check']),contextlib.redirect_stdout(io.StringIO()) as out:code=enroll.main()
   self.assertEqual(code,0);self.assertIn('Agent Workforce: joined',out.getvalue())
   with patch.object(enroll,'command',FakeGh(signed_in=False)),patch.object(sys,'argv',['enroll.py','--workbench',str(wb)]),contextlib.redirect_stdout(io.StringIO()) as out:code=enroll.main()
   self.assertEqual(code,1);self.assertIn('Enroll paused',out.getvalue())

if __name__=='__main__':unittest.main()
