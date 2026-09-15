import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch
import test_student_updates as fixtures
import student_updates as u


class Observations(unittest.TestCase):
    setUp=fixtures.Updates.setUp
    package=fixtures.Updates.package
    apply=fixtures.Updates.apply
    v2=fixtures.Updates.v2
    prepare=fixtures.Updates.prepare
    merge=fixtures.Updates.merge

    def synchronized(self):
        self.merge();state=u.synchronize(self.root,'one')
        evidence=Path(self.tmp.name).resolve()/'private-evidence.txt';evidence.write_text('Synthetic first-action evidence, not native proof')
        self.observation=Path(self.tmp.name).resolve()/'observation.json'
        self.value={'schema_version':'aibl.native-update-observation/v1','operation':'one','repository':state['repository'],'local_revision':state['local_synchronized_revision'],'family_sha256':state['family_sha256'],'observer':'synthetic fixture','observed_at':'2026-09-14T00:00:00Z','app':{'id':'codex','version':'synthetic-1'},'os':{'name':'synthetic OS','version':'1'},'fresh_session':True,'discovered_skills':['aibl-enroll','aibl-personalize','aibl-checkpoint'],'first_action':{'status':'passed','description':'Synthetic fixture action','evidence':{'path':str(evidence),'sha256':u.digest(evidence.read_bytes())}}}
        return state

    def record(self,value=None):
        self.observation.write_bytes(u.encoded(value or self.value))
        return u.record_verification(self.root,'one',self.observation,u.digest(self.observation.read_bytes()))

    def test_exact_observation_records_provenance_without_claiming_native_or_acceptance(self):
        self.synchronized();result=self.record()
        self.assertEqual(result['stage'],'observation_recorded')
        self.assertEqual(result['native_verification'],'caller_observation_recorded')
        self.assertFalse(result['automated_native_proof']);self.assertEqual(result['human_acceptance'],'not_recorded')
        self.assertIn('independently supplied',result['verification_observation']['provenance'])
        self.assertEqual(result,self.record())
        self.assertEqual(self.backend.creates,1);self.assertEqual(self.backend.merges,1)

    def test_missing_and_failed_observations_stay_pending(self):
        state=self.synchronized()
        with self.assertRaises(u.ReleaseError):u.record_verification(self.root,'one',None,None)
        for key,value in [('fresh_session',False),('discovered_skills',[]),('observer',''),('observed_at','2999-01-01T00:00:00Z')]:
            changed=copy.deepcopy(self.value);changed[key]=value
            with self.subTest(key=key),self.assertRaises(u.ReleaseError):self.record(changed)
        changed=copy.deepcopy(self.value);changed['first_action']['status']='failed'
        with self.assertRaises(u.ReleaseError):self.record(changed)
        self.assertEqual(u.read_state(self.root,'one'),state)

    def test_each_identity_binding_and_app_metadata_required(self):
        state=self.synchronized()
        for key in ('operation','repository','local_revision','family_sha256'):
            changed=copy.deepcopy(self.value);changed[key]='wrong'
            with self.subTest(key=key),self.assertRaises(u.ReleaseError):self.record(changed)
        for key,value in [('app',{'id':'other','version':'1'}),('app',{'id':'codex','version':''}),('os',{'name':'test','version':''})]:
            changed=copy.deepcopy(self.value);changed[key]=value
            with self.assertRaises(u.ReleaseError):self.record(changed)
        self.assertEqual(u.read_state(self.root,'one'),state)

    def test_artifact_hashes_and_nonsymlink_files_required(self):
        state=self.synchronized();self.observation.write_bytes(u.encoded(self.value))
        with self.assertRaises(u.ReleaseError):u.record_verification(self.root,'one',self.observation,'0'*64)
        evidence=Path(self.value['first_action']['evidence']['path']);evidence.write_text('changed')
        with self.assertRaises(u.ReleaseError):self.record()
        link=Path(self.tmp.name)/'evidence-link';link.symlink_to(evidence)
        self.value['first_action']['evidence'].update(path=str(link),sha256=u.digest(evidence.read_bytes()))
        with self.assertRaises(u.ReleaseError):self.record()
        self.assertEqual(u.read_state(self.root,'one'),state)

    def test_current_origin_head_and_managed_bytes_rechecked_even_on_repeat(self):
        self.synchronized();self.record()
        with patch.object(u,'repository',return_value='other/repo'):
            with self.assertRaisesRegex(u.ReleaseError,'origin changed'):self.record()
        target=self.root/'.agents/skills/aibl-enroll/SKILL.md';before=target.read_bytes();target.write_text('changed')
        with self.assertRaisesRegex(u.ReleaseError,'managed bytes'):self.record()
        target.write_bytes(before)
        u.git(self.root,'commit','--allow-empty','-m','later')
        with self.assertRaisesRegex(u.ReleaseError,'local revision'):self.record()

    def test_conflicting_observation_preserves_first_receipt(self):
        self.synchronized();first=self.record();self.value['observer']='another fixture'
        with self.assertRaisesRegex(u.ReleaseError,'different observation'):self.record()
        self.assertEqual(u.read_state(self.root,'one'),first)

    def test_requires_local_sync_and_supports_claude_inventory(self):
        self.prepare()
        with self.assertRaisesRegex(u.ReleaseError,'Synchronize'):u.record_verification(self.root,'one','unused','0'*64)
        self.synchronized();self.value['app']['id']='claude'
        self.assertEqual(self.record()['stage'],'observation_recorded')


if __name__=='__main__':unittest.main()
