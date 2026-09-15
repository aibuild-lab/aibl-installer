"""Real first-enrollment, local Git update, and interruption recovery.

Account replies, private ownership, provider PRs and student approval are
synthetic. No hosted writes, app use, or native qualification are asserted.
"""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_standalone_enrollment as enrollment_fixture
import test_student_updates as update_fixture
from test_family_v2 import package_core
import student_updates as u
import student_update_sync as sync
import workbench_packages as packages
from release_files import lock


class EnrollmentUpdateSync(unittest.TestCase):
    package = enrollment_fixture.StandaloneEnrollment.package
    v2 = enrollment_fixture.StandaloneEnrollment.v2
    init = enrollment_fixture.StandaloneEnrollment.init
    preview = enrollment_fixture.StandaloneEnrollment.preview
    apply = enrollment_fixture.StandaloneEnrollment.apply

    def setUp(self):
        enrollment_fixture.StandaloneEnrollment.setUp(self)
        if getattr(self,'seed_fixture',False):
            self.seed_path='course/workforce/student-authoring/lesson-notes.md'
            self.add_seed_package(self.seed_path,'Your own lesson notes')
            self.lockfile.write_bytes(packages.encoded(self.family))
            self.lockhash=packages.digest(self.lockfile.read_bytes())
        self.init()
        self.apply(self.preview())
        self.remote = self.services.server
        self.backend = update_fixture.Backend(self)
        self.repo_patch = patch.object(u, 'repository', return_value='student/my-workbench')
        self.repo_patch.start()
        self.addCleanup(self.repo_patch.stop)
        u.git(self.root, 'remote', 'set-url', 'origin', str(self.remote))
        self.old_marker = (self.root / packages.MARKER).read_bytes()
        self.old_native = {name: (self.root / name).read_bytes() for name in packages.read(self.root / packages.MARKER)['files']
                           if packages.read(self.root / packages.MARKER)['files'][name]['product'] == 'agent-workforce'}
        (self.root / 'context/project.md').write_text('Unfinished private student context')
        (self.root / 'work-in-progress.txt').write_text('Do not stage me')
        (self.root / '.aibl-local/learning').mkdir()
        (self.root / '.aibl-local/learning/progress.json').write_text('Private learning state')
        package_core(self, {'.agents/skills/aibl-enroll/SKILL.md': 'updated'}, version='0.0.11')
        self.family['packages']['workbench-core'].update(publisher=packages.PUBLIC_TEMPLATE,
            release_tag='workbench-core-v0.0.11', release_target='b' * 40)

    def add_seed_package(self,name,content,version='0.0.10'):
        _,payload=packages.verify(self.bundles,'agent-workforce',self.family['packages']['agent-workforce'])
        files={path:raw.decode('utf-8') for path,raw in payload.items()}
        files[name]=content
        self.package('agent-workforce',files,version=version)
        path=self.bundles/'agent-workforce/manifest.json'
        manifest=packages.read(path)
        for row in manifest['files']:
            if row['path']==name:row['policy']='seed'
        path.write_bytes(packages.encoded(manifest))
        self.family['packages']['agent-workforce'].update(manifest_sha256=packages.digest(path.read_bytes()),
            publisher=packages.V2_PUBLISHERS['agent-workforce'],release_tag='v'+version,release_target='b'*40)

    def prepare(self):
        return u.prepare(self.root, self.bundles, self.family, 'one', self.base / 'preparations', self.backend)

    def merge(self):
        state = self.prepare()
        u.propose(self.root, 'one', self.backend)
        def real_merge(repository, number, head):
            self.backend.merges += 1
            tree = u.git(state['candidate'], 'rev-parse', head + '^{tree}')
            merge = u.git(state['candidate'], 'commit-tree', tree, '-p', state['base_revision'], '-p', head, '-m', 'Synthetic provider merge')
            u.git(state['candidate'], 'push', 'origin', merge + ':refs/heads/main')
            self.backend.pr.update(merged_at='2026-09-14T00:00:00Z', merge_commit_sha=merge, state='closed')
            if self.backend.uncertain: raise OSError('Synthetic lost merge response')
        self.backend.merge = real_merge
        return u.approve_and_merge(self.root, 'one', state['head_revision'], self.backend)

    def student_work_unchanged(self):
        self.assertEqual((self.root / 'context/project.md').read_text(), 'Unfinished private student context')
        self.assertEqual((self.root / 'work-in-progress.txt').read_text(), 'Do not stage me')
        self.assertEqual((self.root / '.aibl-local/learning/progress.json').read_text(), 'Private learning state')

    def synchronized(self):
        state = u.synchronize(self.root, 'one')
        self.assertEqual(state['stage'], 'local_synchronized')
        self.assertIn('pending', state['native_verification'])
        self.assertEqual(u.git(self.root, 'rev-parse', 'HEAD'), state['merge_revision'])
        self.assertEqual((self.root / '.agents/skills/aibl-enroll/SKILL.md').read_text(), 'updated')
        for name, raw in self.old_native.items(): self.assertEqual((self.root / name).read_bytes(), raw)
        self.assertEqual(sync.location(self.root, 'one', 'before/' + packages.MARKER).read_bytes(), self.old_marker)
        self.student_work_unchanged()
        return state

    def test_actual_uncommitted_enrollment_joins_single_pr_without_checkpoint(self):
        remote_marker = json.loads(u.git(self.root, 'show', 'HEAD:' + packages.MARKER))
        self.assertEqual(set(remote_marker['packages']), {'agent-workbench', 'workbench-core'})
        self.assertIn('agent-workforce', packages.read(self.root / packages.MARKER)['packages'])
        before = u.git(self.root, 'rev-parse', 'HEAD')
        self.backend.uncertain = True
        state = self.merge()
        self.assertEqual(u.git(self.root, 'rev-parse', 'HEAD'), before)
        changed = set(u.git(state['candidate'], 'diff', '--name-only', state['base_revision'], state['head_revision']).splitlines())
        self.assertIn('course/workforce/connection.json', changed)
        self.assertIn('.agents/skills/aibl-enroll/SKILL.md', changed)
        self.assertNotIn('context/project.md', changed)
        self.assertEqual(self.backend.creates, 1)
        self.assertEqual(self.backend.merges, 1)
        result = self.synchronized()
        self.assertEqual(u.synchronize(self.root, 'one'), result)

    def test_staged_student_work_refused_before_normalization(self):
        self.merge()
        u.git(self.root, 'add', 'work-in-progress.txt')
        staged = u.git(self.root, 'write-tree')
        with self.assertRaisesRegex(packages.ReleaseError, 'staged'): u.synchronize(self.root, 'one')
        self.assertEqual(u.git(self.root, 'write-tree'), staged)
        self.assertEqual((self.root / packages.MARKER).read_bytes(), self.old_marker)
        self.student_work_unchanged()

    def test_unpushed_commit_refused_before_normalization(self):
        self.merge()
        u.git(self.root, 'add', 'work-in-progress.txt')
        u.git(self.root, 'commit', '-m', 'Unpushed student work')
        head = u.git(self.root, 'rev-parse', 'HEAD')
        with self.assertRaisesRegex(packages.ReleaseError, 'HEAD advanced'): u.synchronize(self.root, 'one')
        self.assertEqual(u.git(self.root, 'rev-parse', 'HEAD'), head)
        self.assertEqual((self.root / packages.MARKER).read_bytes(), self.old_marker)

    def test_concurrent_package_guard_refuses_sync(self):
        self.merge()
        with lock(self.root):
            with self.assertRaisesRegex(packages.ReleaseError, 'process'): u.synchronize(self.root, 'one')
        self.assertEqual((self.root / packages.MARKER).read_bytes(), self.old_marker)

    def test_lost_response_after_real_fast_forward_reconciles(self):
        self.merge()
        real_git = u.git
        def lost(root, *args):
            result = real_git(root, *args)
            if args[:2] == ('merge', '--ff-only'): raise OSError('Synthetic lost successful Git response')
            return result
        with patch.object(u, 'git', side_effect=lost): self.synchronized()

    def test_failed_merge_restores_enrollment_bytes(self):
        self.merge()
        real_git = u.git
        def rejected(root, *args):
            if args[:2] == ('merge', '--ff-only'): raise packages.ReleaseError('Synthetic Git refusal')
            return real_git(root, *args)
        with patch.object(u, 'git', side_effect=rejected):
            with self.assertRaisesRegex(packages.ReleaseError, 'Git refusal'): u.synchronize(self.root, 'one')
        self.assertEqual((self.root / packages.MARKER).read_bytes(), self.old_marker)
        for name, raw in self.old_native.items(): self.assertEqual((self.root / name).read_bytes(), raw)
        self.student_work_unchanged()
        self.synchronized()

    def test_each_normalization_interruption_recovers(self):
        # Marker plus three first-enrollment files require normalization.
        for stop in range(1, 5):
            with self.subTest(stop=stop):
                case = EnrollmentUpdateSync()
                case.setUp()
                try:
                    case.merge()
                    original = sync.apply_file
                    count = [0]
                    def interrupt(*args, **kwargs):
                        original(*args, **kwargs)
                        count[0] += 1
                        if count[0] == stop: raise OSError('Synthetic normalization interruption')
                    with patch.object(sync, 'apply_file', side_effect=interrupt):
                        with self.assertRaises(OSError): u.synchronize(case.root, 'one')
                    case.synchronized()
                finally: case.doCleanups()

    def test_each_snapshot_and_journal_write_interruption_recovers(self):
        # Six core entries, three Workforce files, marker, plan and pending marker.
        for stop in range(1, 13):
            with self.subTest(stop=stop):
                case = EnrollmentUpdateSync()
                case.setUp()
                try:
                    case.merge()
                    original = sync.atomic
                    count = [0]
                    def interrupt(*args, **kwargs):
                        original(*args, **kwargs)
                        count[0] += 1
                        if count[0] == stop: raise OSError('Synthetic snapshot interruption')
                    with patch.object(sync, 'atomic', side_effect=interrupt):
                        with self.assertRaises(OSError): u.synchronize(case.root, 'one')
                    case.synchronized()
                finally: case.doCleanups()

    def test_later_edit_during_pending_normalization_is_retained(self):
        self.merge()
        original = sync.apply_file
        def interrupt(*args, **kwargs):
            original(*args, **kwargs)
            raise OSError('Synthetic interruption')
        with patch.object(sync, 'apply_file', side_effect=interrupt):
            with self.assertRaises(OSError): u.synchronize(self.root, 'one')
        changed = self.root / 'workforce/guide.md'
        changed.write_text('Student later native customization')
        with self.assertRaisesRegex(packages.ReleaseError, 'later edits'): u.synchronize(self.root, 'one')
        self.assertEqual(changed.read_text(), 'Student later native customization')
        self.assertEqual(sync.location(self.root, 'one', 'before/' + packages.MARKER).read_bytes(), self.old_marker)
        self.student_work_unchanged()

    def test_lost_final_state_write_recovers_same_merge(self):
        self.merge()
        original = u.save
        def interrupt(path, state):
            if state['stage'] == 'local_synchronized': raise OSError('Synthetic lost final state write')
            original(path, state)
        with patch.object(u, 'save', side_effect=interrupt):
            with self.assertRaises(OSError): u.synchronize(self.root, 'one')
        self.synchronized()

    def test_interrupted_normalization_blocks_package_interleaving(self):
        self.merge()
        original = sync.apply_file
        def interrupt(*args, **kwargs):
            original(*args, **kwargs)
            raise OSError('Synthetic interruption')
        with patch.object(sync, 'apply_file', side_effect=interrupt):
            with self.assertRaises(OSError): u.synchronize(self.root, 'one')
        before = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        for action in (
            lambda: packages.compose(self.root, self.bundles, self.family, ['agent-essentials']),
            lambda: packages.compose(self.root, self.bundles, self.family, ['agent-workforce'], preview=True),
            lambda: packages.repair(self.root, self.bundles, 'workbench-core', ['.agents/skills/aibl-enroll/SKILL.md'], {'.agents/skills/aibl-enroll/SKILL.md': None}),
            lambda: packages.recover(self.root),
            lambda: packages.recover(self.root, '123'),
            lambda: u.prepare(self.root, self.bundles, self.family, 'two', self.base / 'preparations', self.backend),
            lambda: enrollment_fixture.enrollment.apply_plan(self.root, '0' * 32, runner=self.services, state_root=self.plans),
        ):
            with self.assertRaisesRegex(packages.ReleaseError, 'existing student update'): action()
            self.assertEqual({p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}, before)
        # The actual enrollment preview reaches the same held package engine.
        with self.assertRaisesRegex(packages.ReleaseError, 'existing student update'):
            self.preview('agent-essentials')
        self.assertEqual({p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}, before)
        self.assertEqual(packages.status(self.root)['status'], 'recovery_required')
        self.synchronized()
        self.assertFalse((self.root / packages.SYNC_PENDING).exists())

    def test_lost_pending_clear_response_is_idempotent(self):
        self.merge()
        with patch.object(sync, 'finish', side_effect=OSError('Synthetic interruption before clear')):
            with self.assertRaises(OSError): u.synchronize(self.root, 'one')
        self.assertTrue((self.root / packages.SYNC_PENDING).exists())
        state = u.read_state(self.root, 'one')
        self.assertEqual(state['stage'], 'local_synchronized')
        before = (self.root / packages.MARKER).stat().st_mtime_ns
        self.synchronized()
        self.assertFalse((self.root / packages.SYNC_PENDING).exists())
        self.assertEqual((self.root / packages.MARKER).stat().st_mtime_ns, before)

    def test_local_student_seed_omitted_from_pr_preserves_customization_and_deletion(self):
        for choice in ('unchanged','customized','deleted'):
            with self.subTest(choice=choice):
                case=EnrollmentUpdateSync()
                case.seed_fixture=True
                case.setUp()
                try:
                    path=case.root/case.seed_path
                    if choice=='customized':path.write_text('Private student response, never copy this into the package PR')
                    if choice=='deleted':path.unlink()
                    before=path.read_bytes() if path.exists() else None
                    state=case.merge()
                    self.assertIn(case.seed_path,state['local_only_seeds'])
                    self.assertNotIn(case.seed_path,{row['path'] for row in state['intended_changes']})
                    self.assertEqual(u.git(state['candidate'],'ls-tree','--name-only','-z',state['head_revision'],'--',case.seed_path),'')
                    result=u.synchronize(case.root,'one')
                    self.assertEqual(result['stage'],'local_synchronized')
                    self.assertEqual(path.read_bytes() if path.exists() else None,before)
                    self.assertEqual(u.git(case.root,'ls-tree','--name-only','-z','HEAD','--',case.seed_path),'')
                    self.assertEqual(packages.read(case.root/packages.MARKER)['files'][case.seed_path]['policy'],'seed')
                    case.student_work_unchanged()
                finally:case.doCleanups()

    def test_newly_introduced_seed_still_enters_reviewed_pr(self):
        name='course/workforce/student-authoring/new-update-notes.md'
        self.add_seed_package(name,'New optional notes starter',version='0.0.11')
        state=self.merge()
        self.assertNotIn(name,state['local_only_seeds'])
        self.assertIn(name,{row['path'] for row in state['intended_changes']})
        self.assertEqual(u.git(state['candidate'],'show',state['head_revision']+':'+name),'New optional notes starter')
        self.assertEqual(u.synchronize(self.root,'one')['stage'],'local_synchronized')
        self.assertEqual((self.root/name).read_text(),'New optional notes starter')
        self.student_work_unchanged()

    def test_new_seed_collision_does_not_normalize_or_discard_student_file(self):
        name='course/workforce/student-authoring/new-update-notes.md'
        self.add_seed_package(name,'New optional notes starter',version='0.0.11')
        (self.root/name).parent.mkdir(parents=True,exist_ok=True)
        (self.root/name).write_text('Pre-existing private student answer')
        self.merge()
        with self.assertRaises(packages.ReleaseError):u.synchronize(self.root,'one')
        self.assertEqual((self.root/name).read_text(),'Pre-existing private student answer')
        self.assertEqual((self.root/packages.MARKER).read_bytes(),self.old_marker)
        self.student_work_unchanged()


if __name__ == '__main__': unittest.main()
