import datetime as dt
import json
import unittest
from pathlib import Path
import test_workbench_packages as fixtures
import release_discovery as d

class DiscoveryTests(unittest.TestCase):
 setUp=fixtures.FamilyTests.setUp
 package=fixtures.FamilyTests.package
 setup_packages=fixtures.FamilyTests.setup_packages
 apply=fixtures.FamilyTests.apply
 def fixture(self):
  self.setup_packages()
  self.index={'schema_version':'aibl.release-index/v1','product':'agent-essentials','sequence':2,'generated_at':'2026-09-13T00:00:00Z','expires_at':'2026-09-15T00:00:00Z','package':self.family['packages']['agent-essentials'],'installer_revision':'a'*40,'withdrawn':False,'package_url':(self.bundles/'agent-essentials').as_uri()}
  self.path=Path(self.tmp.name)/'index.json'
  self.trust={'schema_version':'aibl.release-trust/v1','product':'agent-essentials','index_url':self.path.as_uri(),'index_sha256':'','allowed_origin':'file://','minimum_sequence':2}
 def check(self,**kw):
  raw=json.dumps(self.index).encode();self.path.write_bytes(raw);self.trust['index_sha256']=d.digest(raw)
  return d.discover(self.trust,'a'*40,now=dt.datetime(2026,9,14,tzinfo=dt.timezone.utc),local_simulation=True,**kw)
 def test_discovery_readonly_and_validation(self):
  self.fixture();before=list(self.root.rglob('*'));self.assertEqual(self.check()['update_availability'],'verified_candidate');self.assertEqual(before,list(self.root.rglob('*')))
  for key,value in [('sequence',1),('product','agent-workforce'),('expires_at','2026-09-13T00:00:00Z'),('installer_revision','b'*40),('schema_version','future')]:
   old=self.index[key];self.index[key]=value;self.assertEqual(self.check()['update_availability'],'unknown');self.index[key]=old
  self.index['withdrawn']=True;self.assertEqual(self.check()['update_availability'],'withdrawn')
 def test_tamper_transport_unknown(self):
  self.fixture();self.check();self.path.write_text('{}');self.assertEqual(d.discover(self.trust,'a'*40,local_simulation=True)['update_availability'],'unknown')
  self.assertEqual(d.discover(self.trust,'a'*40)['update_availability'],'unknown')
  self.path.unlink();self.assertEqual(d.discover(self.trust,'a'*40,local_simulation=True)['update_availability'],'unknown')
 def test_bad_payload_unknown(self):
  self.fixture();(self.bundles/'agent-essentials/payload.zip').write_bytes(b'bad');self.assertEqual(self.check()['update_availability'],'unknown')
 def test_repair_preserves_and_rolls_back(self):
  self.setup_packages();self.apply();name='course/essentials/start.md';p=self.root/name;p.write_text('personal')
  expected={name:digest_snapshot(self.root,name)}
  result=d_repair(self,name,expected);self.assertEqual(p.read_text(),'first')
  import workbench_packages as w
  w.recover(self.root,result['rollback']);self.assertEqual(p.read_text(),'personal')
 def test_repair_later_edit_refused(self):
  self.setup_packages();self.apply();name='course/essentials/start.md';expected={name:digest_snapshot(self.root,name)};(self.root/name).write_text('later')
  import workbench_packages as w
  with self.assertRaisesRegex(w.ReleaseError,'changed'):d_repair(self,name,expected)
 def test_repair_deletion_interruption(self):
  self.setup_packages();self.apply();name='course/essentials/start.md';(self.root/name).unlink()
  import workbench_packages as w
  with self.assertRaises(w.ReleaseError):w.repair(self.root,self.bundles,'agent-essentials',[name],{name:None},fail_after=1)
  w.recover(self.root);self.assertFalse((self.root/name).exists())

 def test_unadmitted_package_origin(self):
  self.fixture();self.index['package_url']='https://unadmitted.invalid/bundle';self.assertEqual(self.check()['update_availability'],'unknown')
 def test_repair_seed_and_unowned_refused(self):
  self.setup_packages();self.apply()
  import workbench_packages as w
  name='context/project.md'
  with self.assertRaisesRegex(w.ReleaseError,'supplied'):w.repair(self.root,self.bundles,'agent-workbench',[name],{name:w.snapshot(self.root,name)})
 def test_repair_rollback_later_work_and_backup_integrity(self):
  self.setup_packages();self.apply();name='course/essentials/start.md';p=self.root/name;p.write_text('mine')
  import workbench_packages as w
  result=d_repair(self,name,{name:w.snapshot(self.root,name)});p.write_text('later')
  with self.assertRaisesRegex(w.ReleaseError,'changed'):w.recover(self.root,result['rollback'])
  p.write_text('first');(self.root/'.aibl-local/family-backups'/result['rollback']/name).write_text('tampered')
  with self.assertRaisesRegex(w.ReleaseError,'integrity'):w.recover(self.root,result['rollback'])

def digest_snapshot(root,name):
 import workbench_packages as w
 return w.snapshot(root,name)
def d_repair(case,name,expected):
 import workbench_packages as w
 return w.repair(case.root,case.bundles,'agent-essentials',[name],expected)
