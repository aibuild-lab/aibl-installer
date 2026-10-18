"""UPDATE-PROMPT.md step 1 and step 2 contract.

Step 1: a workbench without a GitHub connection is not "the wrong folder". A live run told a student "This
session is not open on your workbench" for their real workbench, because the old step 1 treated a failed
`git remote get-url origin` as the wrong folder. These tests pin the classification, the connect step's safety
checks, and the settings hook guidance.

Step 1, older workbenches: workbenches made in the first setup cohort (13 September 2026) never got
`.aibl/template.json`, so a student already in `my-workbench` was told to go and open `my-workbench`, and looped.
Step 1 now recognises an older workbench by its shape, adds the template's marker on a yes, and never sends a
student in a folder named `my-workbench` back to the same folder. The shape tests run the prompt's own checks and
Git commands on disposable folders.

Step 2: an unedited stock copy gets a "take the template version" recommendation. The staff rehearsal on
2026-10-14 (finding B3) saw five keep-or-take questions on about 43 KB of raw diff with no recommendation, for
files the student had never touched. The prompt now compares each copy's Git id with every version the template
shipped on main, recommends taking the template version only on an exact match (or when the workbench has no
copy), recommends nothing for a student edit, and falls back to the plain question when the history cannot be
read. The wording tests read the prompt; the history tests run the prompt's own Git commands on disposable
repositories. Nothing here runs an app.
"""
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEXT = (ROOT / 'UPDATE-PROMPT.md').read_text(encoding='utf-8')
FLAT = re.sub(r'\s+', ' ', TEXT)


def section(start, end):
    return TEXT.split(start, 1)[1].split(end, 1)[0]


STEP1 = section('## Step 1:', '## Step 2:')
CONNECT = section('### Connect it first', 'Run `git status --short`.')
MARKER = section('### Add the marker first', '### Connect it first')
RULES = section('## Rules', '## Step 1:')
STEP2 = section('## Step 2:', '## Step 3:')


def bullet(label):
    match = re.search(r'^- \*\*' + re.escape(label) + r'\*\*(.*)$', STEP1, flags=re.M)
    if not match:
        raise AssertionError('missing step 1 case: ' + label)
    return match.group(1)


class WorkbenchClassification(unittest.TestCase):
    def test_marker_file_decides_what_the_folder_is(self):
        self.assertIn('.aibl/template.json', STEP1)
        self.assertIn('aibuild-lab/my-workbench-template', STEP1)
        self.assertIn('not by `origin` alone', STEP1)

    def test_wrong_folder_message_only_when_there_is_no_marker(self):
        self.assertEqual(STEP1.count('This session is not open on your workbench'), 1)
        wrong = bullet('Not a workbench.')
        self.assertIn('This session is not open on your workbench', wrong)
        self.assertIn('no `.aibl/template.json`', wrong)
        for case in ('Your workbench, not connected to GitHub yet.', 'A workbench with no save history.',
                     'An older workbench, missing its marker.', 'A workbench from the retired course.'):
            self.assertNotIn('not open on your workbench', bullet(case))

    def test_missing_origin_is_a_workbench_that_needs_connecting(self):
        case = bullet('Your workbench, not connected to GitHub yet.')
        self.assertIn('`git remote get-url origin` fails', case)
        self.assertIn("isn't connected to your GitHub yet", case)
        self.assertIn('Connect it first', case)
        self.assertIn('continue', case)

    def test_a_clone_of_the_template_counts_as_not_connected(self):
        self.assertIn('`origin` is the public template', bullet('Your workbench, not connected to GitHub yet.'))

    def test_every_case_is_named_once(self):
        for case in ('Not a workbench.', 'A workbench from the retired course.', 'An older workbench, missing its marker.',
                     'A workbench with no save history.', 'Your workbench, not connected to GitHub yet.',
                     "Your workbench, connected to someone else's repository.", 'Your workbench, connected.'):
            with self.subTest(case=case):
                bullet(case)


