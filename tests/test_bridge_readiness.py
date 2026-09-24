"""Bridge readiness (SETUP-PROMPT step 8.5). Synthetic machines only: no Homebrew, no sign-in, no real settings."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import bridge_readiness as br

TEAMS = br.TEAMS_KEY
SUBSCRIPTION = {'loggedIn': True, 'authMethod': 'claude.ai', 'apiProvider': 'firstParty',
                'email': 'student@example.com', 'orgName': 'Synthetic Org'}
STUDENT_SETTINGS = {
    'model': 'opus',
    'env': {'FOO': 'bar'},
    'hooks': {'PreToolUse': [{'matcher': 'Bash', 'hooks': [{'type': 'command', 'command': 'node secrets-guard.js'}]}]},
    'permissions': {'allow': ['Bash(ls)'], 'deny': ['WebFetch']},
    'statusLine': {'type': 'command', 'command': 'echo hi'},
}


class FakeMachine:
    """Builds a br.Machine over a temp home with scripted tools and scripted command results."""

    def __init__(self, test, system='mac', tools=('tmux', 'brew', 'claude', 'zsh'), auth=SUBSCRIPTION, auth_raw=None,
                 brew_exit=0):
        self.test = test
        self.dir = tempfile.TemporaryDirectory()
        test.addCleanup(self.dir.cleanup)
        self.home = Path(self.dir.name).resolve()
        self.workbench = self.home / 'GitHub' / 'my-workbench'
        (self.workbench / '.claude').mkdir(parents=True)
        self.tools = set(tools)
        self.auth = auth
        self.auth_raw = auth_raw
        self.brew_exit = brew_exit
        self.calls = []
        self.machine = br.Machine(home=self.home, system=system, workbench=self.workbench,
                                  which=self.which, run=self.run, env={}, is_file=self.is_file)

    def is_file(self, path):
        # Only files inside the synthetic home exist; the real /opt/homebrew and /usr/local are never consulted.
        path = Path(path)
        return self.home in path.parents and path.is_file()

    def which(self, name):
        return f'/synthetic/bin/{name}' if name in self.tools else None

    def run(self, args, timeout=None):
        self.calls.append(list(args))
        if args[-1] == 'claude auth status --json' or args[1:] == ['auth', 'status', '--json']:
            if self.auth_raw is not None:
                return subprocess.CompletedProcess(args, 0, self.auth_raw, '')
            if self.auth is None:
                return subprocess.CompletedProcess(args, 127, '', 'zsh: command not found: claude')
            return subprocess.CompletedProcess(args, 0 if self.auth.get('loggedIn') else 1, json.dumps(self.auth), '')
        if args[1:] == ['install', 'tmux']:
            if not self.brew_exit:
                self.tools.add('tmux')
            return subprocess.CompletedProcess(args, self.brew_exit, '', '' if not self.brew_exit else 'Error: synthetic brew failure')
        raise AssertionError('Unexpected command ' + repr(args))

    @property
    def settings(self):
        return self.machine.user_settings

    def write_settings(self, data, raw=None):
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.settings.write_text(raw if raw is not None else json.dumps(data, indent=2) + '\n', encoding='utf-8')

    def backups(self, folder=None):
        folder = folder or self.settings.parent
        return sorted(p for p in folder.iterdir() if br.BACKUP_TAG in p.name)

    def brew_installs(self):
        return [c for c in self.calls if c[1:] == ['install', 'tmux']]


def quiet_main(argv, machine):
    with contextlib.redirect_stdout(io.StringIO()):
        return br.main(argv, machine=machine)


def by_item(report):
    return {i['item']: i for i in report['items']}


class SettingsMerge(unittest.TestCase):
    def test_existing_keys_are_preserved(self):
        fake = FakeMachine(self)
        fake.write_settings(STUDENT_SETTINGS)
        report = br.apply(fake.machine, yes=True)
        after = json.loads(fake.settings.read_text())
        for key, value in STUDENT_SETTINGS.items():
            if key != 'env':
                self.assertEqual(after[key], value, key)
        self.assertEqual(after['env'], {'FOO': 'bar', TEAMS: '1'})
        self.assertEqual(list(after), list(STUDENT_SETTINGS), 'top-level key order is kept')
        self.assertTrue(report['ready'])

    def test_backup_holds_the_original_bytes(self):
        fake = FakeMachine(self)
        raw = json.dumps(STUDENT_SETTINGS) + '\n'
        fake.write_settings(None, raw=raw)
        report = br.apply(fake.machine, yes=True)
        backups = fake.backups()
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), raw)
        self.assertEqual(report['backups'], [str(backups[0])])
        if os.name != 'nt':
            self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)

    def test_file_mode_is_kept(self):
        if os.name == 'nt':
            self.skipTest('POSIX file modes')
        fake = FakeMachine(self)
        fake.write_settings(STUDENT_SETTINGS)
        os.chmod(fake.settings, 0o600)
        br.apply(fake.machine, yes=True)
        self.assertEqual(fake.settings.stat().st_mode & 0o777, 0o600)

    def test_missing_settings_file_is_created_with_only_the_flag(self):
        fake = FakeMachine(self)
        report = br.apply(fake.machine, yes=True)
        self.assertEqual(json.loads(fake.settings.read_text()), {'env': {TEAMS: '1'}})
        self.assertEqual(report['backups'], [])

    def test_a_different_value_is_corrected_and_reported(self):
        fake = FakeMachine(self)
        fake.write_settings({'env': {TEAMS: '0'}})
        report = br.apply(fake.machine, yes=True)
        self.assertEqual(json.loads(fake.settings.read_text())['env'][TEAMS], '1')
        self.assertTrue(any('it was "0"' in c for c in report['changed']))

    def test_invalid_json_is_never_touched(self):
        fake = FakeMachine(self)
        raw = '{"env": {"FOO": "bar",}\n'
        fake.write_settings(None, raw=raw)
        report = br.apply(fake.machine, yes=True)
        self.assertEqual(fake.settings.read_text(), raw)
        self.assertEqual(fake.backups(), [])
        teams = by_item(report)['agent teams']
        self.assertFalse(teams['pass'])
        self.assertIn('not valid JSON', teams['detail'])
        self.assertFalse(report['ready'])

    def test_env_that_is_not_an_object_is_never_touched(self):
        for bad in ({'env': ['x']}, ['not', 'an', 'object']):
            with self.subTest(bad=bad):
                fake = FakeMachine(self)
                fake.write_settings(bad)
                before = fake.settings.read_text()
                br.apply(fake.machine, yes=True)
                self.assertEqual(fake.settings.read_text(), before)
                self.assertEqual(fake.backups(), [])

    def test_merge_never_removes_or_duplicates(self):
        data = {'permissions': {'allow': ['A', 'B'], 'deny': ['C']}, 'env': {'X': '1'}}
        new, changes = br.merge(data, env={'X': '1'}, allow=['B', 'D'])
        self.assertEqual(new['permissions'], {'allow': ['A', 'B', 'D'], 'deny': ['C']})
        self.assertEqual(changes, ['allow D'])
        self.assertEqual(data['permissions']['allow'], ['A', 'B'], 'the input is not mutated')


class Idempotency(unittest.TestCase):
    def test_second_apply_changes_nothing(self):
        for system in ('mac', 'windows'):
            with self.subTest(system=system):
                fake = FakeMachine(self, system=system)
                fake.write_settings(STUDENT_SETTINGS)
                local = fake.machine.workbench_settings
                local.write_text(json.dumps({'permissions': {'allow': ['Bash(ls)']}}), encoding='utf-8')
                first = br.apply(fake.machine, yes=True)
                self.assertTrue(first['changed'])
                snapshot = {p: p.read_bytes() for p in (fake.settings, local)}
                backups = fake.backups() + fake.backups(local.parent)
                second = br.apply(fake.machine, yes=True)
                self.assertEqual(second['changed'], [])
                self.assertEqual(second['backups'], [])
                self.assertEqual({p: p.read_bytes() for p in snapshot}, snapshot)
                self.assertEqual(fake.backups() + fake.backups(local.parent), backups)
                self.assertTrue(second['ready'])
                self.assertEqual(br.plan(fake.machine)['will_change'], [])

    def test_render_says_nothing_changed(self):
        fake = FakeMachine(self)
        br.apply(fake.machine, yes=True)
        text = br.render(br.apply(fake.machine, yes=True))
        self.assertIn('nothing; everything this step manages was already in place', text)
        self.assertIn('BRIDGE READY', text)

    def test_tmux_is_installed_only_when_missing(self):
        fake = FakeMachine(self, tools=('brew', 'claude', 'zsh'))
        first = br.apply(fake.machine, yes=True)
        self.assertEqual(fake.brew_installs(), [['/synthetic/bin/brew', 'install', 'tmux']])
        self.assertIn('installed tmux with Homebrew', first['changed'])
        br.apply(fake.machine, yes=True)
        self.assertEqual(len(fake.brew_installs()), 1, 'tmux already there: Homebrew is not called again')


class ApprovalAndPlan(unittest.TestCase):
    def test_apply_without_yes_writes_nothing(self):
        fake = FakeMachine(self, tools=('brew', 'claude', 'zsh'))
        fake.write_settings(STUDENT_SETTINGS)
        before = fake.settings.read_bytes()
        report = br.apply(fake.machine, yes=False)
        self.assertTrue(report['refused'])
        self.assertEqual(fake.settings.read_bytes(), before)
        self.assertEqual(fake.brew_installs(), [])
        self.assertEqual(quiet_main(['--apply'], fake.machine), 2)
        self.assertEqual(fake.settings.read_bytes(), before)

    def test_plan_writes_nothing_and_names_each_change(self):
        fake = FakeMachine(self, system='windows')
        report = br.plan(fake.machine)
        self.assertFalse(fake.settings.exists())
        self.assertFalse(fake.machine.workbench_settings.exists())
        text = '\n'.join(report['will_change'])
        self.assertIn(f'"{TEAMS}": "1"', text)
        self.assertIn('PowerShell(workforce/skills/aibl-bridge/scripts/windows/bridge-go.ps1)', text)

    def test_homebrew_missing_is_reported_not_installed(self):
        fake = FakeMachine(self, tools=('claude', 'zsh'))
        report = br.apply(fake.machine, yes=True)
        self.assertEqual(fake.brew_installs(), [])
        tmux = by_item(report)['tmux']
        self.assertFalse(tmux['pass'])
        self.assertIn('step 4.2', tmux['fix'])

    def test_brew_failure_is_reported(self):
        fake = FakeMachine(self, tools=('brew', 'claude', 'zsh'), brew_exit=1)
        report = br.apply(fake.machine, yes=True)
        self.assertTrue(any('Homebrew could not install it' in s for s in report['skipped']))
        self.assertFalse(by_item(report)['tmux']['pass'])


class Windows(unittest.TestCase):
    def test_allow_rules_go_to_the_workbench_local_settings_only(self):
        fake = FakeMachine(self, system='windows')
        fake.write_settings(STUDENT_SETTINGS)
        local = fake.machine.workbench_settings
        local.write_text(json.dumps({'permissions': {'allow': ['Bash(ls)']}, 'other': 1}), encoding='utf-8')
        report = br.apply(fake.machine, yes=True)
        rules = json.loads(local.read_text())['permissions']['allow']
        self.assertEqual(rules[0], 'Bash(ls)')
        self.assertEqual(rules[1:], fake.machine.windows_allow_rules())
        self.assertEqual(json.loads(local.read_text())['other'], 1)
        self.assertEqual(json.loads(fake.settings.read_text())['permissions'], STUDENT_SETTINGS['permissions'],
                         'the user settings get only the env line')
        self.assertNotIn('tmux', by_item(report))
        self.assertEqual(fake.brew_installs(), [])
        self.assertTrue(report['ready'])

    def test_rules_are_exact_with_no_wildcard(self):
        machine = br.Machine(home='C:\\Users\\Student Name', system='windows',
                             workbench='C:\\Users\\Student Name\\GitHub\\my-workbench', which=lambda n: None, env={},
                             is_file=lambda p: False)
        self.assertEqual(machine.windows_allow_rules(), [
            'PowerShell(workforce/skills/aibl-bridge/scripts/windows/bridge-go.ps1)',
            'PowerShell(C:/Users/Student Name/GitHub/my-workbench/workforce/skills/aibl-bridge/scripts/windows/bridge-go.ps1)',
        ])
        self.assertFalse(any('*' in r for r in machine.windows_allow_rules()))

    def test_missing_workbench_is_a_fail_not_a_write(self):
        fake = FakeMachine(self, system='windows')
        fake.machine.workbench = fake.home / 'GitHub' / 'elsewhere'
        report = br.apply(fake.machine, yes=True)
        self.assertFalse(by_item(report)['launcher permission']['pass'])
        self.assertFalse((fake.home / 'GitHub' / 'elsewhere').exists())

    def test_windows_asks_the_cli_directly(self):
        fake = FakeMachine(self, system='windows')
        br.verify(fake.machine)
        self.assertIn(['/synthetic/bin/claude', 'auth', 'status', '--json'], fake.calls)


class SignIn(unittest.TestCase):
    def login(self, **kwargs):
        fake = FakeMachine(self, **kwargs)
        report = br.verify(fake.machine)
        return by_item(report)['claude login'], br.render(report), fake

    def test_subscription_passes(self):
        login, text, fake = self.login()
        self.assertTrue(login['pass'])
        self.assertIn(['zsh', '-ic', 'claude auth status --json'], fake.calls, 'Mac asks the way the bridge starts claude')

    def test_account_details_are_never_printed(self):
        _, text, _ = self.login()
        self.assertNotIn('student@example.com', text)
        self.assertNotIn('Synthetic Org', text)

    def test_signed_out_fails_with_a_hand_off(self):
        login, _, _ = self.login(auth={'loggedIn': False, 'authMethod': 'none'})
        self.assertFalse(login['pass'])
        self.assertIn('/login', login['fix'])
        self.assertIn('Never sign in for them', login['fix'])

    def test_api_key_fails_as_billing(self):
        login, _, _ = self.login(auth={'loggedIn': True, 'authMethod': 'api_key', 'apiProvider': 'firstParty'})
        self.assertFalse(login['pass'])
        self.assertIn('API key', login['detail'])

    def test_third_party_provider_fails(self):
        login, _, _ = self.login(auth={'loggedIn': True, 'authMethod': 'claude.ai', 'apiProvider': 'bedrock'})
        self.assertFalse(login['pass'])

    def test_terminal_cannot_find_claude(self):
        login, _, _ = self.login(auth=None)
        self.assertFalse(login['pass'])
        self.assertIn('4.5', login['fix'])

    def test_shell_noise_around_the_json_is_ignored(self):
        login, _, _ = self.login(auth_raw='Welcome back!\n' + json.dumps(SUBSCRIPTION) + '\n')
        self.assertTrue(login['pass'])

    def test_unreadable_answer_fails(self):
        login, _, _ = self.login(auth_raw='something went wrong')
        self.assertFalse(login['pass'])

    def test_missing_cli_fails_both_items(self):
        fake = FakeMachine(self, tools=('tmux', 'zsh'))
        items = by_item(br.verify(fake.machine))
        self.assertFalse(items['claude CLI']['pass'])
        self.assertFalse(items['claude login']['pass'])
        self.assertFalse(any('auth' in ' '.join(c) for c in fake.calls))


class VerifyOutput(unittest.TestCase):
    def test_one_pass_or_fail_line_per_item_and_exit_code(self):
        fake = FakeMachine(self, tools=('claude', 'zsh'), auth={'loggedIn': False})
        text = br.render(br.verify(fake.machine))
        lines = [l for l in text.splitlines() if l.startswith(('PASS', 'FAIL'))]
        self.assertEqual([l.split(':')[0] for l in lines],
                         ['FAIL  tmux', 'FAIL  agent teams', 'PASS  claude CLI', 'FAIL  claude login'])
        self.assertIn('BRIDGE NOT READY (3 to fix)', text)
        self.assertEqual(quiet_main(['--verify'], fake.machine), 1)
        br.apply(fake.machine, yes=True)
        fake.tools.add('tmux')
        fake.auth = SUBSCRIPTION
        self.assertEqual(quiet_main(['--verify'], fake.machine), 0)

    def test_no_em_dashes_in_student_facing_text(self):
        fake = FakeMachine(self, system='windows', tools=('zsh',), auth={'loggedIn': False})
        for report in (br.plan(fake.machine), br.verify(fake.machine)):
            self.assertNotIn('\u2014', br.render(report))


if __name__ == '__main__':
    unittest.main()
