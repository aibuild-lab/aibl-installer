"""Real hashes/packages and local Git, synthetic provider/app/engine boundaries."""
import copy
import json
from pathlib import Path
import subprocess
import shutil
import unittest
from unittest.mock import patch
import test_frozen_family as fixtures
import frozen_family
import workbench_distribution as d
import workbench_packages as packages
import enrollment_v2
import enroll
import family_setup_handoff as handoff
import test_standalone_enrollment as standalone_fixtures
import standalone_setup


class RetainedDistribution(unittest.TestCase):
    save=fixtures.FrozenFamily.save
    runner=fixtures.FrozenFamily.runner

    def setUp(self):
        fixtures.FrozenFamily.setUp(self)
        self.workbench=self.root/'projects/my-workbench';self.custody=self.root/'custody'
        self.acquire_patch=patch.object(d,'acquire',side_effect=lambda *args,**kwargs:frozen_family.acquire(*args,**kwargs,now=fixtures.NOW))
        self.acquire_patch.start();self.addCleanup(self.acquire_patch.stop)

    def retain(self):
        return d.retain(self.workbench,'student/my-workbench',self.engine,self.path,self.sha,state_root=self.custody,runner=self.runner)

    def base(self):
        folder,row,value=self.retain()
        inputs=d.cached_inputs(folder,row,value,self.engine,['agent-workbench','workbench-core'],github=self.github,runner=self.runner)
        self.workbench.mkdir(parents=True)
        packages.compose(self.workbench,inputs['family_bundles'],self.family,['agent-workbench','workbench-core'])
        subprocess.run(['git','init','-b','main',str(self.workbench)],check=True,capture_output=True)
        subprocess.run(['git','remote','add','origin','https://github.com/student/my-workbench.git'],cwd=self.workbench,check=True,capture_output=True)
        return folder,row,value

    def student(self,args,cwd=None):
        if args==['gh','api','user']:return '{"login":"student","id":1}'
        if args==['gh','api','repos/student/my-workbench']:return '{"private":true,"full_name":"student/my-workbench","owner":{"login":"student"}}'
        return subprocess.check_output(args,cwd=cwd,text=True).strip()

    def selected(self,product='agent-workforce'):
        return d.enrollment_inputs(self.workbench,product,self.engine,state_root=self.custody,runner=self.student,engine_runner=self.runner,github=self.github)

    def test_original_admission_retained_before_effects_and_reused(self):
        first=self.retain();self.assertFalse(self.workbench.exists())
        self.assertEqual(first,self.retain())
        self.assertEqual((first[0]/'distribution.json').read_bytes(),self.path.read_bytes())
        self.assertEqual((first[0]/'association.json').stat().st_mode&0o777,0o600)
        changed=copy.deepcopy(self.distribution);changed['family_lock']['template_revision']='c'*40
        changed['family_lock']['packages']['agent-workbench']['release_target']='c'*40
        changed['family_sha256']=d.digest(d.encoded(changed['family_lock']))
        other=self.root/'other.json';other.write_bytes(d.encoded(changed))
        with self.assertRaisesRegex(d.SetupError,'changed'):
            d.retain(self.workbench,'student/my-workbench',self.engine,other,d.digest(other.read_bytes()),state_root=self.custody,runner=self.runner)

    def test_selected_only_download_with_complete_reverified_local_bundle_set(self):
        self.base();self.github.calls.clear()
        before=(self.workbench/'.aibl/family.json').read_bytes()
        inputs=self.selected()
        self.assertTrue(any(repo=='aibuild-lab/agent-workforce' for repo,_ in self.github.calls))
        self.assertFalse(any(repo==packages.PUBLIC_TEMPLATE for repo,_ in self.github.calls))
        for product in ('agent-workbench','workbench-core','agent-workforce'):packages.verify(inputs['family_bundles'],product,self.family['packages'][product])
        self.assertFalse((Path(inputs['family_bundles'])/'agent-essentials').exists())
        self.assertEqual(before,(self.workbench/'.aibl/family.json').read_bytes())
        self.assertEqual(packages.compose(self.workbench,inputs['family_bundles'],self.family,['agent-workforce'],preview=True)['status'],'ready')

    def test_missing_association_and_wrong_origin_do_not_acquire(self):
        self.base();self.github.calls.clear()
        with patch.object(d,'directory',return_value=self.root/'absent'):
            with self.assertRaisesRegex(d.SetupError,'official independently'):self.selected()
        with patch.object(enrollment_v2,'identity',return_value=({},'other/repo')):
            with self.assertRaisesRegex(d.SetupError,'association differs'):self.selected()
        self.assertEqual(self.github.calls,[])

    def test_pending_sync_stops_before_identity_or_cache_acquisition(self):
        folder,_,_=self.base()
        pending=self.workbench/packages.SYNC_PENDING
        pending.write_text('{}')
        before={p.relative_to(folder).as_posix():p.read_bytes() for p in folder.rglob('*') if p.is_file()}
        self.github.calls.clear()
        with patch.object(enrollment_v2,'identity') as identity:
            with self.assertRaisesRegex(packages.ReleaseError,'existing student update'):
                self.selected()
            identity.assert_not_called()
        self.assertEqual(self.github.calls,[])
        self.assertEqual(before,{p.relative_to(folder).as_posix():p.read_bytes() for p in folder.rglob('*') if p.is_file()})

    def test_tampered_distribution_and_installed_cache_stop_before_network(self):
        folder,row,value=self.base();self.github.calls.clear()
        cache=folder/'bundles/workbench-core/payload.zip';old=cache.read_bytes();cache.write_bytes(b'changed')
        with self.assertRaises(packages.ReleaseError):self.selected()
        cache.write_bytes(old)
        (folder/'distribution.json').write_bytes(b'changed')
        with self.assertRaises(packages.ReleaseError):self.selected()
        self.assertEqual(self.github.calls,[])

    def test_new_family_cannot_be_admitted_from_installed_marker(self):
        self.base();self.github.calls.clear()
        marker=self.workbench/'.aibl/family.json';value=json.loads(marker.read_bytes())
        value['family']['template_revision']='f'*40;marker.write_bytes(d.encoded(value))
        with self.assertRaisesRegex(d.SetupError,'original setup admission'):self.selected()
        self.assertEqual(self.github.calls,[])

    def test_cached_optional_candidate_does_not_bypass_new_admission_failure(self):
        self.base();self.selected()
        with patch.object(d,'acquire',side_effect=packages.ReleaseError('Synthetic expired index')):
            with self.assertRaisesRegex(packages.ReleaseError,'expired'):self.selected()

    def test_interrupted_acquisition_retries_same_association(self):
        first=self.retain()
        with patch.object(d,'acquire',side_effect=OSError('synthetic interrupted download')):
            with self.assertRaises(OSError):d.cached_inputs(*first,self.engine,['agent-workbench','workbench-core'],github=self.github,runner=self.runner)
        self.assertEqual(first,self.retain())
        inputs=d.cached_inputs(*first,self.engine,['agent-workbench','workbench-core'],github=self.github,runner=self.runner)
        packages.verify(inputs['family_bundles'],'workbench-core',self.family['packages']['workbench-core'])

    def test_preview_without_trio_routes_through_retained_admission(self):
        self.base();result={'family_lock':'lock','family_sha256':'digest','family_bundles':'bundles'}
        with patch('sys.argv',['enroll','--workbench',str(self.workbench),'--preview','--program','agent-workforce']),patch.object(enroll,'find_workbench',return_value=self.workbench),patch.object(enroll,'verify_engine'),patch.object(d,'enrollment_inputs',return_value=result) as resolver,patch.object(enrollment_v2,'preview',return_value={'status':'previewed'}) as preview,patch('builtins.print'):
            enroll.main()
        resolver.assert_called_once();preview.assert_called_once_with(self.workbench,'agent-workforce','lock','digest','bundles')

    def test_established_handoff_rerun_reads_only_and_rejects_substitution(self):
        folder,row,value=self.base()
        home=self.root/'home';engine=home/'.aibl/installers'/self.revision
        with patch.object(handoff,'__file__',str(engine/'scripts/family_setup_handoff.py')),patch.object(Path,'home',return_value=home),patch.object(handoff,'load_distribution',return_value=value),patch.object(handoff,'command',return_value='{"login":"student","id":1}'),patch('standalone_setup.signed_in'),patch.object(handoff,'setup_standalone',return_value={'status':'already_initialized'}) as setup,patch.object(handoff,'read_association',return_value=(folder,row,value)),patch.object(handoff,'retain') as retain,patch.object(handoff,'cached_inputs') as acquire:
            self.assertEqual(handoff.setup(self.path,self.sha,'codex',self.workbench.parent,no_launch=True)['status'],'already_initialized')
            with self.assertRaisesRegex(d.SetupError,'distribution changed'):handoff.setup(self.path,'b'*64,'codex',self.workbench.parent,no_launch=True)
        retain.assert_not_called();acquire.assert_not_called()
        self.assertTrue(all(call.kwargs['no_launch'] for call in setup.call_args_list))