class OlderWorkbench(unittest.TestCase):
    """A workbench from before the template carried its marker is still the student's workbench."""

    def test_the_shape_names_every_part(self):
        older = bullet('An older workbench, missing its marker.')
        for part in ('There is no `.aibl/template.json`', '`git rev-parse` worked', '`CLAUDE.md` or `AGENTS.md`',
                     'a `context/` folder', '`aibl-enroll`, `aibl-checkpoint` or `aibl-personalize`',
                     '`.claude/skills/` or `.agents/skills/`', 'it is not from the retired course', 'Add the marker first',
                     'from the top of this step'):
            with self.subTest(part=part):
                self.assertIn(part, older)

    def test_the_retired_course_is_sent_to_start_fresh_not_marked(self):
        retired = bullet('A workbench from the retired course.')
        self.assertIn('`.aibl/installed-agent-essentials.json`', retired)
        self.assertIn('`/aibl-teach`', retired)
        self.assertIn('Start fresh', retired)
        self.assertIn('Stop.', retired)
        self.assertLess(STEP1.index('**A workbench from the retired course.**'),
                        STEP1.index('**An older workbench, missing its marker.**'))

    def test_the_wrong_folder_message_never_loops_inside_my_workbench(self):
        wrong = bullet('Not a workbench.')
        named = wrong.index('If the folder is named `my-workbench`')
        self.assertIn("part of an older workbench's shape but not all of it", wrong)
        self.assertIn('do not send them back to it', wrong)
        self.assertIn('it is missing <what is missing, in plain words>', wrong)
        self.assertIn("ask in your program's channel", wrong[named:wrong.index('Otherwise')])
        self.assertLess(named, wrong.index('Otherwise, say: "This session is not open on your workbench.'))

    def test_the_marker_comes_from_the_template_and_is_checked(self):
        self.assertIn("step 2's two commands", MARKER)
        self.assertIn('`git show template/main:.aibl/template.json`', MARKER)
        self.assertIn('`schema_version` is `aibl.workbench-template/v1`', MARKER)
        self.assertIn('`repository` is `aibuild-lab/my-workbench-template`', MARKER)
        self.assertIn('not a plain folder', MARKER)

    def test_the_file_is_shown_and_written_only_after_a_yes(self):
        ask = MARKER.index('OK?"')
        self.assertLess(MARKER.index("the file's exact contents"), ask)
        self.assertLess(ask, MARKER.index('git checkout template/main -- .aibl/template.json'))
        self.assertIn('On a no, say:', MARKER)
        self.assertIn('run each of these yourself', MARKER)

    def test_only_the_marker_is_committed(self):
        self.assertIn('`git commit -m "Add the workbench marker file" -- .aibl/template.json`', MARKER)
        self.assertIn('nothing else', MARKER)
        self.assertIn('`git diff --quiet HEAD template/main -- .aibl/template.json`', MARKER)

    def test_rule_2_allows_the_marker_and_nothing_more(self):
        self.assertIn('plus `.aibl/template.json` in step 1\'s "Add the marker first", only when it is missing and only '
                      "after the student's yes", RULES)

    def test_student_facing_lines_carry_no_shell_commands(self):
        found = re.findall(r'[Ss]ay: "([^"]*)"|^> "(.*)"$', MARKER, flags=re.M)
        said = [a or b for a, b in found]
        self.assertGreaterEqual(len(said), 4)
        for line in said:
            self.assertNotRegex(line, r'`(git|gh|node|python3?|py) ')


TEMPLATE_SKILLS = ('aibl-enroll', 'aibl-checkpoint', 'aibl-personalize')


