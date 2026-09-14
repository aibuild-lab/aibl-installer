"""Real Git/package tests; GitHub and app authentication are simulated, not native proof."""
import copy
import hashlib
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import course_setup as setup
import standalone_setup as standalone
import enrollment_v2 as enrollment
import enroll
import workbench_packages as packages
import test_workbench_packages as fixtures
from test_family_v2 import FamilyV2


class Services:
    def __init__(self, root):
        self.server = root / 'remote.git'
        self.calls = []
        self.lose_creation = False
        self.lose_push = False
        self.access = True
        self.username = 'student'
        self.env = {**os.environ, 'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_TERMINAL_PROMPT': '0'}

    def git(self, *args, cwd=None):
        result = subprocess.run(['git', *args], cwd=cwd, env=self.env, text=True, capture_output=True)
        if result.returncode:
            raise setup.SetupError('Synthetic Git failure: ' + result.stderr)
        return result.stdout.strip()

    def __call__(self, args, cwd=None, interactive=False):
        self.calls.append(args)
        if args[:2] == ['git', 'ls-remote']:
            return self.git('ls-remote', str(self.server), *args[3:])
        if args[:2] == ['git', 'push']:
            value = self.git('push', str(self.server), 'HEAD:refs/heads/main', cwd=cwd)
            if self.lose_push:
                self.lose_push = False
                raise setup.SetupError('Lost push response', 'network')
            return value
        if args[0] == 'git':
            return self.git(*args[1:], cwd=cwd)
        if args == ['gh', 'api', 'user']:
            return json.dumps({'login': self.username, 'name': 'Synthetic Student', 'id': 321})
        if args[:2] == ['gh', 'api']:
            if args[2].startswith('repos/aibuild-lab/'):
                if 'agent-workforce' in args[2] and not self.access:
                    raise setup.SetupError('HTTP 404', 'not_found')
                if 'the-lab' in args[2]:
                    raise setup.SetupError('HTTP 404', 'not_found')
                return '{}'
            if not self.server.exists():
                raise setup.SetupError('HTTP 404', 'not_found')
            return json.dumps({'private': True, 'full_name': 'student/my-workbench', 'owner': {'login': 'student'}, 'id': 456})
        if args[:3] == ['gh', 'repo', 'create']:
            self.git('init', '--bare', str(self.server))
            if self.lose_creation:
                self.lose_creation = False
                raise setup.SetupError('Lost creation response', 'network')
            return ''
        if args == ['gh', 'auth', 'status']:
            return ''
        if args == ['gh', '--version']:
            return 'gh version 2.70.0'
        if args == [sys.executable, '--version']:
            return 'Python 3.13.0'
        if args == ['node', '--version']:
            return 'v22.0.0'
        if args == ['codex', '--version']:
            return 'codex-cli 0.147.0'
        if args == ['codex', 'login', 'status']:
            return 'Logged in using ChatGPT'
        raise AssertionError(args)