class OfficialSetupEnrollment(unittest.TestCase):
    setUp=standalone_fixtures.StandaloneEnrollment.setUp
    package=standalone_fixtures.StandaloneEnrollment.package
    v2=standalone_fixtures.StandaloneEnrollment.v2

    def test_setup_then_preview_and_confirm_without_manual_candidate_paths(self):
        home=self.base.resolve()/'home';engine=home/'.aibl/installers'/self.family['installer_revision']
        distribution=self.base.resolve()/'official.json'
        value={'installer':{'revision':self.family['installer_revision']},'family_lock':self.family,'family_sha256':self.lockhash}
        distribution.write_bytes(d.encoded(value));sha=d.digest(distribution.read_bytes())
        downloaded=[]
        def admitted(path,expected_sha,root,**kwargs):
            self.assertEqual(root,engine);self.assertEqual(d.digest(Path(path).read_bytes()),expected_sha)
            return json.loads(Path(path).read_bytes())
        def acquire(path,expected_sha,root,output,products,**kwargs):
            admitted(path,expected_sha,root);downloaded.append(list(products))
            bundles=Path(output)/'bundles'
            for product in products:shutil.copytree(self.bundles/product,bundles/product)
            return {'family_bundles':str(bundles)}
        def setup(workspace,name,family,bundles,**kwargs):
            return standalone_setup.setup_standalone(workspace,name,family,bundles,state_root=home/'setup-state',runner=self.services,**kwargs)
        with patch.object(Path,'home',return_value=home),patch.object(handoff,'__file__',str(engine/'scripts/family_setup_handoff.py')),patch.object(handoff,'load_distribution',side_effect=admitted),patch.object(d,'load_distribution',side_effect=admitted),patch.object(d,'acquire',side_effect=acquire),patch.object(handoff,'command',side_effect=self.services),patch.object(standalone_setup,'signed_in'),patch.object(handoff,'setup_standalone',side_effect=setup):
            self.services.lose_creation=True
            with self.assertRaisesRegex(d.SetupError,'Lost creation'):
                handoff.setup(distribution,sha,'codex',self.base.resolve()/'projects',no_launch=True)
            association=d.directory(self.base.resolve()/'projects/my-workbench')/'association.json'
            original_admission=association.read_bytes()
            result=handoff.setup(distribution,sha,'codex',self.base.resolve()/'projects',no_launch=True)
            self.assertEqual(original_admission,association.read_bytes())
            self.assertEqual(sum(call[:3]==['gh','repo','create'] for call in self.services.calls),1)
            workbench=Path(result['workspace'])
            inputs=d.enrollment_inputs(workbench,'agent-workforce',engine,runner=self.services)
            plan=enrollment_v2.preview(workbench,'agent-workforce',inputs['family_lock'],inputs['family_sha256'],inputs['family_bundles'],runner=self.services,state_root=self.plans)
            self.assertEqual(plan['status'],'previewed')
            self.assertFalse((workbench/'workforce/guide.md').exists())
            installed=enrollment_v2.apply_plan(workbench,plan['plan_id'],runner=self.services,state_root=self.plans)
            self.assertEqual(installed['status'],'installed')
            self.assertEqual(installed['native_verification'],'pending')
            self.assertEqual(downloaded,[['agent-workbench','workbench-core'],['agent-workbench','workbench-core'],['agent-workforce']])
            self.assertFalse((workbench/'blueprints/youtube-transcripts.md').exists())


if __name__=='__main__':unittest.main()