def folder_case(top, is_git):
    """Step 1's cases for a folder, in the prompt's order, before origin is looked at. top is the folder on disk."""
    if (top / '.aibl' / 'template.json').is_file():
        return 'marked'
    claude = top / 'CLAUDE.md'
    if (top / '.aibl' / 'installed-agent-essentials.json').is_file() or (
            claude.is_file() and '/aibl-teach' in claude.read_text(encoding='utf-8')):
        return 'A workbench from the retired course.'
    notes = claude.is_file() or (top / 'AGENTS.md').is_file()
    skills = any((top / root / name).is_dir() for root in ('.claude/skills', '.agents/skills') for name in TEMPLATE_SKILLS)
    shape = [is_git, notes, (top / 'context').is_dir(), skills]
    if all(shape):
        return 'An older workbench, missing its marker.'
    if top.name == 'my-workbench' or any(shape[1:]):
        return 'Not a workbench (say what is missing).'
    return 'Not a workbench (wrong folder).'


@unittest.skipUnless(shutil.which('git'), 'git not available')
class OlderWorkbenchWithRealGit(unittest.TestCase):
    """The shape check and the marker commands, run as the student's agent would."""

    MARKER_BYTES = ('{\n  "schema_version": "aibl.workbench-template/v1",\n'
                    '  "repository": "aibuild-lab/my-workbench-template",\n  "version": "0.0.12"\n}\n')

    def git(self, *args, cwd, check=True):
        result = subprocess.run(['git', '-c', 'core.autocrlf=false', *args], cwd=cwd, check=False,
                                capture_output=True, text=True)
        if check and result.returncode:
            raise AssertionError(result.stderr)
        return result

    def repo(self, name, files, commit=True):
        path = self.tmp / name
        path.mkdir(parents=True)
        self.git('init', '-q', '-b', 'main', cwd=path)
        self.git('config', 'user.email', 'test@example.invalid', cwd=path)
        self.git('config', 'user.name', 'test', cwd=path)
        for rel, body in files.items():
            target = path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body.encode('utf-8'))
        if commit:
            self.git('add', '-A', cwd=path)
            self.git('commit', '-q', '-m', 'Day one: the workbench starter', cwd=path)
        return path

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.template = self.repo('template', {'.aibl/template.json': self.MARKER_BYTES, 'CLAUDE.md': 'template\n'})

    def early(self, name='my-workbench', commit=True, extra=None):
        files = {'CLAUDE.md': 'notes\n', 'AGENTS.md': 'notes\n', 'context/README.md': 'me\n',
                 '.claude/skills/aibl-checkpoint/SKILL.md': 'early\n', '.claude/skills/aibl-personalize/SKILL.md': 'early\n'}
        files.update(extra or {})
        return self.repo(name, files, commit=commit)

    def add_marker(self, wb):
        """Add the marker first, after the yes: step 2's two commands, then the three numbered steps."""
        self.git('remote', 'add', 'template', self.template.as_uri(), cwd=wb)
        self.git('fetch', '-q', 'template', 'main', cwd=wb)
        shown = self.git('show', 'template/main:.aibl/template.json', cwd=wb).stdout
        self.assertIn('"schema_version": "aibl.workbench-template/v1"', shown)
        self.git('checkout', 'template/main', '--', '.aibl/template.json', cwd=wb)
        self.git('commit', '-q', '-m', 'Add the workbench marker file', '--', '.aibl/template.json', cwd=wb)
        self.assertEqual(self.git('diff', '--quiet', 'HEAD', 'template/main', '--', '.aibl/template.json', cwd=wb,
                                  check=False).returncode, 0)

    def test_an_early_workbench_has_the_older_shape(self):
        self.assertEqual(folder_case(self.early(), True), 'An older workbench, missing its marker.')

    def test_codex_skills_alone_count(self):
        wb = self.repo('codex-only', {'AGENTS.md': 'notes\n', 'context/README.md': 'me\n',
                                      '.agents/skills/aibl-enroll/SKILL.md': 'early\n'})
        self.assertEqual(folder_case(wb, True), 'An older workbench, missing its marker.')

    def test_the_retired_course_is_not_an_older_workbench(self):
        wb = self.early(extra={'.aibl/installed-agent-essentials.json': '{}\n'})
        self.assertEqual(folder_case(wb, True), 'A workbench from the retired course.')
        wb = self.early(name='teach', extra={'CLAUDE.md': 'Start with /aibl-teach\n'})
        self.assertEqual(folder_case(wb, True), 'A workbench from the retired course.')

    def test_a_partial_shape_in_my_workbench_says_what_is_missing(self):
        wb = self.repo('my-workbench', {'CLAUDE.md': 'notes\n', '.claude/skills/aibl-checkpoint/SKILL.md': 'x\n'})
        self.assertEqual(folder_case(wb, True), 'Not a workbench (say what is missing).')
        plain = self.tmp / 'nested' / 'my-workbench'
        plain.mkdir(parents=True)
        self.assertEqual(folder_case(plain, False), 'Not a workbench (say what is missing).')

    def test_an_unrelated_folder_is_the_wrong_folder(self):
        other = self.tmp / 'Documents'
        other.mkdir()
        self.assertEqual(folder_case(other, False), 'Not a workbench (wrong folder).')

    def test_the_marker_is_the_template_file_and_the_only_commit(self):
        wb = self.early()
        (wb / 'context' / 'README.md').write_bytes(b'me, half written\n')
        (wb / 'work').mkdir()
        (wb / 'work' / 'draft.md').write_bytes(b'unsaved\n')
        before = self.git('rev-parse', 'HEAD', cwd=wb).stdout.strip()
        self.add_marker(wb)
        self.assertEqual((wb / '.aibl' / 'template.json').read_bytes(), self.MARKER_BYTES.encode('utf-8'))
        self.assertEqual(self.git('diff', '--name-only', before, 'HEAD', cwd=wb).stdout.split(), ['.aibl/template.json'])
        status = self.git('status', '--short', cwd=wb).stdout
        self.assertIn(' M context/README.md', status)
        self.assertIn('?? work/', status)
        self.assertEqual(folder_case(wb, True), 'marked')
        # No origin, so the next pass of step 1 reaches "not connected to GitHub yet".
        self.assertNotEqual(self.git('remote', 'get-url', 'origin', cwd=wb, check=False).returncode, 0)

    def test_a_workbench_with_no_snapshot_yet_gets_the_marker_as_its_first(self):
        wb = self.early(name='unborn', commit=False)
        self.add_marker(wb)
        self.assertEqual(self.git('ls-tree', '-r', '--name-only', 'HEAD', cwd=wb).stdout.split(), ['.aibl/template.json'])
        self.assertIn('?? CLAUDE.md', self.git('status', '--short', cwd=wb).stdout)


