"""Synthetic immutable releases with real Git history/push; account calls simulated."""
import contextlib, io, json, os, stat, sys, tempfile, unittest, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import course_setup as setup
import pinned_distribution as pinned
from test_course_setup_integration import LocalServices

def bundle_fixture():
    payload = {'README.md': b'# Synthetic Essentials\n', '.gitignore': b'.aibl-local/\n__pycache__/\n', 'scripts/aibl.py': b"from pathlib import Path\np=Path('context');p.mkdir(exist_ok=True)\nf=p/'project.md'\nif not f.exists():f.write_text('Synthetic pinned starter')\n"}
    manifest = {'schema_version': 'aibl.course-release/v3', 'product': 'agent-essentials', 'release_id': 'agent-essentials-v0.0.0-synthetic', 'source_repository': 'aibuild-lab/agent-native-workforce-internal', 'source_revision': 'a' * 40, 'files': [{'source': 'synthetic/' + str(i) + '.txt', 'path': path, 'sha256': pinned.digest(data), 'mode': 0o644} for i, (path, data) in enumerate(payload.items())]}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for path, data in payload.items():
            info = zipfile.ZipInfo(path); info.create_system = 3; info.external_attr = (stat.S_IFREG | 0o644) << 16; archive.writestr(info, data)
    archive = stream.getvalue(); manifest_bytes = pinned.encoded(manifest)
    essentials = {'schema_version': 'aibl.release-pin/v3', 'product': 'agent-essentials', 'release_id': manifest['release_id'], 'source_revision': manifest['source_revision'], 'archive_sha256': pinned.digest(archive), 'manifest_sha256': pinned.digest(manifest_bytes)}
    workforce = {**essentials, 'product': 'agent-native-workforce', 'release_id': 'agent-native-workforce-v0.0.0-synthetic'}
    distribution = {'schema_version': 'aibl.course-distribution/v1', 'course_id': 'agent-workforce', 'installer': {'repository': 'aibuild-lab/aibl-installer', 'commit': 'b' * 40, 'files': {name: 'c' * 64 for name in pinned.INSTALLER_FILES}}, 'source_release_pins': {'agent-essentials': essentials, 'agent-native-workforce': workforce}}
    return manifest_bytes, archive, distribution

class PinnedServices(LocalServices):
    def __init__(self, root):
        super().__init__(root); self.manifest_bytes, self.archive, self.distribution = bundle_fixture(); self.description = None; self.lose_push_reply = False

    def __call__(self, args, cwd=None, interactive=False):
        if args[:3] == ['gh', 'release', 'download']:
            self.calls.append(args); directory = Path(args[args.index('--dir') + 1]); directory.mkdir(parents=True, exist_ok=True)
            (directory / 'manifest.json').write_bytes(self.manifest_bytes); (directory / 'payload.zip').write_bytes(self.archive); return ''
        if args[:3] == ['gh', 'repo', 'create']:
            self.calls.append(args); self.description = args[args.index('--description') + 1]
            self.git('init', '--bare', '--initial-branch=main', str(self.server))
            if self.lose_create_reply: self.lose_create_reply = False; raise setup.SetupError('Lost creation reply', 'network')
            return ''
        if args[:2] == ['gh', 'api'] and args[2] == 'repos/synthetic-student/my-workbench':
            self.calls.append(args)
            if not self.server.exists(): raise setup.SetupError('HTTP 404', 'not_found')
            return json.dumps({'private': True, 'full_name': 'synthetic-student/my-workbench', 'id': 456, 'default_branch': 'main', 'description': self.description})
        if args[:3] == ['git', 'ls-remote', '--heads']:
            self.calls.append(args); return self.git('ls-remote', '--heads', str(self.server))
        if args[:3] == ['git', 'push', '--set-upstream']:
            self.calls.append(args); result = self.git('push', str(self.server), 'HEAD:refs/heads/main', cwd=cwd)
            if self.lose_push_reply: self.lose_push_reply = False; raise setup.SetupError('Lost push reply', 'network')
            return result
        return super().__call__(args, cwd, interactive)

