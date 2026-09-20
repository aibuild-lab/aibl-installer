"""Actual public template snapshots and real Git/packages; provider/engine identity simulated."""
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile

import test_frozen_family as frozen_fixtures
import test_standalone_enrollment as git_fixtures
import frozen_family as frozen
import enrollment_bridge as bridge
import enrollment_v2 as enrollment
import workbench_distribution as distribution
import workbench_packages as packages
import enroll

FIXTURES = Path(__file__).parent / 'fixtures/workbench-templates'


class EnrollmentBridge(unittest.TestCase):
    save = frozen_fixtures.FrozenFamily.save
    runner = frozen_fixtures.FrozenFamily.runner

    def setUp(self):
        frozen_fixtures.FrozenFamily.setUp(self)
        self.home = self.root
        retained = self.home / '.aibl/installers' / self.revision
        retained.parent.mkdir(parents=True)
        self.engine.rename(retained)
        self.engine = retained
        for name in ['scripts/enrollment_bridge.py', 'scripts/enrollment_templates.json']:
            (self.engine/name).write_bytes(b'synthetic admitted bridge')
            self.distribution['installer']['files'][name] = packages.digest((self.engine/name).read_bytes())
        self.workbench = self.home / 'my-workbench'
        self.plans = self.home / 'plans'
        self.services = git_fixtures.Services(self.home)
        self.services.git('init', '--bare', str(self.services.server))
        self.sources = json.loads(Path(bridge.__file__).with_name('enrollment_templates.json').read_text())['snapshots']
        self.seed(self.sources[0]['revision'])
        contract = {'schema_version': 'aibl.program-connection/v1', 'product': 'agent-workforce',
                    'requires': ['agent-workbench', 'workbench-core'],
                    'first_action': {'path': 'course/workforce/START-HERE.md', 'prompt': 'Use aibl-workforce.'},
                    'native': {client: [prefix + '/skills/aibl-workforce/SKILL.md']
                               for client, prefix in [('claude', '.claude'), ('codex', '.agents')]}}
        files = {'course/workforce/connection.json': json.dumps(contract).encode(),
                 'course/workforce/START-HERE.md': b'Synthetic course first action'}
        files.update({paths[0]: b'Synthetic entry skill' for paths in contract['native'].values()})
        self.replace_package('agent-workforce', files)
        self.save()
        original_load, original_acquire = frozen.load_distribution, frozen.acquire
        def load(*args, **kwargs):
            kwargs['runner'] = kwargs.get('runner') or self.runner
            return original_load(*args, **kwargs)
        def acquire(*args, **kwargs):
            kwargs.update(github=self.github, now=frozen_fixtures.NOW, runner=self.runner)
            return original_acquire(*args, **kwargs)
        real_lock = packages.load_lock
        for target, name, replacement in [
            (Path, 'home', lambda: self.home), (bridge, 'ROOT', self.engine),
            (enrollment, 'ROOT', self.engine), (frozen, 'load_distribution', load),
            (distribution, 'load_distribution', load), (frozen, 'acquire', acquire),
            (distribution, 'acquire', acquire),
            (enrollment, 'load_lock', lambda p, h, engine: real_lock(p, h))]:
            active = patch.object(target, name, replacement)
            active.start(); self.addCleanup(active.stop)

    def replace_package(self, product, contents, manifest=None):
        pin = self.family['packages'][product]
        locator = {'repository': pin['publisher'], 'release_tag': pin['release_tag'], 'release_target': pin['release_target']}
        if manifest is None:
            manifest = {'schema_version': 'aibl.family-package/v2', 'product': product, 'version': pin['version'],
                        'source_repository': 'aibuild-lab/agent-native-workforce-internal', 'source_revision': 'c'*40,
                        'components': [], 'files': [{'path': n, 'sha256': packages.digest(raw), 'mode': 420, 'policy': 'supplied'} for n, raw in contents.items()]}
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as z:
            for name, raw in contents.items(): z.writestr(name, raw)
        mb, ab = packages.encoded(manifest), stream.getvalue()
        pin.update(manifest_sha256=packages.digest(mb), archive_sha256=packages.digest(ab))
        self.github.put(locator, 'manifest.json', mb); self.github.put(locator, 'payload.zip', ab)

    def seed(self, revision):
        self.workbench.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(FIXTURES / (revision + '.zip')) as archive:
            archive.extractall(self.workbench)
        git = self.services.git
        git('init', '-b', 'main', cwd=self.workbench)
        git('config', 'user.name', 'Synthetic Student', cwd=self.workbench)
        git('config', 'user.email', 'student@example.invalid', cwd=self.workbench)
        git('remote', 'add', 'origin', 'https://github.com/student/my-workbench.git', cwd=self.workbench)
        git('add', '.', cwd=self.workbench); git('commit', '-m', 'Essentials', cwd=self.workbench)

    def preview(self, client='codex'):
        inputs, extra = bridge.prepare(self.workbench, self.path, self.sha, client, state_root=self.plans)
        return enrollment.preview(self.workbench, 'agent-workforce', inputs['family_lock'], inputs['family_sha256'], inputs['family_bundles'],
                                  bridge=extra, runner=self.services, state_root=self.plans)

    def apply(self, plan):
        return enrollment.apply_plan(self.workbench, plan['plan_id'], runner=self.services, state_root=self.plans)

    def test_both_templates_clients_preserve_student_and_index(self):
        for source, client in zip(self.sources, ['claude', 'codex']):
            with self.subTest(revision=source['revision'], client=client):
                self.workbench = self.home / source['revision']; self.seed(source['revision'])
                (self.workbench/'context/project.md').write_text('My actual context')
                (self.workbench/'work/saved.txt').write_text('My saved work')
                self.services.git('add', 'work/saved.txt', cwd=self.workbench)
                before = enrollment.git_state(self.workbench, self.services)
                root_instructions = (self.workbench/'AGENTS.md').read_bytes()
                plan = self.preview(client)
                self.assertEqual(enrollment.git_state(self.workbench, self.services), before)
                self.assertFalse((self.workbench/'.aibl/family.json').exists())
                self.assertEqual(self.apply(plan)['native_verification'], 'pending')
                after = enrollment.git_state(self.workbench, self.services)
                self.assertEqual(after['index'], before['index']); self.assertEqual(after['head'], before['head'])
                self.assertEqual((self.workbench/'context/project.md').read_text(), 'My actual context')
                self.assertEqual((self.workbench/'work/saved.txt').read_text(), 'My saved work')
                self.assertEqual((self.workbench/'AGENTS.md').read_bytes(), root_instructions)
                self.assertEqual(self.apply(plan)['status'], 'installed')
                self.assertFalse(any(call[:2] == ['git', 'push'] for call in self.services.calls))

    def test_check_and_unapplied_preview_write_no_workbench_files(self):
        before = enrollment.git_state(self.workbench, self.services)
        result = bridge.available(self.workbench, self.services)
        self.assertFalse(result['programs'][0]['supported'])
        self.assertNotIn('aibl-adopt-workforce', json.dumps(result))
        self.preview()
        self.assertEqual(enrollment.git_state(self.workbench, self.services), before)
        self.assertFalse(distribution.directory(self.workbench).exists())

    def test_changed_skill_unknown_template_and_mode_hold(self):
        path = self.workbench/'.agents/skills/aibl-enroll/SKILL.md'
        old = path.read_bytes(); path.write_text('Student customization')
        with self.assertRaisesRegex(ValueError, 'edited supplied'): self.preview()
        path.write_bytes(old)
        if os.name != 'nt':
            path.chmod(0o755)
            with self.assertRaises(ValueError): self.preview()
            path.chmod(0o644)
        (self.workbench/'.aibl/template.json').write_text('{}')
        with self.assertRaises(ValueError): self.preview()
        self.assertFalse((self.workbench/'.aibl/family.json').exists())

    def test_account_origin_and_changed_plan_hold(self):
        plan = self.preview(); self.services.username = 'other'
        with self.assertRaises(ValueError): self.apply(plan)
        self.services.username = 'student'
        self.services.git('remote', 'set-url', 'origin', 'https://example.invalid/foreign', cwd=self.workbench)
        with self.assertRaises(ValueError): self.apply(plan)
        self.services.git('remote', 'set-url', 'origin', 'https://github.com/student/my-workbench.git', cwd=self.workbench)
        (self.workbench/'work/later.txt').write_text('Changed after preview')
        with self.assertRaisesRegex(ValueError, 'changed since preview'): self.apply(plan)

    def test_missing_admission_bad_digest_and_tampered_bundle(self):
        with self.assertRaises(ValueError): bridge.prepare(self.workbench, self.path, '0'*64, 'codex')
        with self.assertRaises(ValueError): bridge.prepare(self.workbench, self.path, self.sha, None)
        with self.assertRaises(ValueError): distribution.retain(self.workbench, 'student/my-workbench', self.engine, self.path, self.sha)
        plan = self.preview(); saved = json.loads((self.plans/(plan['plan_id']+'.json')).read_text())
        (Path(saved['family_bundles'])/'workbench-core/payload.zip').write_bytes(b'tampered')
        with self.assertRaises(ValueError): self.apply(plan)

    def test_interruption_recovery_and_lost_response(self):
        plan = self.preview(); original = enrollment.compose
        def interrupted(*args, **kwargs):
            if not kwargs.get('preview'): kwargs['fail_after'] = 1
            return original(*args, **kwargs)
        with patch.object(enrollment, 'compose', interrupted):
            with self.assertRaisesRegex(ValueError, 'interruption'): self.apply(plan)
        with self.assertRaisesRegex(ValueError, 'interrupted'): self.apply(plan)
        before_index = (self.workbench/'.git/index').read_bytes()
        packages.recover(self.workbench)
        enrollment.git_state(self.workbench, self.services)
        self.assertEqual((self.workbench/'.git/index').read_bytes(), before_index)
        def lost(*args, **kwargs):
            result = original(*args, **kwargs)
            if not kwargs.get('preview'): raise OSError('lost apply response')
            return result
        with patch.object(enrollment, 'compose', lost):
            with self.assertRaises(OSError): self.apply(plan)
        self.assertEqual(self.apply(plan)['status'], 'installed')

    def test_unknown_collision_and_missing_client_entry_hold(self):
        (self.workbench/'course/workforce').mkdir(parents=True)
        (self.workbench/'course/workforce/START-HERE.md').write_text('My own course')
        result = self.preview(); self.assertEqual(result['status'], 'needs_review')
        self.assertNotIn('plan_id', result)
        (self.workbench/'course/workforce/START-HERE.md').unlink()
        locator = self.family['packages']['agent-workforce']
        key = (locator['publisher'], locator['release_tag'], 'payload.zip')
        with zipfile.ZipFile(io.BytesIO(self.github.values[key])) as archive:
            payload = {n: archive.read(n) for n in archive.namelist()}
        contract = json.loads(payload['course/workforce/connection.json'])
        contract['native']['codex'] = ['course/workforce/START-HERE.md']
        payload['course/workforce/connection.json'] = json.dumps(contract).encode()
        self.replace_package('agent-workforce', payload); self.save()
        with self.assertRaisesRegex(ValueError, 'selected client entry'): self.preview()

    def test_recheck_withdrawal_before_writes(self):
        plan = self.preview()
        self.indexes['agent-workforce']['withdrawn'] = True
        row = self.distribution['trust']['agent-workforce']['descriptor']
        self.github.put(row['index_release'], row['index_asset'], packages.encoded(self.indexes['agent-workforce']))
        with self.assertRaises(ValueError): self.apply(plan)
        self.assertFalse((self.workbench/'.aibl/family.json').exists())

    def test_cli_check_uses_new_access_route(self):
        with patch.object(enroll, 'command', self.services), patch.object(enroll, 'verify_engine', return_value={}), patch('sys.argv', ['enroll.py', '--workbench', str(self.workbench), '--check', '--json']):
            self.assertEqual(enroll.main(), 0)

    @unittest.skipUnless(os.environ.get('AIBL_BRIDGE_CANDIDATE_BUNDLES'), 'Private source builder candidates are a separate local integration gate')
    def test_actual_private_builder_candidates(self):
        folder = Path(os.environ['AIBL_BRIDGE_CANDIDATE_BUNDLES'])
        for product in bridge.PRODUCTS:
            manifest = json.loads((folder/product/'manifest.json').read_text())
            self.family['packages'][product]['version'] = manifest['version']
            self.family['packages'][product]['release_tag'] = packages.release_tag(product, manifest['version'])
            with zipfile.ZipFile(folder/product/'payload.zip') as archive:
                payload = {n: archive.read(n) for n in archive.namelist()}
            self.replace_package(product, payload, manifest)
        self.save()
        plan = self.preview()
        result = self.apply(plan)
        self.assertIn('.agents/skills/aibl-workforce/SKILL.md', result['native_paths']['codex'])
        self.assertTrue((self.workbench/'course/workforce/prompts/anw-m1-01.txt').is_file())
        # Run the actual installed wrapper's read-only argument parser; never invoke a worker.
        import subprocess, sys
        outcome = subprocess.run([sys.executable, '-B', str(self.workbench/'.agents/skills/aibl-enroll/enroll.py'), '--help'], capture_output=True, text=True)
        self.assertEqual(outcome.returncode, 0, outcome.stderr)
        self.assertIn('--apply-plan', outcome.stdout)


if __name__ == '__main__': unittest.main()