class ConnectStep(unittest.TestCase):
    def test_asks_before_creating_anything(self):
        ask = CONNECT.index('OK?"')
        self.assertLess(ask, CONNECT.index('gh repo create'))
        self.assertIn('On a no, continue the update without connecting', CONNECT)

    def test_creates_a_private_repository_from_this_folder(self):
        self.assertIn('gh repo create <login>/<name> --private --source . --remote origin --push', CONNECT)
        self.assertIn('--jq .visibility` prints `PRIVATE`', CONNECT)

    def test_never_connects_to_an_existing_repository(self):
        check = CONNECT.index('gh repo view <login>/<name> --json name')
        self.assertLess(check, CONNECT.index('gh repo create'))
        self.assertIn('do not connect to it and do not push', CONNECT)

    def test_keeps_the_template_remote_and_needs_a_snapshot(self):
        self.assertIn('git remote rename origin template', CONNECT)
        self.assertIn('git rev-parse --verify HEAD', CONNECT)

    def test_the_agent_runs_every_command(self):
        self.assertIn('run each of these yourself', CONNECT)
        self.assertIn('Never hand the student a command.', RULES)
        self.assertNotRegex(FLAT, r'(?i)(ask|tell|have) the student to (type|run|paste|open (terminal|powershell))')

    def test_rule_4_allows_only_the_approved_connect_push(self):
        self.assertIn('Never push anywhere except `origin`', RULES)
        self.assertIn('only after their yes', RULES)

    def test_student_facing_lines_carry_no_shell_commands(self):
        quotes = re.findall(r'Say: "([^"]*)"|^> "(.*)"$', STEP1, flags=re.M)
        said = [a or b for a, b in quotes]
        self.assertGreaterEqual(len(said), 5)
        for line in said:
            self.assertNotRegex(line, r'`(git|gh|node|python3?|py) ')