class PinnedSetupTests(unittest.TestCase):
    def run_setup(self, services, root, sha='d' * 64):
        with contextlib.redirect_stdout(io.StringIO()):
            return setup.setup(setup.choose('agent-workforce'), root / 'projects', 'my-workbench', root / 'state', services, True, services.distribution, sha)

    def test_exact_release_seeds_independent_private_history_and_preserves_rerun_work(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); services = PinnedServices(root)
            result = self.run_setup(services, root); project = Path(result['workspace'])
            self.assertEqual(result['next'], '/aibl-teach')
            self.assertEqual((project / 'context/project.md').read_text(), 'Synthetic pinned starter')
            self.assertEqual(services.git('rev-list', '--count', 'HEAD', cwd=project), '1')
            self.assertFalse(any('--template' in call for call in services.calls))
            (project / 'context/project.md').write_text('Student decision')
            self.run_setup(services, root)
            self.assertEqual((project / 'context/project.md').read_text(), 'Student decision')
            self.assertEqual(sum(call[:3] == ['gh', 'repo', 'create'] for call in services.calls), 1)
            attempt = json.loads((root / 'state/my-workbench.json').read_text())['attempts'][-1]
            self.assertEqual(attempt['provenance']['distribution_sha256'], 'd' * 64)
            self.assertEqual(attempt['provenance']['source_release_pins'], services.distribution['source_release_pins'])

    def test_lost_create_and_push_replies_resume_without_new_repository_or_history(self):
        for phase in ('lose_create_reply', 'lose_push_reply'):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve(); services = PinnedServices(root); setattr(services, phase, True)
                with self.assertRaisesRegex(setup.SetupError, 'Lost'): self.run_setup(services, root)
                result = self.run_setup(services, root)
                self.assertEqual(services.git('rev-list', '--count', 'HEAD', cwd=Path(result['workspace'])), '1')
                self.assertEqual(sum(call[:3] == ['gh', 'repo', 'create'] for call in services.calls), 1)

    def test_existing_name_collision_and_changed_helper_preserve_work(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); services = PinnedServices(root); services.git('init', '--bare', str(services.server))
            with self.assertRaisesRegex(ValueError, 'collision'): self.run_setup(services, root)
            self.assertFalse((root / 'projects/my-workbench').exists())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); services = PinnedServices(root); project = Path(self.run_setup(services, root)['workspace'])
            script = project / 'scripts/aibl.py'; script.write_text('raise Exception("student experiment")\n')
            with self.assertRaisesRegex(ValueError, 'helper changed'): self.run_setup(services, root)
            self.assertIn('student experiment', script.read_text())
            with self.assertRaisesRegex(ValueError, 'different frozen distribution'): self.run_setup(services, root, 'e' * 64)

    def test_staging_edits_survive_interrupted_push(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); services = PinnedServices(root); services.lose_push_reply = True
            with self.assertRaises(setup.SetupError): self.run_setup(services, root)
            note = root / 'projects/.my-workbench-clone-in-progress/student-note.md'; note.write_text('Keep this')
            with self.assertRaisesRegex(ValueError, 'unrecognized work'): self.run_setup(services, root)
            self.assertEqual(note.read_text(), 'Keep this')

    def test_pinned_setup_cannot_resume_through_mutable_launcher(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); services = PinnedServices(root)
            project = Path(self.run_setup(services, root)['workspace']); calls = len(services.calls)
            (project / 'context/project.md').write_text('Preserve my decision')
            with self.assertRaisesRegex(setup.SetupError, 'reviewed pinned launcher'):
                setup.setup(setup.choose('agent-workforce'), root / 'projects', 'my-workbench', root / 'state', services, True)
            self.assertEqual(len(services.calls), calls)
            self.assertEqual((project / 'context/project.md').read_text(), 'Preserve my decision')

    def test_mutable_setup_cannot_be_silently_converted_to_pinned(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); services = PinnedServices(root)
            state = root / 'state/my-workbench.json'; state.parent.mkdir()
            state.write_text(json.dumps({'schema_version': 'aibl.setup-progress/v1', 'repository_name': 'my-workbench', 'repository': 'synthetic-student/my-workbench', 'attempts': []}))
            with self.assertRaisesRegex(setup.SetupError, 'began without a frozen distribution'): self.run_setup(services, root)
            self.assertFalse(services.calls)
            self.assertNotIn('distribution_sha256', json.loads(state.read_text()))

    def test_staging_git_link_and_special_files_stop_before_writes(self):
        for kind in ('git-link', 'fifo'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve(); services = PinnedServices(root); services.lose_push_reply = True
                with self.assertRaises(setup.SetupError): self.run_setup(services, root)
                staging = root / 'projects/.my-workbench-clone-in-progress'
                if kind == 'git-link':
                    (staging / '.git').rename(root / 'metadata'); (staging / '.git').symlink_to(root / 'metadata', target_is_directory=True)
                else:
                    if not hasattr(os, 'mkfifo'): continue
                    os.mkfifo(staging / 'student-pipe')
                with self.assertRaisesRegex(ValueError, 'Git metadata|nonregular'): self.run_setup(services, root)
                self.assertFalse((root / 'projects/my-workbench').exists())

    def test_wrong_archive_is_rejected_before_private_source_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); services = PinnedServices(root); services.archive += b'alteration'
            with self.assertRaisesRegex(ValueError, 'release bytes'): self.run_setup(services, root)
            self.assertFalse((root / 'projects/my-workbench').exists())

