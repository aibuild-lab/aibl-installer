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
   self.assertEqual(r['status'],'nothing to select');self.assertEqual(r['chosen'],[])
   self.assertEqual({p['id']:p['access'] for p in r['programs']},{'agent-workforce':'unavailable','the-lab':'unavailable'})
   rec=json.loads((wb/'.aibl'/'enroll.json').read_text());self.assertEqual(rec['schema_version'],'aibl.enroll/v1');self.assertEqual(rec['chosen'],[])
 def test_joined_workforce_enrolls_and_names_the_adoption_skill(self):
  with tempfile.TemporaryDirectory() as d:
   wb=workbench(d);r=self.run_enroll(wb,FakeGh(readable={'aibuild-lab/agent-workforce'}))
   self.assertEqual(r['status'],'selected');self.assertEqual(r['chosen'],['agent-workforce'])
   self.assertEqual(r['next'],[{'id':'agent-workforce','do':'run aibl-enroll to join aibuild-lab/agent-workforce branch student'}])
   rec=json.loads((wb/'.aibl'/'enroll.json').read_text());self.assertEqual(rec['chosen'],['agent-workforce']);self.assertIn('setup_sha256',rec['installer'])
 def test_bundled_lab_is_reported_as_included_not_missing(self):
  with tempfile.TemporaryDirectory() as d:
   wb=workbench(d);r=self.run_enroll(wb,FakeGh(readable={'aibuild-lab/agent-workforce'}))
   lab=next(p for p in r['programs'] if p['id']=='the-lab')
   self.assertEqual(lab['access'],'unavailable');self.assertEqual(lab['included_by'],'Agent Workforce');self.assertNotIn('the-lab',r['chosen'])
 def test_joined_lab_without_an_adoption_route_says_so(self):
  with tempfile.TemporaryDirectory() as d:
   wb=workbench(d);r=self.run_enroll(wb,FakeGh(readable={'aibuild-lab/the-lab'}))
   self.assertEqual(r['chosen'],['the-lab']);self.assertEqual(r['next'][0]['do'],'no verified adoption route yet; ask the course team for supported delivery')
 def test_already_installed_program_is_left_alone_and_rerun_is_a_noop(self):
  with tempfile.TemporaryDirectory() as d:
   wb=workbench(d,installed=[('agent-native-workforce','agent-native-workforce-v0.2.1')]);fake=FakeGh(readable={'aibuild-lab/agent-workforce'})
   r=self.run_enroll(wb,fake);self.assertEqual(r['status'],'nothing to select')
   wf=next(p for p in r['programs'] if p['id']=='agent-workforce');self.assertEqual(wf['installed'],'agent-native-workforce-v0.2.1');self.assertTrue(wf['next'].startswith('installed release recorded'))
   again=self.run_enroll(wb,fake);self.assertEqual(again['status'],'nothing to select');self.assertEqual(again['chosen'],[])
 def test_declining_the_confirmation_changes_nothing(self):
  with tempfile.TemporaryDirectory() as d:
   wb=workbench(d);r=self.run_enroll(wb,FakeGh(readable={'aibuild-lab/agent-workforce'}),ask=lambda _:'n')
   self.assertEqual(r['status'],'declined');self.assertEqual(r['chosen'],[]);self.assertFalse((wb/'.aibl'/'enroll.json').exists())
 def test_yes_skips_the_question(self):
  with tempfile.TemporaryDirectory() as d:
   wb=workbench(d);asked=[];r=self.run_enroll(wb,FakeGh(readable={'aibuild-lab/agent-workforce'}),yes=True,ask=lambda q:asked.append(q) or 'n')
   self.assertEqual(asked,[]);self.assertEqual(r['status'],'selected')
 def test_check_shows_and_writes_nothing(self):
  with tempfile.TemporaryDirectory() as d:
   wb=workbench(d);r=self.run_enroll(wb,FakeGh(readable={'aibuild-lab/agent-workforce'}),check=True)
   self.assertEqual(r['status'],'checked');self.assertFalse((wb/'.aibl'/'enroll.json').exists())
 def test_program_filter_limits_the_enrollment_and_rejects_unknown_ids(self):
  with tempfile.TemporaryDirectory() as d:
   wb=workbench(d);fake=FakeGh(readable={'aibuild-lab/agent-workforce','aibuild-lab/the-lab'})
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
 def test_check_never_pulls_or_changes_the_installer(self):
  with tempfile.TemporaryDirectory() as d:
   wb=workbench(d);fake=FakeGh();self.run_enroll(wb,fake,check=True)
   self.assertFalse(any('pull' in call for call in fake.calls))
 def test_corrupt_installed_records_stop_before_selection(self):
  with tempfile.TemporaryDirectory() as d:
   wb=workbench(d);marker=wb/'.aibl/installed-agent-native-workforce.json'
   for bad in ('{', '{}', '[]', '{"release_id":"the-lab-v1.0.0"}'):
    marker.write_text(bad)
    with self.assertRaises(setup.SetupError):self.run_enroll(wb,FakeGh(),yes=True)
    self.assertEqual(marker.read_text(),bad);self.assertFalse((wb/'.aibl/enroll.json').exists())
 def test_selection_preserves_work_and_local_learning(self):
  with tempfile.TemporaryDirectory() as d:
   wb=workbench(d);(wb/'work').mkdir();(wb/'work/draft.txt').write_text('unsaved draft')
   (wb/'.aibl-local').mkdir();(wb/'.aibl-local/progress.json').write_text('{"pending":true}')
   fake=FakeGh(readable={'aibuild-lab/agent-workforce'})
   self.run_enroll(wb,fake,yes=True);self.run_enroll(wb,fake,yes=True)
   self.assertEqual((wb/'work/draft.txt').read_text(),'unsaved draft')
   self.assertEqual((wb/'.aibl-local/progress.json').read_text(),'{"pending":true}')
   self.assertFalse((wb/'.aibl/installed-agent-native-workforce.json').exists())
 def test_frozen_workbench_rejects_different_engine_before_gh(self):
  with tempfile.TemporaryDirectory() as d:
   wb=workbench(d);(wb/'.aibl/distribution.json').write_text(json.dumps({'installer_commit':'a'*40}))
   fake=FakeGh()
   with self.assertRaises(setup.SetupError):self.run_enroll(wb,fake,check=True)
   self.assertFalse(any(call[0]=='gh' for call in fake.calls))
 def test_dangling_distribution_link_is_not_unpinned(self):
  with tempfile.TemporaryDirectory() as d:
   wb=workbench(d);(wb/'.aibl/distribution.json').symlink_to(Path(d)/'absent')
   fake=FakeGh()
   with self.assertRaises(setup.SetupError):self.run_enroll(wb,fake,check=True)
   self.assertEqual(fake.calls,[])
 def test_linked_record_is_not_followed(self):
  with tempfile.TemporaryDirectory() as d:
   wb=workbench(d);target=Path(d)/'keep';target.write_text('keep')
   (wb/'.aibl/enroll.json').symlink_to(target)
   with self.assertRaises(setup.SetupError):self.run_enroll(wb,FakeGh(),yes=True)
   self.assertEqual(target.read_text(),'keep')
 def test_cli_json_and_plain_output(self):
  with tempfile.TemporaryDirectory() as d:
   wb=workbench(d);fake=FakeGh(readable={'aibuild-lab/agent-workforce'})
   from unittest.mock import patch
   with patch.object(enroll,'command',fake),patch.object(sys,'argv',['enroll.py','--workbench',str(wb),'--yes','--json']),contextlib.redirect_stdout(io.StringIO()) as out:code=enroll.main()
   self.assertEqual(code,0);payload=json.loads(out.getvalue());self.assertEqual(payload['status'],'selected');self.assertEqual(payload['chosen'],['agent-workforce'])
   with patch.object(enroll,'command',fake),patch.object(sys,'argv',['enroll.py','--workbench',str(wb),'--check']),contextlib.redirect_stdout(io.StringIO()) as out:code=enroll.main()
   self.assertEqual(code,0);self.assertIn('Agent Workforce: readable',out.getvalue())
   with patch.object(enroll,'command',FakeGh(signed_in=False)),patch.object(sys,'argv',['enroll.py','--workbench',str(wb)]),contextlib.redirect_stdout(io.StringIO()) as out:code=enroll.main()
   self.assertEqual(code,1);self.assertIn('Enroll paused',out.getvalue())

if __name__=='__main__':unittest.main()