class SettingsHook(unittest.TestCase):
    def test_existing_settings_are_read_for_the_update_check_hook(self):
        self.assertIn('hooks.SessionStart', STEP2)
        self.assertIn('.claude/hooks/update-check.mjs', STEP2)
        self.assertIn('leave them unchanged', STEP2)

    def test_missing_hook_entry_is_offered_only_as_a_previewed_yes(self):
        self.assertIn('offers to add just that entry, shown as a diff first and only on a yes', STEP2)


FLAT2 = re.sub(r'\s+', ' ', STEP2)
HEAD_ID = '`git rev-parse --verify --quiet HEAD:<path>`'
SHALLOW = '`git rev-parse --is-shallow-repository`'
HISTORY = '`git rev-list --first-parent template/main -- <path>`'
SHIPPED_ID = '`git rev-parse --verify --quiet <commit>:<path>`'


def case(label):
    match = re.search(r'^\s+- \*\*' + re.escape(label) + r'\*\*(.*)$', STEP2, flags=re.M)
    if not match:
        raise AssertionError('missing step 2 case: ' + label)
    return match.group(1)


class UneditedCopiesGetARecommendation(unittest.TestCase):
    def test_the_history_check_uses_exact_git_ids(self):
        for command in (HEAD_ID, SHALLOW, HISTORY, SHIPPED_ID):
            with self.subTest(command=command):
                self.assertIn(command, STEP2)
        self.assertIn('never by guessing', STEP2)
        self.assertIn('two equal ids mean two identical copies', FLAT2)
        self.assertIn("a folder's covers every name, mode and byte inside it", FLAT2)

    def test_every_case_is_named_once(self):
        for label in ('Unedited.', 'New here.', 'Changed.', "Can't tell."):
            with self.subTest(label=label):
                self.assertEqual(STEP2.count('**' + label + '**'), 1)
                case(label)

    def test_an_unedited_copy_is_recommended_with_a_plain_reason(self):
        unedited = case('Unedited.')
        self.assertIn('equals one of those template ids', unedited)
        self.assertIn('Recommend taking the template version', unedited)
        self.assertIn("You haven't changed this skill, so the new version is safe to take.", unedited)
        self.assertIn('say "file" for the hook file', unedited)
        self.assertIn('Recommend taking the template version', case('New here.'))
        self.assertIn('replaces nothing', case('New here.'))

    def test_new_here_needs_the_path_missing_on_disk_too(self):
        new = case('New here.')
        self.assertIn('the folder or file is not on disk either', new)
        self.assertIn("If `HEAD:<path>` fails but the path is on disk, this is not New here; use Can't tell.", new)
        self.assertIn('`HEAD:<path>` failed while the path is on disk', case("Can't tell."))
        self.assertIn('Write `<path>` with forward slashes on every system', STEP2)

    def test_a_student_edit_gets_no_recommendation(self):
        changed = case('Changed.')
        self.assertIn('matches none of them', changed)
        self.assertIn('Recommend nothing.', changed)
        self.assertIn('would replace them', changed)
        self.assertNotIn('Recommend taking', changed)

    def test_an_unreadable_history_falls_back_to_the_plain_question(self):
        cant = case("Can't tell.")
        for trigger in ('the shallow check or the history list failed', 'the repository is shallow', 'the list is empty',
                        'no shipped id could be read'):
            self.assertIn(trigger, cant)
        self.assertIn('no recommendation', cant)
        self.assertIn('say nothing about who changed the file', cant)
        self.assertIn('The shallow check printed `false`, the history list worked and has at least one commit, '
                      'at least one shipped id was read', case('Changed.'))
        self.assertIn('Use the first case that fits, in this order.', STEP2)

    def test_a_short_summary_comes_before_any_raw_diff(self):
        self.assertIn('in one or two plain lines, what the template version changes', FLAT2)
        self.assertIn('Do not show the raw diff unless they ask for it', FLAT2)
        self.assertNotIn('show `git diff HEAD template/main -- <path>` and ask', FLAT2)

    def test_the_student_still_chooses_every_path(self):
        self.assertIn('Ask once per path.', FLAT2)
        self.assertIn('"Take the template version (recommended), or keep yours?', FLAT2)
        self.assertIn('"Keep your version, or take the template version?', FLAT2)
        self.assertIn('nothing is overwritten without their answer', FLAT2)
        checkout = FLAT2.index('after they choose the template version, run `git checkout template/main -- <path>`')
        self.assertLess(FLAT2.index('Ask once per path.'), checkout)

    def test_student_facing_lines_carry_no_shell_commands(self):
        said = re.findall(r'"([^"]*)"', STEP2.split('1. **Read the ids.**', 1)[1].split('Skip a path', 1)[0])
        self.assertGreaterEqual(len(said), 6)
        for line in said:
            self.assertNotRegex(line, r'`(git|gh|node|python3?|py) ')


