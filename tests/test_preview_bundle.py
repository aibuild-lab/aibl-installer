"""Candidate source stays local; private Git setup uses the existing test service."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
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

    def run_setup(self,services,root,bundle,lock,sha,rehearsal='ui-first',desktop=False,no_launch=True):
        with contextlib.redirect_stdout(io.StringIO()):
            return setup.setup(setup.choose('agent-native-workforce'),root/'projects','my-workbench',
                root/'state',services,no_launch,services.distribution,sha,str(bundle) if bundle is not None else None,str(lock),rehearsal,desktop)

    def test_desktop_handoff_never_calls_cli_and_preserves_unobserved_boundary_on_retry(self):
        for rehearsal,no_launch in [('ui-first',False),(None,True)]:
            with self.subTest(rehearsal=rehearsal),tempfile.TemporaryDirectory() as directory:
                root=Path(directory).resolve();services,bundle,lock,sha=self.prepare(root)
                def no_cli(args,**kwargs):
                    self.assertNotEqual(args[0],'claude','Desktop handoff must not inspect, authenticate or launch Claude CLI')
                    state=json.loads((root/'state/my-workbench.json').read_bytes())
                    self.assertEqual(state['client'],'claude_desktop','Client must be frozen before tool or account calls')
                    return services(args,**kwargs)
                no_cli.distribution=services.distribution
                result=self.run_setup(no_cli,root,bundle,lock,sha,rehearsal,True,no_launch)
                project=Path(result['workspace']);head=services.git('rev-parse','HEAD',cwd=project)
                self.assertEqual(result['status'],'files_ready_for_desktop');self.assertEqual(result['client'],'claude_desktop')
                self.assertEqual(result['next'],'/aibl-teach');self.assertEqual(set(result['versions']),{'git','gh','python'})
                self.assertEqual(result['student_observed_commit'],head)
                self.assertEqual(result['student_observed_tree'],services.git('rev-parse','HEAD^{tree}',cwd=project))
                self.assertEqual(head,services.git('rev-parse','refs/heads/main',cwd=services.server))
                statefile=root/'state/my-workbench.json';attempt=json.loads(statefile.read_bytes())['attempts'][-1]
                self.assertEqual(attempt['result'],'files_ready_for_desktop');self.assertEqual(attempt['last_proven_stage'],'student_context')
                self.assertEqual(result['last_proven_stage'],'student_context');self.assertEqual(result['stages'],attempt['stages'])
                self.assertEqual(attempt['client'],'claude_desktop');self.assertIsNone(attempt['failed_stage'])
                for field in ('desktop_authentication','desktop_session','native_runtime'):
                    self.assertEqual(result[field],'NOT_OBSERVED');self.assertEqual(attempt[field],'NOT_OBSERVED')
                for stage in ('candidate_inputs','tools','github_auth','private_repository','clone','git_identity','student_context'):
                    self.assertEqual(attempt['stages'][stage],'PASS')
                for stage in ('course_access','claude_auth','claude_launch'):self.assertEqual(attempt['stages'][stage],'NOT_RUN')
                if rehearsal:
                    self.assertEqual(result['actor'],'automated_test');self.assertFalse(result['course_credit'])
                    self.assertFalse(attempt['course_credit']);self.assertEqual(attempt['rehearsal_id'],rehearsal)
                    self.assertIn('--rehearsal '+rehearsal+' --actor automated_test',result['handoff_prompt'])
                    self.assertIn('never human answers, approval, assessment or credit',result['handoff_prompt'])
                    self.assertIn('course_credit=false',result['handoff_prompt'])
                else:
                    self.assertNotIn('actor',result);self.assertNotIn('course_credit',result)
                    self.assertIn('my actual choices and explanations',result['handoff_prompt'])
                note=project/'student-note.txt';note.write_text('Preserve this existing work.')
                resumed=self.run_setup(no_cli,root,bundle,lock,sha,rehearsal,True,no_launch)
                self.assertEqual(resumed['status'],'files_ready_for_desktop')
                self.assertEqual(resumed['student_observed_commit'],head);self.assertEqual(note.read_text(),'Preserve this existing work.')
                self.assertEqual(sum(call[:3]==['gh','repo','create'] for call in services.calls),1)
                self.assertFalse(any(call[:2]==['gh','auth'] or '--global' in call for call in services.calls))

    def test_desktop_requires_preview_before_effects(self):
        for course,bundle in [('agent-native-workforce',None)]:
            with self.subTest(course=course),tempfile.TemporaryDirectory() as directory:
                root=Path(directory).resolve();services,bundle_root,lock,sha=self.prepare(root)
                with self.assertRaisesRegex(setup.SetupError,'explicit local candidate preview'):
                    setup.setup(setup.choose(course),root/'projects','my-workbench',root/'state',services,
                        distribution=services.distribution,distribution_sha256=sha,
                        preview_bundle=str(bundle_root) if bundle else None,distribution_lock=str(lock),desktop=True)
                self.assertFalse(services.calls);self.assertFalse((root/'state').exists())
                self.assertFalse((root/'projects').exists())
        for argv in [['course_setup.py','--desktop'],['course_setup.py','--desktop','--course','agent-native-workforce']]:
            with self.subTest(argv=argv),patch.object(setup.sys,'argv',argv),patch.object(setup,'command',side_effect=AssertionError('No command may run')),patch.object(setup,'setup',side_effect=AssertionError('No setup may run')),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(setup.main(),1)

    def test_desktop_failures_never_report_files_ready_or_observed_runtime(self):
        cases=[('github_auth','authentication',['gh','api','user']),('github_auth','network',['gh','api','user']),
               ('clone','network',['git','push','--set-upstream']),('student_context','operation',[setup.sys.executable,'scripts/aibl.py','setup'])]
        for stage,reason,trigger in cases:
            with self.subTest(stage=stage,reason=reason),tempfile.TemporaryDirectory() as directory:
                root=Path(directory).resolve();services,bundle,lock,sha=self.prepare(root)
                def fail(args,**kwargs):
                    self.assertNotEqual(args[0],'claude')
                    if args[:len(trigger)]==trigger:
                        services.calls.append(args);raise setup.SetupError('Synthetic required gate failure',reason)
                    return services(args,**kwargs)
                fail.distribution=services.distribution
                with self.assertRaisesRegex(setup.SetupError,'Synthetic required gate failure'):
                    self.run_setup(fail,root,bundle,lock,sha,desktop=True)
                attempt=json.loads((root/'state/my-workbench.json').read_bytes())['attempts'][-1]
                self.assertEqual(attempt['result'],'blocked');self.assertEqual(attempt['failed_stage'],stage)
                self.assertEqual(attempt['failure_domain'],reason);self.assertEqual(attempt['stages'][stage],'FAIL')
                self.assertNotEqual(attempt['last_proven_stage'],'student_context')
                for field in ('desktop_authentication','desktop_session','native_runtime'):self.assertEqual(attempt[field],'NOT_OBSERVED')
                for skipped in ('claude_auth','claude_launch'):self.assertEqual(attempt['stages'][skipped],'NOT_RUN')
                self.assertFalse(any(call[:2]==['gh','auth'] for call in services.calls))
                if stage=='github_auth':self.assertFalse(any(call[:3]==['gh','repo','create'] for call in services.calls))

    def test_client_changes_preserve_existing_project_and_legacy_cli_route(self):
        for initial_desktop,legacy_state in [(False,False),(False,True),(True,False)]:
            with self.subTest(initial_desktop=initial_desktop,legacy_state=legacy_state),tempfile.TemporaryDirectory() as directory:
                root=Path(directory).resolve();services,bundle,lock,sha=self.prepare(root)
                first=self.run_setup(services,root,bundle,lock,sha,desktop=initial_desktop)
                project=Path(first['workspace']);statefile=root/'state/my-workbench.json'
                before=json.loads(statefile.read_bytes())
                if legacy_state:before.pop('client');statefile.write_text(json.dumps(before))
                original=(project/'.aibl/distribution.json').read_bytes();calls=len(services.calls)
                note=project/'student-note.txt';note.write_text('Keep my work and chosen client.')
                with self.assertRaisesRegex(setup.SetupError,'fresh project name to change clients'):
                    self.run_setup(services,root,bundle,lock,sha,desktop=not initial_desktop)
                after=json.loads(statefile.read_bytes())
                self.assertEqual({k:v for k,v in before.items() if k!='attempts'},{k:v for k,v in after.items() if k!='attempts'})
                self.assertEqual(after['attempts'][-1]['result'],'blocked');self.assertIsNone(after['attempts'][-1]['last_proven_stage'])
                self.assertEqual(len(services.calls),calls);self.assertEqual((project/'.aibl/distribution.json').read_bytes(),original)
                resumed=self.run_setup(services,root,bundle,lock,sha,desktop=initial_desktop)
                self.assertEqual(resumed['status'],first['status']);self.assertEqual(note.read_text(),'Keep my work and chosen client.')
                self.assertEqual(sum(call[:3]==['gh','repo','create'] for call in services.calls),1)

    def test_desktop_client_is_frozen_even_if_first_account_gate_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();services,bundle,lock,sha=self.prepare(root)
            def missing(args,**kwargs):
                if args==['gh','api','user']:
                    services.calls.append(args);raise setup.SetupError('Authentication required','authentication_missing')
                return services(args,**kwargs)
            missing.distribution=services.distribution
            with self.assertRaisesRegex(setup.SetupError,'no account enrollment or login'):
                self.run_setup(missing,root,bundle,lock,sha,desktop=True)
            state=json.loads((root/'state/my-workbench.json').read_bytes());calls=len(services.calls)
            self.assertEqual(state['client'],'claude_desktop');self.assertNotIn('repository',state)
            self.assertFalse(any(call[:2]==['gh','auth'] or call[0]=='claude' or call[:3]==['gh','repo','create'] for call in services.calls))
            with self.assertRaisesRegex(setup.SetupError,'fresh project name to change clients'):
                self.run_setup(services,root,bundle,lock,sha)
            self.assertEqual(len(services.calls),calls)

    def test_default_cli_and_no_launch_still_require_claude_authentication(self):
        for no_launch in (False,True):
            with self.subTest(no_launch=no_launch),tempfile.TemporaryDirectory() as directory:
                root=Path(directory).resolve();services,bundle,lock,sha=self.prepare(root)
                def unavailable(args,**kwargs):
                    if args[:3]==['claude','auth','status']:
                        services.calls.append(args);raise setup.SetupError('Synthetic CLI policy rejection')
                    return services(args,**kwargs)
                unavailable.distribution=services.distribution
                with self.assertRaisesRegex(setup.SetupError,'existing supported Claude Code access'):
                    self.run_setup(unavailable,root,bundle,lock,sha,no_launch=no_launch)
                state=json.loads((root/'state/my-workbench.json').read_bytes());attempt=state['attempts'][-1]
                self.assertEqual(state['client'],'claude_code');self.assertEqual(attempt['result'],'blocked')
                self.assertEqual(attempt['failed_stage'],'claude_auth');self.assertEqual(attempt['last_proven_stage'],'student_context')
                self.assertEqual(attempt['stages']['claude_auth'],'FAIL');self.assertEqual(attempt['stages']['claude_launch'],'NOT_RUN')
                self.assertIn(['claude','--version'],services.calls);self.assertIn(['claude','auth','status','--json'],services.calls)
                self.assertNotIn('desktop_session',attempt)

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
        for desktop,kind in [(desktop,kind) for desktop in (False,True) for kind in ('missing','changed','wrong-digest')]:
            with self.subTest(kind=kind,desktop=desktop),tempfile.TemporaryDirectory() as directory:
                root=Path(directory).resolve();services,bundle,lock,sha=self.prepare(root)
                path=bundle/'agent-native-workforce/payload.zip'
                if kind=='missing':path.unlink()
                elif kind=='changed':path.write_bytes(b'corrupt')
                else:sha='0'*64
                with self.assertRaises(ValueError):self.run_setup(services,root,bundle,lock,sha,desktop=desktop)
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