class DistributionContractTests(unittest.TestCase):
    def test_lock_requires_both_product_pins_and_exact_source(self):
        _, _, lock = bundle_fixture(); pinned.validate_lock(lock)
        lock['source_release_pins']['agent-essentials']['source_revision'] = 'f' * 40
        with self.assertRaisesRegex(ValueError, 'different accepted sources'): pinned.validate_lock(lock)

    def test_lock_digest_and_installer_file_drift_are_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); _, _, lock = bundle_fixture()
            for name in pinned.INSTALLER_FILES:
                path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('synthetic installer file\n'); lock['installer']['files'][name] = pinned.digest(path.read_bytes())
            lockpath = root / 'external-lock.json'; data = pinned.encoded(lock); lockpath.write_bytes(data)
            def runner(args, cwd=None): return lock['installer']['commit'] if args[1] == 'rev-parse' else ''
            self.assertEqual(pinned.load_lock(lockpath, pinned.digest(data), root, runner)[0], lock)
            with self.assertRaisesRegex(ValueError, 'independently supplied digest'): pinned.load_lock(lockpath, '0' * 64, root, runner)
            (root / 'start.sh').write_text('changed')
            with self.assertRaisesRegex(ValueError, 'Installer file differs'): pinned.load_lock(lockpath, pinned.digest(data), root, runner)

    def test_archive_links_and_traversal_are_rejected_even_with_matching_archive_pin(self):
        manifest_bytes, _, lock = bundle_fixture(); manifest = json.loads(manifest_bytes)
        for path, mode in [('../escape', stat.S_IFREG), ('.GIT/config', stat.S_IFREG), ('scripts/aibl.py', stat.S_IFLNK)]:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                manifest['files'] = [{'source': 'synthetic/source.py', 'path': path, 'sha256': pinned.digest(b'x'), 'mode': 0o644}]
                stream = io.BytesIO()
                with zipfile.ZipFile(stream, 'w') as archive:
                    info = zipfile.ZipInfo(path); info.create_system = 3; info.external_attr = (mode | 0o644) << 16; archive.writestr(info, b'x')
                root = Path(directory); data = pinned.encoded(manifest); (root / 'manifest.json').write_bytes(data); (root / 'payload.zip').write_bytes(stream.getvalue())
                pin = {**lock['source_release_pins']['agent-essentials'], 'archive_sha256': pinned.digest(stream.getvalue()), 'manifest_sha256': pinned.digest(data)}
                with self.assertRaises(ValueError): pinned.verify_bundle(root, pin)

if __name__ == '__main__': unittest.main()