def decide(head_id, on_disk, shallow, commits, shipped):
    """Step 2's four cases, first fit wins, in the prompt's order. None means that command failed."""
    if head_id is not None and head_id in shipped:
        return 'Unedited.'
    if head_id is None and not on_disk:
        return 'New here.'
    if head_id is not None and shallow == 'false' and commits and shipped:
        return 'Changed.'
    return "Can't tell."


class CaseOrder(unittest.TestCase):
    """The first-fit rules on their own, including failures a real repository rarely produces."""

    def test_a_match_wins_even_on_a_shallow_repository(self):
        self.assertEqual(decide('a', True, 'true', ['c1'], {'a'}), 'Unedited.')

    def test_no_shipped_id_read_cannot_claim_a_student_edit(self):
        self.assertEqual(decide('a', True, 'false', ['c1', 'c2'], set()), "Can't tell.")

    def test_a_failed_head_read_with_the_path_on_disk_is_not_new_here(self):
        self.assertEqual(decide(None, True, 'false', ['c1'], {'b'}), "Can't tell.")

    def test_a_failed_shallow_check_cannot_claim_a_student_edit(self):
        self.assertEqual(decide('a', True, None, ['c1'], {'b'}), "Can't tell.")
        self.assertEqual(decide('a', True, 'false', None, set()), "Can't tell.")


