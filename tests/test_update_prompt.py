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
CONNECT = section('### Connect it first', '### Unsaved work')
UNSAVED = section('### Unsaved work', '## Step 2:')
RULES = section('## Rules', '## Step 1:')
STEP2 = section('## Step 2:', '## Step 2.5:')
GUARD = section('## Step 2.5:', '## Step 3:')
STEP3 = section('## Step 3:', '## Step 4:')
REPORT = TEXT.split('## Step 4:', 1)[1]


def flat(text):
    return re.sub(r'\s+', ' ', text)


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


class UnsavedWork(unittest.TestCase):
    """Decision 40 (WF-6): mid-course lesson output no longer stops the update."""

    def test_offers_to_save_and_continue_in_the_decided_words(self):
        self.assertIn('Save it now and continue the update? (yes / no)', UNSAVED)
        self.assertIn('You have unsaved lesson work', UNSAVED)
        self.assertIn('1. Yes, save it and continue (recommended)', UNSAVED)
        self.assertIn('`aibl-checkpoint`', UNSAVED)

    def test_the_old_stop_and_paste_again_is_gone(self):
        self.assertNotIn('then paste the prompt again." Stop.', TEXT)

    def test_stops_only_for_the_course_folders_it_writes_or_staged_changes(self):
        f = flat(UNSAVED)
        for path in ('.claude/skills/aibl-*', '.agents/skills/aibl-*', '.claude/hooks/update-check.mjs', '.claude/settings.json'):
            self.assertIn(path, UNSAVED)
        self.assertIn('git diff --cached --name-only', UNSAVED)
        self.assertIn('lesson output (`runs/`, `work-orders/`, `work/`)', f)
        self.assertIn('No, stop the update for now', f)
        self.assertIn('Your unsaved files stay exactly as they are.', f)
        self.assertIn('Never stash, reset or discard', f)

    def test_rule_five_matches(self):
        f = flat(RULES)
        self.assertIn('can stay unsaved: the update never touches it', f)
        self.assertNotIn('If the working tree is not clean, stop and ask the student to save first.', f)

    def test_rules_are_numbered_in_order(self):
        numbers = [int(n) for n in re.findall(r'^(\d+)\. \*\*', RULES, flags=re.M)]
        self.assertEqual(numbers, list(range(1, len(numbers) + 1)))

    def test_the_core_save_commits_only_its_own_paths(self):
        self.assertIn('git commit -m "Update workbench skills from the template" -- <the approved paths>', STEP2)

    def test_program_update_does_not_ask_twice(self):
        self.assertIn('do not ask again', STEP3)


class AutoModeMessage(unittest.TestCase):
    """Decision 42 (WF-7, WF-56): say what the app may stop, and how to continue, before the step."""

    def test_names_both_apps_modes_and_buttons(self):
        f = flat(RULES)
        for words in ('**Auto** to **Accept edits**', '**Allow once**', 'Switch back to **Auto**',
                      '**Approve for me** to **Ask for approval**', '**Approve**', 'prompt injection',
                      "**That's a good thing:**", 'Only continue for sources you trust.',
                      "This one is the course's own installer, from AI Build Lab."):
            with self.subTest(words=words):
                self.assertIn(words, f)

    def test_the_save_has_its_own_reply(self):
        self.assertIn("reply: 'Yes, save the course update now.'", flat(RULES))

    def test_said_before_the_steps_it_covers(self):
        self.assertLess(STEP2.index("rule 7's message for the save"), STEP2.index('git commit -m'))
        self.assertLess(GUARD.index("rule 7's message for a course script"), GUARD.index('refresh-guard.mjs --check'))

    def test_still_never_hands_out_a_command(self):
        self.assertIn('never hand them the command instead', flat(RULES))


class SecretsGuardRefresh(unittest.TestCase):
    """Decision 41 (WF-8): the update offers to refresh a stale guard, ask-first, with the existing tool."""

    def test_rule_three_allows_only_the_two_course_add_ons_on_a_yes(self):
        f = flat(RULES)
        self.assertIn("refresh the course's own two add-ons that are already on this computer", f)
        self.assertIn('the secrets guard (step 2.5) and the Langfuse recorder (`aibl-update`)', f)
        self.assertIn("only on the student's yes", f)
        self.assertIn('never runs the full setup, never installs a tool or a missing add-on, and never asks for a password', f)

    def test_installer_copy_refreshed_before_the_check(self):
        self.assertLess(GUARD.index('pull --ff-only origin main'), GUARD.index('refresh-guard.mjs --check'))
        self.assertIn('never reset, move or delete it', GUARD)

    def test_checks_first_asks_once_then_refreshes(self):
        check = GUARD.index('refresh-guard.mjs --check --<app>')
        ask = GUARD.index('Refresh it? (yes / no)')
        refresh = GUARD.index('refresh-guard.mjs --<app>` for each app')
        self.assertLess(check, ask)
        self.assertLess(ask, refresh)
        self.assertIn('A course add-on on this computer is older than the course\'s version: your secrets guard.', GUARD)

    def test_never_adds_a_guard_that_is_not_there(self):
        f = flat(GUARD)
        self.assertIn('Never add a guard to an app that has none here', f)
        self.assertIn('~/.codex/hooks/codex-secrets-guard.mjs', GUARD)

    def test_failure_and_rollback_are_told_plainly(self):
        self.assertIn('restored the previous version', GUARD)
        self.assertIn('your previous guard is back in place', GUARD)

    def test_codex_retrust_line(self):
        self.assertIn("Choose 'Trust all and continue'", GUARD)
        self.assertIn("Never choose 'Continue without trusting'", GUARD)

    def test_report_says_to_restart_after_a_refresh(self):
        self.assertIn('fully quit the app and open it again', REPORT)


class StudentFacingQuotes(unittest.TestCase):
    def test_no_shell_commands_in_anything_said_to_the_student(self):
        said = re.findall(r'^\s*> "?(.*)$', TEXT, flags=re.M) + re.findall(r'[Ss]ay:? "([^"]*)"', TEXT)
        self.assertGreaterEqual(len(said), 12)
        for line in said:
            self.assertNotRegex(line, r'`(git|gh|node|python3?|py) ')


class NoEmDashes(unittest.TestCase):
    def test_prompt_has_no_em_dashes(self):
        self.assertNotIn('—', TEXT)


if __name__ == '__main__':
    unittest.main()