class StandaloneEnrollment(unittest.TestCase):
    package = fixtures.FamilyTests.package
    v2 = FamilyV2.v2

    def setUp(self):
        fixtures.FamilyTests.setUp(self)
        self.base = Path(self.tmp.name)
        self.v2()
        self.package('agent-workbench', {'AGENTS.md': 'Generic guidance', '.gitignore': '.aibl-local/\n', 'context/project.md': 'Your context', 'blueprints/.gitkeep': ''}, seed=True)
        connection = {'schema_version': 'aibl.program-connection/v1', 'product': 'agent-workforce',
                      'requires': ['agent-workbench', 'workbench-core'],
                      'first_action': {'path': 'course/workforce/START-HERE.md', 'prompt': 'Open your Workforce guide.'},
                      'native': {'claude': ['workforce/guide.md'], 'codex': ['workforce/guide.md']}}
        self.package('agent-workforce', {'course/workforce/connection.json': json.dumps(connection), 'course/workforce/START-HERE.md': 'Begin here', 'workforce/guide.md': 'Native guide'})
        self.package('agent-essentials', {'course/essentials/START-HERE.md': 'Lesson 8', 'blueprints/youtube-transcripts.md': 'The transcript blueprint'})
        for product, pin in self.family['packages'].items():
            pin.update(publisher=packages.V2_PUBLISHERS[product], release_tag=packages.release_tag(product, pin['version']), release_target='b' * 40)
        self.lockfile = self.base / 'family.json'
        self.lockfile.write_bytes(packages.encoded(self.family))
        self.lockhash = packages.digest(self.lockfile.read_bytes())
        self.services = Services(self.base)
        self.plans = self.base / 'plans'
        self.real_load = packages.load_lock
        # Tests do real hash/schema verification; exact clean retained-engine admission is a separate existing gate.
        self.load_patch = mock.patch.object(enrollment, 'load_lock', side_effect=lambda p, h, engine: self.real_load(p, h))
        self.load_patch.start()
        self.addCleanup(self.load_patch.stop)

    def init(self):
        result = setup.setup({'id': 'my-workbench'}, self.base / 'projects', 'my-workbench', state_root=self.base / 'state', runner=self.services, no_launch=True, harness='codex', family=self.family, family_bundles=self.bundles)
        self.root = Path(result['workspace'])
        return result

    def preview(self, product='agent-workforce'):
        return enrollment.preview(self.root, product, self.lockfile, self.lockhash, self.bundles, runner=self.services, state_root=self.plans)

    def apply(self, plan):
        return enrollment.apply_plan(self.root, plan['plan_id'], runner=self.services, state_root=self.plans)

    def tree(self):
        return {p.relative_to(self.root).as_posix(): (p.read_bytes(), p.stat().st_mode) for p in self.root.rglob('*') if p.is_file()}

    def test_fresh_public_base_then_zero_write_rerun(self):
        self.services.access = False
        result = self.init()
        self.assertEqual(result['status'], 'files_ready')
        self.assertEqual(result['native_verification'], 'pending')
        self.assertEqual(set(packages.read(self.root / packages.MARKER)['packages']), {'agent-workbench', 'workbench-core'})
        self.assertFalse(any('agent-workforce' in x for call in self.services.calls for x in call))
        (self.root / 'context/project.md').write_text('My own context')
        (self.root / 'work.txt').write_text('Untracked student work')
        (self.root / 'blueprints/.gitkeep').unlink()
        before = self.tree()
        self.assertEqual(self.init()['status'], 'already_initialized')
        self.assertEqual(self.tree(), before)
        self.assertEqual(self.services.git('rev-list', '--count', 'HEAD', cwd=self.root), '1')

    def test_codex_auth_status_uses_its_success_stderr(self):
        response = subprocess.CompletedProcess(['codex', 'login', 'status'], 0, '', 'Logged in using ChatGPT\n')
        with mock.patch.object(setup.subprocess, 'run', return_value=response):
            self.assertEqual(setup.command(['codex', 'login', 'status']), 'Logged in using ChatGPT')
            self.assertEqual(setup.command(['git', 'status']), '')

    def test_uncertain_creation_and_push_reconcile(self):
        self.services.lose_creation = True
        with self.assertRaisesRegex(setup.SetupError, 'Lost creation'):
            self.init()
        self.services.lose_push = True
        with self.assertRaisesRegex(setup.SetupError, 'Lost push'):
            self.init()
        self.assertEqual(self.init()['status'], 'files_ready')
        self.assertEqual(sum(c[:3] == ['gh', 'repo', 'create'] for c in self.services.calls), 1)
        self.assertEqual(sum(c[:2] == ['git', 'push'] for c in self.services.calls), 1)

    def test_name_collision_and_wrong_owner_preserve_files(self):
        self.init()
        before = self.tree()
        self.services.username = 'someone-else'
        with self.assertRaises(setup.SetupError):
            self.init()
        self.assertEqual(self.tree(), before)
        self.services.username = 'student'
        saved = self.base / 'preserved-workbench'
        self.root.rename(saved)
        (self.base / 'state/my-workbench-standalone.json').rename(self.base / 'preserved-state.json')
        with self.assertRaisesRegex(setup.SetupError, 'already contains work'):
            self.init()
        self.assertTrue((saved / 'AGENTS.md').exists())

    def test_selection_yes_does_not_install(self):
        self.init()
        with mock.patch.object(enroll, 'verify_engine', return_value={'mode': 'family', 'refreshed': False}):
            result = enroll.enroll(self.root, yes=True, only=['agent-workforce'], runner=self.services)
        self.assertEqual(result['status'], 'selected')
        self.assertFalse((self.root / 'course/workforce/START-HERE.md').exists())
        self.assertEqual(set(packages.read(self.root / packages.MARKER)['packages']), {'agent-workbench', 'workbench-core'})

    def test_seed_never_commits_separately_staged_local_state(self):
        original = self.services
        def stop_at_commit(args, **kwargs):
            if args[:2] == ['git', 'commit']:
                raise setup.SetupError('Stopped before commit')
            return original(args, **kwargs)
        with self.assertRaisesRegex(setup.SetupError, 'Stopped before commit'):
            setup.setup({'id': 'my-workbench'}, self.base / 'projects', 'my-workbench', state_root=self.base / 'state', runner=stop_at_commit, no_launch=True, harness='codex', family=self.family, family_bundles=self.bundles)
        stage = self.base / 'projects/.my-workbench-seed-in-progress'
        self.services.git('add', '-f', '.aibl-local/family-history.json', cwd=stage)
        with self.assertRaisesRegex(setup.SetupError, 'index includes unexpected'):
            self.init()
        self.assertTrue((stage / '.aibl-local/family-history.json').exists())

    def test_interrupted_seed_recovers(self):
        real = packages.compose
        with mock.patch.object(standalone, 'compose', side_effect=lambda *a, **kw: real(*a, **kw, fail_after=2)):
            with self.assertRaisesRegex(ValueError, 'interruption'):
                self.init()
        self.assertEqual(self.init()['status'], 'files_ready')

    def test_interrupted_seed_preserves_new_work(self):
        real = packages.compose
        with mock.patch.object(standalone, 'compose', side_effect=lambda *a, **kw: real(*a, **kw, fail_after=2)):
            with self.assertRaises(ValueError):
                self.init()
        stage = self.base / 'projects/.my-workbench-seed-in-progress'
        (stage / 'AGENTS.md').write_text('Student changed this')
        with self.assertRaisesRegex(ValueError, 'Work changed'):
            self.init()
        self.assertEqual((stage / 'AGENTS.md').read_text(), 'Student changed this')

    def test_accessible_only_check_writes_nothing(self):
        self.init()
        self.services.access = False
        before = self.tree()
        result = enrollment.available(self.root, self.services)
        self.assertEqual(result['programs'], [])
        self.assertIn('student', result['help'])
        self.assertNotIn('agent-workforce', json.dumps(result))
        self.assertEqual(before, self.tree())

    def test_preview_confirm_install_and_repeat(self):
        self.init()
        (self.root / 'context/project.md').write_text('Personal context')
        (self.root / 'work.txt').write_text('Keep unfinished work')
        before = self.tree()
        plan = self.preview()
        self.assertEqual(self.tree(), before)
        self.assertEqual(plan['status'], 'previewed')
        result = self.apply(plan)
        self.assertEqual(result['status'], 'installed')
        self.assertEqual(result['native_verification'], 'pending')
        self.assertTrue(result['rollback'])
        self.assertEqual((self.root / 'work.txt').read_text(), 'Keep unfinished work')
        after = self.tree()
        self.assertEqual(self.apply(plan), result)
        self.assertEqual(self.tree(), after)
        self.assertEqual(self.preview()['status'], 'already_connected')

    def test_changed_work_or_identity_after_preview_refuses(self):
        self.init()
        (self.root / 'work.txt').write_text('First')
        plan = self.preview()
        (self.root / 'work.txt').write_text('Second')
        with self.assertRaisesRegex(setup.SetupError, 'changed since preview'):
            self.apply(plan)
        self.assertFalse((self.root / 'course/workforce/START-HERE.md').exists())
        self.services.username = 'someone-else'
        with self.assertRaises(setup.SetupError):
            self.apply(plan)

    def test_lost_apply_response_recovers_same_backup(self):
        self.init()
        plan = self.preview()
        with mock.patch.object(enrollment, 'finish', side_effect=RuntimeError('Lost process')):
            with self.assertRaisesRegex(RuntimeError, 'Lost process'):
                self.apply(plan)
        result = self.apply(plan)
        self.assertTrue((self.root / '.aibl-local/family-backups' / result['rollback'] / 'transaction.json').exists())
        self.assertEqual(result['native_verification'], 'pending')

    def test_interrupted_apply_requires_recovery_then_resumes(self):
        self.init()
        plan = self.preview()
        real = packages.compose
        def interrupt(*args, **kw):
            return real(*args, **kw) if kw.get('preview') else real(*args, **kw, fail_after=1)
        with mock.patch.object(enrollment, 'compose', side_effect=interrupt):
            with self.assertRaisesRegex(ValueError, 'interruption'):
                self.apply(plan)
        with self.assertRaisesRegex(setup.SetupError, 'Run package recover'):
            self.apply(plan)
        packages.recover(self.root)
        self.assertEqual(self.apply(plan)['status'], 'installed')

    def test_public_optional_essentials_only_after_selection(self):
        self.init()
        self.services.access = False
        self.assertFalse((self.root / 'blueprints/youtube-transcripts.md').exists())
        result = self.apply(self.preview('agent-essentials'))
        self.assertEqual(result['status'], 'installed')
        self.assertTrue((self.root / 'blueprints/youtube-transcripts.md').exists())
        self.assertFalse(any(c == ['gh', 'api', 'repos/aibuild-lab/agent-essentials'] for c in self.services.calls))

    def test_tampered_archive_and_installed_update_refused(self):
        self.init()
        plan = self.preview()
        path = self.bundles / 'agent-workforce/payload.zip'
        path.write_bytes(path.read_bytes() + b'tampered')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            self.apply(plan)
        bad = copy.deepcopy(self.family)
        bad['packages']['workbench-core']['version'] = '0.0.11'
        bad['packages']['workbench-core']['release_tag'] = 'workbench-core-v0.0.11'
        self.lockfile.write_bytes(packages.encoded(bad))
        self.lockhash = packages.digest(self.lockfile.read_bytes())
        with self.assertRaisesRegex(setup.SetupError, 'update installed'):
            self.preview()


if __name__ == '__main__':
    unittest.main()