@unittest.skipUnless(shutil.which('git'), 'git not available')
class HistoryCheckWithRealGit(unittest.TestCase):
    """Runs the prompt's commands, as the student's agent would, on a template with real history."""

    SKILL = '.claude/skills/aibl-enroll'
    HOOK = '.claude/hooks/update-check.mjs'
    UPDATE = '.claude/skills/aibl-update'

    def git(self, *args, cwd, check=True):
        result = subprocess.run(['git', '-c', 'core.autocrlf=false', *args], cwd=cwd, check=False,
                                capture_output=True, text=True)
        if check and result.returncode:
            raise AssertionError(result.stderr)
        return result

    def repo(self, name):
        path = self.tmp / name
        path.mkdir()
        self.git('init', '-q', '-b', 'main', cwd=path)
        self.git('config', 'user.email', 'test@example.invalid', cwd=path)
        self.git('config', 'user.name', 'test', cwd=path)
        return path

    def write(self, repo, files):
        for rel, body in files.items():
            target = repo / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body.encode('utf-8'))

    def commit(self, repo, files, message):
        self.write(repo, files)
        self.git('add', '-A', cwd=repo)
        self.git('commit', '-q', '-m', message, cwd=repo)

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        t = self.template = self.repo('template')
        self.commit(t, {self.SKILL + '/SKILL.md': 'v1\n', self.HOOK: 'h1\n'}, 'first')
        self.commit(t, {self.SKILL + '/SKILL.md': 'v2\n'}, 'second')
        self.git('checkout', '-q', '-b', 'pr', cwd=t)
        self.commit(t, {self.SKILL + '/SKILL.md': 'draft never shipped\n'}, 'draft')
        self.commit(t, {self.SKILL + '/SKILL.md': 'v3\n'}, 'ready')
        self.git('checkout', '-q', 'main', cwd=t)
        self.git('merge', '-q', '--no-ff', '-m', 'Merge pull request', 'pr', cwd=t)
        self.commit(t, {self.HOOK: 'h2\n', self.UPDATE + '/SKILL.md': 'u1\n'}, 'third')

    def workbench(self, files, name='workbench'):
        wb = self.repo(name)
        self.commit(wb, {'README.md': 'mine\n', **files}, 'Initial commit')
        self.git('remote', 'add', 'template', self.template.as_uri(), cwd=wb)
        self.git('fetch', '-q', 'template', 'main', cwd=wb)
        return wb

    def classify(self, wb, path, read_path=None):
        """Step 2's commands, as the agent runs them. read_path is the spelling the agent typed, if different."""
        spelled = read_path or path
        head = self.git('rev-parse', '--verify', '--quiet', 'HEAD:' + spelled, cwd=wb, check=False)
        shallow = self.git('rev-parse', '--is-shallow-repository', cwd=wb, check=False)
        listed = self.git('rev-list', '--first-parent', 'template/main', '--', spelled, cwd=wb, check=False)
        commits = listed.stdout.split() if listed.returncode == 0 else []
        shipped = set()
        for commit in commits:
            found = self.git('rev-parse', '--verify', '--quiet', commit + ':' + spelled, cwd=wb, check=False)
            if found.returncode == 0:
                shipped.add(found.stdout.strip())
        return decide(head_id=head.stdout.strip() if head.returncode == 0 else None,
                      on_disk=(wb / path).exists(),
                      shallow=shallow.stdout.strip() if shallow.returncode == 0 else None,
                      commits=commits if listed.returncode == 0 else None,
                      shipped=shipped)

    def test_prompt_names_the_commands_this_test_runs(self):
        for command in (HEAD_ID, SHALLOW, HISTORY, SHIPPED_ID):
            self.assertIn(command, STEP2)

    def test_an_older_stock_copy_is_unedited(self):
        wb = self.workbench({self.SKILL + '/SKILL.md': 'v2\n', self.HOOK: 'h1\n'})
        self.assertTrue(self.git('diff', '--quiet', 'HEAD', 'template/main', '--', self.SKILL, cwd=wb, check=False).returncode)
        self.assertEqual(self.classify(wb, self.SKILL), 'Unedited.')
        self.assertEqual(self.classify(wb, self.HOOK), 'Unedited.')

    def test_the_first_shipped_version_counts(self):
        wb = self.workbench({self.SKILL + '/SKILL.md': 'v1\n'})
        self.assertEqual(self.classify(wb, self.SKILL), 'Unedited.')

    def test_a_student_edit_is_changed(self):
        wb = self.workbench({self.SKILL + '/SKILL.md': 'v2\nmy own note\n', self.HOOK: 'h1 \n'})
        self.assertEqual(self.classify(wb, self.SKILL), 'Changed.')
        self.assertEqual(self.classify(wb, self.HOOK), 'Changed.')

    def test_an_extra_file_in_a_stock_folder_is_changed(self):
        wb = self.workbench({self.SKILL + '/SKILL.md': 'v2\n', self.SKILL + '/notes.md': 'mine\n'})
        self.assertEqual(self.classify(wb, self.SKILL), 'Changed.')

    def test_a_version_that_only_lived_on_a_pull_request_branch_never_shipped(self):
        wb = self.workbench({self.SKILL + '/SKILL.md': 'draft never shipped\n'})
        self.assertEqual(self.classify(wb, self.SKILL), 'Changed.')

    def test_a_missing_copy_is_new_here(self):
        wb = self.workbench({self.SKILL + '/SKILL.md': 'v2\n'})
        self.assertEqual(self.classify(wb, self.UPDATE), 'New here.')

    def test_a_shallow_workbench_cannot_claim_a_student_edit(self):
        source = self.workbench({self.SKILL + '/SKILL.md': 'v2\nmy own note\n', self.HOOK: 'h1\n'}, 'source')
        self.commit(source, {'README.md': 'mine, later\n'}, 'Later work')
        wb = self.tmp / 'shallow'
        self.git('clone', '-q', '--depth', '1', source.as_uri(), str(wb), cwd=self.tmp)
        self.git('remote', 'add', 'template', self.template.as_uri(), cwd=wb)
        self.git('fetch', '-q', 'template', 'main', cwd=wb)
        self.assertEqual(self.git('rev-parse', '--is-shallow-repository', cwd=wb).stdout.strip(), 'true')
        self.assertEqual(self.classify(wb, self.SKILL), "Can't tell.")
        self.assertEqual(self.classify(wb, self.HOOK), 'Unedited.')

    def test_a_backslash_spelling_of_an_edited_copy_is_not_new_here(self):
        wb = self.workbench({self.SKILL + '/SKILL.md': 'v2\nmy own note\n'})
        self.assertEqual(self.classify(wb, self.SKILL, read_path=self.SKILL.replace('/', '\\')), "Can't tell.")
        self.assertEqual(self.classify(wb, self.SKILL), 'Changed.')

    def test_a_shallow_template_fetch_cannot_claim_a_student_edit(self):
        wb = self.repo('shallow-fetch')
        self.commit(wb, {self.SKILL + '/SKILL.md': 'v2\n'}, 'Initial commit')
        self.git('remote', 'add', 'template', self.template.as_uri(), cwd=wb)
        self.git('fetch', '-q', '--depth', '1', 'template', 'main', cwd=wb)
        self.assertEqual(self.git('rev-parse', '--is-shallow-repository', cwd=wb).stdout.strip(), 'true')
        self.assertEqual(self.classify(wb, self.SKILL), "Can't tell.")

    def test_a_mode_change_inside_a_folder_is_changed(self):
        wb = self.workbench({self.SKILL + '/SKILL.md': 'v2\n', self.HOOK: 'h1\n'})
        self.git('update-index', '--chmod=+x', self.SKILL + '/SKILL.md', cwd=wb)
        self.git('update-index', '--chmod=+x', self.HOOK, cwd=wb)
        self.git('commit', '-q', '-m', 'make them executable', cwd=wb)
        self.assertEqual(self.classify(wb, self.SKILL), 'Changed.')
        # A file's id is its bytes alone: same bytes, so still a shipped copy.
        self.assertEqual(self.classify(wb, self.HOOK), 'Unedited.')

    def test_no_template_history_means_cant_tell(self):
        wb = self.repo('no-template')
        self.commit(wb, {self.SKILL + '/SKILL.md': 'v2\n'}, 'Initial commit')
        self.assertEqual(self.classify(wb, self.SKILL), "Can't tell.")


class NoEmDashes(unittest.TestCase):
    def test_prompt_has_no_em_dashes(self):
        self.assertNotIn('—', TEXT)


if __name__ == '__main__':
    unittest.main()
