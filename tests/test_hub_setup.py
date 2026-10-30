import json, os, sys, tempfile, unittest
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
        self.team_hq = False          # the student's repository on GitHub already holds Agent Team HQ's work/team-hq/

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
            if self.team_hq:
                (p / 'work' / 'team-hq').mkdir(parents=True); (p / 'work' / 'team-hq' / 'north-star.md').write_text('mine\n')
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


# Throwaway home folders go under AIBL_TEST_SCRATCH when it is set (removed after each test either way).
SCRATCH = os.environ.get('AIBL_TEST_SCRATCH') or None
PROMPT = (Path(__file__).resolve().parents[1] / 'SETUP-PROMPT.md').read_text(encoding='utf-8')
CAMP = {'schema_version': 'aibl.repository-descriptor/v2', 'id': 'repo.agent-native-camp'}


def scratch_home():
    if SCRATCH:
        Path(SCRATCH).mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=SCRATCH)


def camp_clone(home, descriptor=CAMP):
    folder = Path(home) / 'GitHub' / 'agent-native-camp'
    (folder / '.aibl').mkdir(parents=True)
    (folder / 'START-HERE.md').write_text('camp\n')
    if descriptor is not None:
        (folder / '.aibl' / 'repository.json').write_text(descriptor if isinstance(descriptor, str) else json.dumps(descriptor))
    return folder


def snapshot(base):
    out = {}
    for dirpath, dirnames, filenames in os.walk(base):
        for name in dirnames + filenames:
            full = Path(dirpath) / name
            info = full.lstat()
            out[full.relative_to(base).as_posix()] = (info.st_size, info.st_mtime_ns)
    return out


class LeftBehindTests(unittest.TestCase):
    """cloned_existing: the workbench came back from GitHub, for example onto a new computer, without
    what only ever lived on the old one (risk R6 in Wonderboy's Returning-Students-Routes-10-30-2026)."""

    def test_cloned_back_says_what_stayed_on_the_old_computer(self):
        with scratch_home() as home:
            f = Fake(); f.exists = True
            r = run(f, home)
            self.assertEqual(r['status'], 'cloned_existing')
            left = r['left_behind']
            self.assertEqual(left['say'], hub.LEFT_BEHIND)
            self.assertEqual(left['what'], ['library/', 'runs/', 'work/course/staff/voice*', '.env'])
            self.assertFalse(left['team_hq_night_shift'])
            self.assertNotIn('night shift', left['say'])
            for words in ('library', 'job folders', 'voice samples', 'old computer', 'If that computer still works'):
                self.assertIn(words, left['say'])

    def test_team_hq_workbench_also_hears_about_its_night_shift(self):
        with scratch_home() as home:
            f = Fake(); f.exists = True; f.team_hq = True
            left = run(f, home)['left_behind']
            self.assertTrue(left['team_hq_night_shift'])
            self.assertEqual(left['say'], hub.LEFT_BEHIND + '\n' + hub.LEFT_BEHIND_NIGHT_SHIFT)

    def test_new_and_reused_workbenches_say_nothing_about_it(self):
        with scratch_home() as home:
            f = Fake()
            self.assertNotIn('left_behind', run(f, home))     # created
            self.assertNotIn('left_behind', run(f, home))     # already_initialized

    def test_prompt_carries_the_same_words_for_an_older_script(self):
        self.assertIn('`left_behind.say` word for word', PROMPT)
        for line in hub.LEFT_BEHIND.split('\n'):
            self.assertIn('  > ' + line + '\n', PROMPT)

    def test_no_em_dashes_in_the_new_words(self):
        for text in (hub.LEFT_BEHIND, hub.LEFT_BEHIND_NIGHT_SHIFT, hub.CAMP_SAY):
            self.assertNotIn('—', text)


class CampNoticeTests(unittest.TestCase):
    """A Camp alum's own Camp clone sits at ~/GitHub/agent-native-camp. Setup only says it is untouched."""

    def test_camp_clone_with_its_descriptor_gets_one_line(self):
        with scratch_home() as home:
            folder = camp_clone(home)
            r = run(Fake(), home)
            self.assertEqual(r['camp'], {'folder': str(folder), 'say': hub.CAMP_SAY})

    def test_no_descriptor_or_another_id_or_unreadable_says_nothing(self):
        for descriptor in (None, {'id': 'repo.something-else'}, 'not json', json.dumps({'id': 'repo.agent-native-camp', 'pad': 'y' * 70000})):
            with self.subTest(descriptor=str(descriptor)[:20]), scratch_home() as home:
                camp_clone(home, descriptor)
                self.assertNotIn('camp', run(Fake(), home))

    def test_no_camp_says_nothing(self):
        with scratch_home() as home:
            self.assertNotIn('camp', run(Fake(), home))

    def test_camp_folder_is_left_exactly_as_it_was(self):
        with scratch_home() as home:
            folder = camp_clone(home)
            before = snapshot(folder)
            f = Fake(); f.exists = True
            run(f, home)
            self.assertEqual(snapshot(folder), before)
            self.assertFalse(any(str(folder) in ' '.join(map(str, c)) for c in f.calls))

    def test_prompt_says_the_camp_line_and_nothing_more(self):
        self.assertIn("Say its `camp.say` once, word for word. Say nothing else about Camp", PROMPT)


if __name__ == '__main__':
    unittest.main()
