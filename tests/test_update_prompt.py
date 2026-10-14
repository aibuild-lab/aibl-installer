"""UPDATE-PROMPT.md step 1 and step 2 contract.

Step 1: a workbench without a GitHub connection is not "the wrong folder". A live run told a student "This
session is not open on your workbench" for their real workbench, because the old step 1 treated a failed
`git remote get-url origin` as the wrong folder. These tests pin the classification, the connect step's safety
checks, and the settings hook guidance.

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
        for case in ('Your workbench, not connected to GitHub yet.', 'A workbench with no save history.'):
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
        for case in ('Not a workbench.', 'A workbench with no save history.', 'Your workbench, not connected to GitHub yet.',
                     "Your workbench, connected to someone else's repository.", 'Your workbench, connected.'):
            with self.subTest(case=case):
                bullet(case)


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

    def test_every_case_is_named_once(self):
        for label in ('Unedited.', 'New here.', 'Changed.', "Can't tell."):
            with self.subTest(label=label):
                self.assertEqual(STEP2.count('**' + label + '**'), 1)
                case(label)

    def test_an_unedited_copy_is_recommended_with_a_plain_reason(self):
        unedited = case('Unedited.')
        self.assertIn('equals one of those template ids', unedited)
        self.assertIn('Recommend taking the template version', unedited)
        self.assertIn("You haven't changed this file, so the new version is safe to take.", unedited)
        self.assertIn('Recommend taking the template version', case('New here.'))
        self.assertIn('replaces nothing', case('New here.'))

    def test_a_student_edit_gets_no_recommendation(self):
        changed = case('Changed.')
        self.assertIn('matches none of them', changed)
        self.assertIn('Recommend nothing.', changed)
        self.assertIn('would replace them', changed)
        self.assertNotIn('Recommend taking', changed)

    def test_an_unreadable_history_falls_back_to_the_plain_question(self):
        cant = case("Can't tell.")
        for trigger in ('the shallow check or the history list failed', 'the repository is shallow', 'the list is empty'):
            self.assertIn(trigger, cant)
        self.assertIn('no recommendation', cant)
        self.assertIn('say nothing about who changed the file', cant)
        self.assertIn('The shallow check printed `false`, the history list worked and has at least one commit', case('Changed.'))
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

    def classify(self, wb, path):
        """Step 2's commands and its four cases, first fit wins, in the prompt's order."""
        head = self.git('rev-parse', '--verify', '--quiet', 'HEAD:' + path, cwd=wb, check=False)
        shallow = self.git('rev-parse', '--is-shallow-repository', cwd=wb, check=False)
        listed = self.git('rev-list', '--first-parent', 'template/main', '--', path, cwd=wb, check=False)
        commits = listed.stdout.split() if listed.returncode == 0 else []
        shipped = set()
        for commit in commits:
            found = self.git('rev-parse', '--verify', '--quiet', commit + ':' + path, cwd=wb, check=False)
            if found.returncode == 0:
                shipped.add(found.stdout.strip())
        if head.returncode == 0 and head.stdout.strip() in shipped:
            return 'Unedited.'
        if head.returncode:
            return 'New here.'
        if shallow.returncode == 0 and shallow.stdout.strip() == 'false' and commits:
            return 'Changed.'
        return "Can't tell."

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

    def test_no_template_history_means_cant_tell(self):
        wb = self.repo('no-template')
        self.commit(wb, {self.SKILL + '/SKILL.md': 'v2\n'}, 'Initial commit')
        self.assertEqual(self.classify(wb, self.SKILL), "Can't tell.")


class NoEmDashes(unittest.TestCase):
    def test_prompt_has_no_em_dashes(self):
        self.assertNotIn('—', TEXT)


if __name__ == '__main__':
    unittest.main()
