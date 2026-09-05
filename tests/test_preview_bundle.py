"""Candidate source stays local; private Git setup uses the existing test service."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
import test_pinned_distribution as fixtures
import course_setup as setup
import pinned_distribution as pinned


class PreviewTests(unittest.TestCase):
    def prepare(self,root):
        services=fixtures.PinnedServices(root)
        bundle=root/'candidate';bundle.mkdir()
        for product in pinned.PRODUCTS:
            folder=bundle/product;folder.mkdir()
            manifest=json.loads(services.manifest_bytes)
            manifest['product']=product;manifest['release_id']=product+'-v0.0.0-synthetic'
            data=pinned.encoded(manifest)
            (folder/'manifest.json').write_bytes(data);(folder/'payload.zip').write_bytes(services.archive)
            services.distribution['source_release_pins'][product]['manifest_sha256']=pinned.digest(data)
        lock=root/'independent-lock.json';lock.write_bytes(pinned.encoded(services.distribution))
        return services,bundle,lock,pinned.digest(lock.read_bytes())

    def run_setup(self,services,root,bundle,lock,sha,rehearsal='ui-first'):
        with contextlib.redirect_stdout(io.StringIO()):
            return setup.setup(setup.choose('agent-native-workforce'),root/'projects','my-workbench',
                root/'state',services,True,services.distribution,sha,str(bundle) if bundle is not None else None,str(lock),rehearsal)

    def test_preview_seeds_exact_local_bytes_and_retains_rehearsal_outside_git(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();services,bundle,lock,sha=self.prepare(root)
            result=self.run_setup(services,root,bundle,lock,sha);project=Path(result['workspace'])
            self.assertEqual(result['delivery_mode'],'local_candidate');self.assertEqual(result['actor'],'automated_test')
            self.assertFalse(result['course_credit'])
            self.assertFalse(any(call[:3]==['gh','release','download'] for call in services.calls))
            self.assertFalse(any(call[:2]==['gh','api'] and 'aibuild-lab/' in call[-1] for call in services.calls))
            self.assertEqual(json.loads((project/'.aibl/distribution.json').read_bytes())['delivery_mode'],'local_candidate')
            transport=json.loads((project/'.aibl-local/candidate-distribution.json').read_bytes())
            self.assertEqual(transport['bundle_root'],str(bundle));self.assertEqual(transport['distribution_sha256'],sha)
            self.assertEqual(json.loads((project/'.aibl-local/rehearsal.json').read_bytes())['rehearsal_id'],'ui-first')
            self.assertEqual(services.git('ls-files','.aibl-local',cwd=project),'')
            attempt=json.loads((root/'state/my-workbench.json').read_bytes())['attempts'][-1]
            self.assertEqual(attempt['stages']['candidate_inputs'],'PASS')
            self.assertEqual(attempt['stages']['course_access'],'NOT_RUN')
            self.run_setup(services,root,bundle,lock,sha)
            self.assertEqual(sum(call[:3]==['gh','repo','create'] for call in services.calls),1)

    def test_anw_demo_011_rehearsal_uses_selected_account_despite_inactive_status_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();services,bundle,lock,sha=self.prepare(root)
            def selected(args,**kwargs):
                if args[:3]==['gh','auth','status']:
                    services.calls.append(args);raise setup.SetupError('Inactive saved account is invalid','authentication')
                return services(args,**kwargs)
            with contextlib.redirect_stdout(io.StringIO()):
                result=setup.setup(setup.choose('agent-native-workforce'),root/'projects','my-workbench',
                    root/'state',selected,True,services.distribution,sha,str(bundle),str(lock),'ui-first')
            self.assertEqual(result['status'],'ready');self.assertEqual(result['actor'],'automated_test')
            self.assertFalse(any(call[:2]==['gh','auth'] for call in services.calls))
            self.assertEqual(sum(call[:3]==['gh','repo','create'] for call in services.calls),1)

    def test_rehearsal_missing_selected_auth_never_automates_login(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();services,bundle,lock,sha=self.prepare(root)
            def missing(args,**kwargs):
                if args==['gh','api','user']:
                    services.calls.append(args);raise setup.SetupError('Authentication required','authentication_missing')
                return services(args,**kwargs)
            with contextlib.redirect_stdout(io.StringIO()),self.assertRaisesRegex(setup.SetupError,'no account enrollment or login'):
                setup.setup(setup.choose('agent-native-workforce'),root/'projects','my-workbench',
                    root/'state',missing,True,services.distribution,sha,str(bundle),str(lock),'ui-first')
            self.assertFalse(any(call[:2]==['gh','auth'] or call[:3]==['gh','repo','create'] for call in services.calls))
            attempt=json.loads((root/'state/my-workbench.json').read_text())['attempts'][-1]
            self.assertEqual(attempt['failure_domain'],'authentication_missing')
            self.assertEqual(attempt['stages']['private_repository'],'NOT_RUN')

    def test_missing_changed_or_wrong_digest_preview_stops_before_account_calls(self):
        for kind in ('missing','changed','wrong-digest'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as directory:
                root=Path(directory).resolve();services,bundle,lock,sha=self.prepare(root)
                path=bundle/'agent-native-workforce/payload.zip'
                if kind=='missing':path.unlink()
                elif kind=='changed':path.write_bytes(b'corrupt')
                else:sha='0'*64
                with self.assertRaises(ValueError):self.run_setup(services,root,bundle,lock,sha)
                self.assertFalse(any(call[0]=='gh' for call in services.calls))
                self.assertFalse((root/'projects/my-workbench').exists())

    def test_preview_cannot_resume_with_download_fallback_or_different_rehearsal(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();services,bundle,lock,sha=self.prepare(root)
            self.run_setup(services,root,bundle,lock,sha)
            with self.assertRaisesRegex(ValueError,'no release download fallback'):
                self.run_setup(services,root,None,lock,sha,rehearsal=None)
            with self.assertRaisesRegex(ValueError,'rehearsal identity differs'):
                self.run_setup(services,root,bundle,lock,sha,rehearsal='different')

    def test_symlink_preview_inputs_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();services,bundle,lock,sha=self.prepare(root)
            alias=root/'alias';alias.symlink_to(bundle,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'linked'):self.run_setup(services,root,alias,lock,sha)
            self.assertFalse(any(call[0]=='gh' for call in services.calls))

    def test_anw_demo_008_published_setup_rejects_preview_and_keeps_its_resume_route(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();services,bundle,lock,sha=self.prepare(root)
            with contextlib.redirect_stdout(io.StringIO()):
                result=setup.setup(setup.choose('agent-native-workforce'),root/'projects','my-workbench',
                    root/'state',services,True,services.distribution,sha)
            project=Path(result['workspace']);record=project/'.aibl/distribution.json'
            original=record.read_bytes();statefile=root/'state/my-workbench.json'
            before=json.loads(statefile.read_bytes());calls=len(services.calls)
            work=project/'student-note.txt';work.write_text('Preserve this existing student work.')
            with self.assertRaisesRegex(ValueError,'fresh project name'):
                self.run_setup(services,root,bundle,lock,sha,rehearsal=None)
            after=json.loads(statefile.read_bytes())
            self.assertEqual({k:v for k,v in before.items() if k!='attempts'},
                             {k:v for k,v in after.items() if k!='attempts'})
            self.assertEqual(after['attempts'][-1]['result'],'blocked')
            self.assertEqual(record.read_bytes(),original)
            self.assertEqual(len(services.calls),calls)
            self.assertFalse((project/'.aibl-local/candidate-distribution.json').exists())
            with self.assertRaisesRegex(ValueError,'not the matching local candidate'):
                pinned.record_candidate_transport(project,bundle,lock,services.distribution,sha)
            self.assertFalse((project/'.aibl-local/candidate-distribution.json').exists())
            with contextlib.redirect_stdout(io.StringIO()):
                resumed=setup.setup(setup.choose('agent-native-workforce'),root/'projects','my-workbench',
                    root/'state',services,True,services.distribution,sha)
            self.assertEqual(resumed['status'],'ready');self.assertNotIn('delivery_mode',resumed)
            self.assertEqual(record.read_bytes(),original)
            self.assertEqual(work.read_text(),'Preserve this existing student work.')
            self.assertEqual(sum(call[:3]==['gh','repo','create'] for call in services.calls),1)


if __name__=='__main__':unittest.main()
