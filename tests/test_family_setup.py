import contextlib,io,json,tempfile,unittest
from pathlib import Path
from test_course_setup import Fake
import test_workbench_packages as fixtures
import course_setup as setup
import enroll
class FamilySetup(unittest.TestCase):
 setUp=fixtures.FamilyTests.setUp
 package=fixtures.FamilyTests.package
 setup_packages=fixtures.FamilyTests.setup_packages
 apply=fixtures.FamilyTests.apply
 def test_fresh_template_then_essentials_without_workforce_access(self):
  self.setup_packages();self.family['template_revision']='a'*40;fake=Fake();fake.template='aibuild-lab/agent-workbench'
  def runner(args,**kw):
   if args==['gh','api','repos/aibuild-lab/agent-workbench/commits/main']:return json.dumps({'sha':'a'*40})
   if args[:3]==['gh','repo','clone']:
    result=fake(args,**kw);folder=Path(args[-1]);(folder/'AGENTS.md').write_text('instructions');(folder/'context').mkdir();(folder/'context/project.md').write_text('seed');return result
   if args==['gh','api','repos/aibuild-lab/agent-workforce']:raise setup.SetupError('not enrolled','not_found')
   return fake(args,**kw)
  with contextlib.redirect_stdout(io.StringIO()):
   result=setup.setup(setup.choose('agent-essentials'),Path(self.tmp.name)/'local','my-workbench',Path(self.tmp.name)/'state',runner,True,harness='codex',family=self.family,family_bundles=self.bundles)
  self.assertEqual(result['status'],'ready');self.assertIn(['gh','repo','create','synthetic-student/my-workbench','--private','--template','aibuild-lab/agent-workbench'],fake.calls)
  folder=Path(result['workspace']);self.assertTrue((folder/'course/essentials/start.md').exists());self.assertFalse(any('agent-workforce' in arg for call in fake.calls for arg in call))
 def test_changed_template_refuses_before_creation(self):
  self.setup_packages();self.family['template_revision']='a'*40;fake=Fake()
  def runner(args,**kw):
   if args==['gh','api','repos/aibuild-lab/agent-workbench/commits/main']:return json.dumps({'sha':'b'*40})
   return fake(args,**kw)
  with self.assertRaisesRegex(setup.SetupError,'Template moved'):
   setup.setup(setup.choose('agent-essentials'),Path(self.tmp.name)/'local','my-workbench',Path(self.tmp.name)/'state',runner,True,family=self.family,family_bundles=self.bundles)
  self.assertFalse(fake.exists)
 def test_family_enroll_uses_successor_publisher(self):
  self.setup_packages();self.apply();calls=[]
  def runner(args,**kw):calls.append(args);return '{}'
  rows=enroll.plan(self.root,runner=runner);wf=next(r for r in rows if r['id']=='agent-workforce');self.assertEqual(wf['publisher'],'aibuild-lab/agent-workforce');self.assertIn('workbench_packages.py',wf['next']);self.assertFalse(wf['installed'])
if __name__=='__main__':unittest.main()
