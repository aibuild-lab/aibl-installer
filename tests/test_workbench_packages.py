import hashlib,io,json,sys,tempfile,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import workbench_packages as w
class FamilyTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)/'work';self.root.mkdir();self.bundles=Path(self.tmp.name)/'bundles';self.family={'packages':{}}
 def package(self,product,files,version='0.0.10',seed=False):
  folder=self.bundles/product;folder.mkdir(parents=True,exist_ok=True);buf=io.BytesIO();rows=[]
  with zipfile.ZipFile(buf,'w') as z:
   for name,text in files.items():
    raw=text.encode();z.writestr(name,raw);rows.append(dict(path=name,sha256=w.digest(raw),mode=420,policy='seed' if seed else 'supplied'))
  m=dict(schema_version='aibl.family-package/v1',product=product,version=version,source_repository='aibuild-lab/agent-native-workforce-internal',source_revision='a'*40,files=rows);mb=w.encoded(m);ab=buf.getvalue();(folder/'manifest.json').write_bytes(mb);(folder/'payload.zip').write_bytes(ab);self.family['packages'][product]=dict(version=version,manifest_sha256=w.digest(mb),archive_sha256=w.digest(ab),publisher='aibuild-lab/'+product)
 def setup_packages(self):
  self.package('agent-workbench',{'AGENTS.md':'instructions','context/project.md':'seed'},seed=True)
  self.package('agent-essentials',{'course/essentials/start.md':'first'})
 def apply(self,products=None,**kw):return w.compose(self.root,self.bundles,self.family,products or ['agent-workbench','agent-essentials'],**kw)
 def test_fresh_repeat_update_rollback_preserves_student(self):
  self.setup_packages();self.apply();(self.root/'context/project.md').write_text('personal');(self.root/'.aibl-local/progress.json').write_text('my progress');(self.root/'custom.txt').write_text('uncommitted')
  self.assertEqual(self.apply()['status'],'already_installed')
  self.package('agent-essentials',{'course/essentials/start.md':'next'},'0.0.11');result=self.apply();self.assertEqual((self.root/'course/essentials/start.md').read_text(),'next');w.recover(self.root,result['rollback']);self.assertEqual((self.root/'course/essentials/start.md').read_text(),'first');self.assertEqual((self.root/'context/project.md').read_text(),'personal');self.assertEqual((self.root/'.aibl-local/progress.json').read_text(),'my progress');self.assertEqual((self.root/'custom.txt').read_text(),'uncommitted')
 def test_interruption_recovery_then_retry(self):
  self.setup_packages()
  with self.assertRaises(w.ReleaseError):self.apply(fail_after=1)
  with self.assertRaisesRegex(w.ReleaseError,'Interrupted'):self.apply()
  w.recover(self.root);self.apply();self.assertTrue((self.root/w.MARKER).exists())
 def test_changed_supplied_file_no_partial_writes(self):
  self.setup_packages();self.apply();(self.root/'course/essentials/start.md').write_text('my edit');self.package('agent-essentials',{'course/essentials/start.md':'next'},'0.0.11')
  with self.assertRaisesRegex(w.ReleaseError,'Changed supplied'):self.apply()
  self.assertEqual((self.root/'course/essentials/start.md').read_text(),'my edit')
 def test_late_workforce_additive(self):
  self.setup_packages();self.apply();self.package('agent-workforce',{'workforce/job.md':'job'})
  self.apply(['agent-workforce']);self.assertEqual((self.root/'AGENTS.md').read_text(),'instructions');self.assertTrue((self.root/'workforce/job.md').exists())
 def test_workforce_root_rejected(self):
  self.package('agent-workforce',{'AGENTS.md':'override'})
  with self.assertRaises(w.ReleaseError):w.verify(self.bundles,'agent-workforce',self.family['packages']['agent-workforce'])
 def test_tamper_and_symlink_rejected(self):
  self.setup_packages();(self.root/'context').symlink_to(self.bundles,target_is_directory=True)
  with self.assertRaises(w.ReleaseError):self.apply()
  (self.bundles/'agent-essentials/payload.zip').write_bytes(b'bad')
  with self.assertRaises(w.ReleaseError):w.verify(self.bundles,'agent-essentials',self.family['packages']['agent-essentials'])
 def test_rollback_preserves_later_edits(self):
  self.setup_packages();result=self.apply();(self.root/'course/essentials/start.md').write_text('later')
  with self.assertRaisesRegex(w.ReleaseError,'Work changed'):w.recover(self.root,result['rollback'])
 def test_deleted_student_seed_not_recreated(self):
  self.setup_packages();self.apply();(self.root/'context/project.md').unlink();self.apply();self.assertFalse((self.root/'context/project.md').exists())
 def test_legacy_hash_transition_preserves_root_and_unused_tools(self):
  self.setup_packages();(self.root/'.aibl').mkdir();(self.root/'course/essentials').mkdir(parents=True);(self.root/'course/essentials/start.md').write_text('old');(self.root/'AGENTS.md').write_text('my old rules');(self.root/'scripts').mkdir();(self.root/'scripts/old.py').write_text('retained')
  old={'schema_version':'aibl.course-release/v3','product':'agent-essentials','files':[{'path':n,'sha256':w.digest(t.encode()),'mode':420} for n,t in [('course/essentials/start.md','old'),('scripts/old.py','retained')]]};(self.root/'.aibl/installed-agent-essentials.json').write_bytes(w.encoded(old));self.apply();self.assertEqual((self.root/'AGENTS.md').read_text(),'my old rules');self.assertEqual((self.root/'scripts/old.py').read_text(),'retained');self.assertEqual((self.root/'course/essentials/start.md').read_text(),'first')
if __name__=='__main__':unittest.main()

class FamilyAccessTests(unittest.TestCase):
 def test_wrong_account_and_missing_access_fail(self):
  from unittest.mock import patch
  import course_setup
  def wrong(args,cwd=None):
   if args==['gh','api','user']:return '{"login":"wrong"}'
   if args[0]=='git':return 'https://github.com/student/my-workbench.git'
   return '{"private":true,"owner":{"login":"student"}}'
  with patch.object(course_setup,'command',side_effect=wrong):
   with self.assertRaisesRegex(w.ReleaseError,'Signed-in account'):w.verify_student_access('.', ['agent-workforce'])
 def test_private_repo_full_name_parsing(self):
  from unittest.mock import patch
  import course_setup
  calls=[]
  def run(args,cwd=None):
   calls.append(args)
   if args==['gh','api','user']:return '{"login":"student"}'
   if args[0]=='git':return 'https://github.com/student/my-workbench.git'
   return '{"private":true,"owner":{"login":"student"}}'
  with patch.object(course_setup,'command',side_effect=run):self.assertEqual(w.verify_student_access('.', ['agent-workforce']),'student')
  self.assertIn(['gh','api','repos/student/my-workbench'],calls);self.assertIn(['gh','api','repos/aibuild-lab/agent-workforce'],calls)
