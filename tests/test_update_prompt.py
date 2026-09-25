"""UPDATE-PROMPT.md step 1 contract: a workbench without a GitHub connection is not "the wrong folder".

A live run told a student "This session is not open on your workbench" for their real workbench, because the
old step 1 treated a failed `git remote get-url origin` as the wrong folder. These tests pin the classification,
the connect step's safety checks, and the settings hook guidance. They read the prompt; they do not run an app.
"""
import pathlib
import re
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


class NoEmDashes(unittest.TestCase):
    def test_prompt_has_no_em_dashes(self):
        self.assertNotIn('—', TEXT)


if __name__ == '__main__':
    unittest.main()
