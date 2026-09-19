import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import hub_setup as hub
from course_setup import SetupError

TEMPLATE = 'aibuild-lab/my-workbench-template'
FULL = 'synthetic-student/my-workbench'


class Fake:
    """Answers the exact commands hub_setup runs. Nothing touches the network."""

    def __init__(self):
        self.calls = []
        self.github = True
        self.exists = False           # <user>/my-workbench on GitHub
        self.private = True
        self.made_from = TEMPLATE
        self.commits_after = 0        # how many polls before the new repo has its first commit
        self.template_visible = True
        self.claude = True
        self.with_skills = True
        self.template_version = '0.0.12'   # .aibl/template.json in the template; None means the template ships no stamp

    def __call__(self, args, cwd=None, interactive=False):
        self.calls.append(args)
        if args[-1] == '--version':
            return {'git': 'git version 2.49.0', 'gh': 'gh version 2.70.0', 'claude': '2.1.228', 'node': 'v22.12.0', 'codex': 'codex-cli 0.154.0'}.get(args[0], 'Python 3.13.0')
        if args == ['gh', 'api', 'user']:
            if not self.github:
                raise SetupError('No selected GitHub sign-in', 'authentication_missing')
            return json.dumps({'login': 'synthetic-student', 'name': 'Student', 'id': 123})
        if args[:2] == ['gh', 'api'] and args[2] == 'repos/' + TEMPLATE:
            if not self.template_visible:
                raise SetupError('HTTP 404', 'not_found')
            return json.dumps({'is_template': True, 'default_branch': 'main', 'private': False})
        if args[:2] == ['gh', 'api'] and args[2] == f'repos/{TEMPLATE}/commits/main':
            return json.dumps({'sha': 'a' * 40})
        if args[:2] == ['gh', 'api'] and args[2] == f'repos/{FULL}/commits/main':
            if self.commits_after > 0:
                self.commits_after -= 1
                raise SetupError('HTTP 404', 'not_found')
            return json.dumps({'sha': 'b' * 40})
        if args[:2] == ['gh', 'api'] and args[2] == 'repos/' + FULL:
            if not self.exists:
                raise SetupError('HTTP 404', 'not_found')
            return json.dumps({'private': self.private, 'full_name': FULL, 'id': 100, 'template_repository': {'full_name': self.made_from}})
        if args[:3] == ['gh', 'repo', 'create']:
            self.exists = True
            return ''
        if args[:3] == ['gh', 'repo', 'clone']:
            p = Path(args[-1]); p.mkdir(); (p / '.git').mkdir()
            if self.template_version:
                (p / '.aibl').mkdir(); (p / '.aibl' / 'template.json').write_text(json.dumps({'schema_version': 'aibl.workbench-template/v1', 'version': self.template_version}))
            if self.with_skills:
                for app in ('.claude', '.agents'):
                    for s in hub.SKILLS:
                        d = p / app / 'skills' / s; d.mkdir(parents=True); (d / 'SKILL.md').write_text('---\nname: ' + s + '\n---\n')
            return ''
        if args[:3] == ['git', 'remote', 'get-url']:
            return 'https://github.com/' + FULL + '.git'
        if args == ['git', 'rev-parse', '--show-toplevel']:
            return str(Path(cwd).resolve())
        if args[:3] == ['git', 'rev-parse'] and 'HEAD' in args:
            return 'b' * 40
        if args[:3] == ['git', 'config', '--local']:
            if '--get' in args:
                raise SetupError('not set')
            return ''
        if args[:3] == ['claude', 'auth', 'status']:
            return json.dumps({'loggedIn': self.claude})
        if args[:3] == ['codex', 'login', 'status']:
            return 'Logged in using ChatGPT'
        return '{}'


def run(fake, root, harness='claude', name='my-workbench'):
    return hub.setup(harness, Path(root) / 'GitHub', name, TEMPLATE, fake, sleep=lambda s: None, home=Path(root))


class HubSetupTests(unittest.TestCase):
    def test_registry_names_the_public_template(self):
        self.assertEqual(hub.public_template(), TEMPLATE)

    def test_fresh_student_gets_a_private_repo_from_the_template_and_three_skills(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fake(); f.commits_after = 2
            r = run(f, d)
            self.assertEqual(r['status'], 'created')
            self.assertIn(['gh', 'repo', 'create', FULL, '--private', '--template', TEMPLATE], f.calls)
            self.assertEqual(r['repository'], FULL)
            self.assertTrue(Path(r['workspace']).is_dir())
            self.assertEqual(r['skills']['.claude/skills'], list(hub.SKILLS))
            self.assertEqual(r['skills']['.agents/skills'], list(hub.SKILLS))
            self.assertEqual(r['skills_missing'], [])
            self.assertTrue(r['twin_signed_in'])
            self.assertEqual(r['template']['revision'], 'a' * 40)
            self.assertTrue((Path(r['workspace']) / '.aibl-local' / 'setup.json').is_file())
            # Nothing was cloned before the new repository had its first commit.
            create = f.calls.index(['gh', 'repo', 'create', FULL, '--private', '--template', TEMPLATE])
            clone = next(i for i, c in enumerate(f.calls) if c[:3] == ['gh', 'repo', 'clone'])
            polls = [c for c in f.calls[create:clone] if c[:2] == ['gh', 'api'] and c[2].endswith('/commits/main')]
            self.assertEqual(len(polls), 3)
            # Local identity was set only for this folder.
            self.assertIn(['git', 'config', '--local', 'user.name', 'Student'], f.calls)
            self.assertIn(['git', 'config', '--local', 'user.email', '123+synthetic-student@users.noreply.github.com'], f.calls)
            self.assertFalse(any(c[:2] == ['git', 'config'] and '--global' in c for c in f.calls))

    def test_receipt_carries_the_template_version_stamp_when_the_template_ships_one(self):
        # Step 10 of the prompt reports "template (version X.Y.Z)"; the number must come from the
        # receipt, or the assistant hunts through the workbench for it (Sara Davison, 09-19-2026).
        with tempfile.TemporaryDirectory() as root:
            r = run(Fake(), root)
            self.assertEqual(r['template']['version'], '0.0.12')
            self.assertEqual(r['template']['revision'], 'a' * 40)
        with tempfile.TemporaryDirectory() as root:
            f = Fake(); f.template_version = None
            r = run(f, root)
            self.assertIsNone(r['template']['version'])
        with tempfile.TemporaryDirectory() as root:
            bad = Path(root) / 'wb'; (bad / '.aibl').mkdir(parents=True); (bad / '.aibl' / 'template.json').write_text('not json')
            self.assertIsNone(hub.template_version(bad))

    def test_no_invitation_check_and_no_private_publisher_read(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fake(); run(f, d)
            reads = [c[2] for c in f.calls if c[:2] == ['gh', 'api'] and c[2].startswith('repos/aibuild-lab/')]
            self.assertTrue(all(r.startswith('repos/' + TEMPLATE) for r in reads), reads)

    def test_rerun_reuses_the_existing_workbench_and_changes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fake(); first = run(f, d)
            marker = Path(first['workspace']) / 'context' / 'project.md'
            marker.parent.mkdir(); marker.write_text('my facts')
            before = len(f.calls)
            second = run(f, d)
            self.assertEqual(second['status'], 'already_initialized')
            self.assertEqual(marker.read_text(), 'my facts')
            self.assertFalse(any(c[:3] in (['gh', 'repo', 'create'], ['gh', 'repo', 'clone']) for c in f.calls[before:]))

    def test_repo_exists_but_folder_is_gone_clones_it_back(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fake(); f.exists = True
            r = run(f, d)
            self.assertEqual(r['status'], 'cloned_existing')
            self.assertFalse(any(c[:3] == ['gh', 'repo', 'create'] for c in f.calls))

    def test_foreign_repo_with_the_same_name_is_kept_and_setup_stops(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fake(); f.exists = True; f.made_from = 'someone/else'
            with self.assertRaises(SetupError) as cm:
                run(f, d)
            self.assertIn('choose a different name', str(cm.exception))
            self.assertFalse(any(c[:3] == ['gh', 'repo', 'clone'] for c in f.calls))

    def test_public_repo_with_the_same_name_stops(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fake(); f.exists = True; f.private = False
            with self.assertRaises(SetupError) as cm:
                run(f, d)
            self.assertIn('not private', str(cm.exception))

    def test_existing_folder_with_a_different_origin_is_never_touched(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / 'GitHub' / 'my-workbench'; (folder / '.git').mkdir(parents=True)
            (folder / 'keep.txt').write_text('mine')
            f = Fake()
            original = f.__call__
            def call(args, cwd=None, interactive=False):
                if args[:3] == ['git', 'remote', 'get-url']:
                    return 'https://github.com/other/thing.git'
                return original(args, cwd, interactive)
            with self.assertRaises(SetupError) as cm:
                hub.setup('claude', Path(d) / 'GitHub', 'my-workbench', TEMPLATE, call, sleep=lambda s: None, home=Path(d))
            self.assertEqual((folder / 'keep.txt').read_text(), 'mine')
            self.assertIn('Rename that folder', str(cm.exception))

    def test_existing_folder_with_no_remote_at_all_is_named_plainly(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / 'GitHub' / 'my-workbench'; (folder / '.git').mkdir(parents=True)
            f = Fake()
            original = f.__call__
            def call(args, cwd=None, interactive=False):
                if args[:3] == ['git', 'remote', 'get-url']:
                    raise SetupError('git remote failed. No work was removed.')
                return original(args, cwd, interactive)
            with self.assertRaises(SetupError) as cm:
                hub.setup('claude', Path(d) / 'GitHub', 'my-workbench', TEMPLATE, call, sleep=lambda s: None, home=Path(d))
            self.assertIn('is not linked to github.com/' + FULL, str(cm.exception))
            self.assertIn('my-workbench-old', str(cm.exception))

    def test_github_not_signed_in_stops_before_anything_is_made(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fake(); f.github = False
            with self.assertRaises(SetupError) as cm:
                run(f, d)
            self.assertEqual(cm.exception.reason, 'authentication_missing')
            self.assertFalse(any(c[:3] == ['gh', 'repo', 'create'] for c in f.calls))

    def test_template_unreadable_stops_before_anything_is_made(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fake(); f.template_visible = False
            with self.assertRaises(SetupError):
                run(f, d)
            self.assertFalse(any(c[:3] == ['gh', 'repo', 'create'] for c in f.calls))

    def test_new_repo_that_never_fills_stops_with_a_retry_message(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fake(); f.commits_after = 99
            with self.assertRaises(SetupError) as cm:
                run(f, d)
            self.assertIn('run this same command again', str(cm.exception))
            self.assertFalse(any(c[:3] == ['gh', 'repo', 'clone'] for c in f.calls))

    def test_old_workbench_without_the_skills_is_reported_not_rewritten(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fake(); f.with_skills = False
            r = run(f, d)
            self.assertEqual(r['skills_missing'], list(hub.SKILLS))
            self.assertIn('note', r)

    def test_codex_harness_checks_the_codex_twin(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fake(); r = run(f, d, harness='codex')
            self.assertIn('codex', r['versions'])
            self.assertIn(['codex', 'login', 'status'], f.calls)
            self.assertTrue(r['twin_signed_in'])

    def test_synced_folders_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SetupError):
                hub.setup('claude', Path(d) / 'Documents', 'my-workbench', TEMPLATE, Fake(), sleep=lambda s: None, home=Path(d))

    def test_bad_names_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            for bad in ('my/workbench', 'con', 'x.git'):
                with self.assertRaises(SetupError):
                    run(Fake(), d, name=bad)


if __name__ == '__main__':
    unittest.main()
