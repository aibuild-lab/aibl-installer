#!/usr/bin/env python3
"""Bridge readiness: get this computer ready for the course's bridge. Standard library only.

This is step 8.5 of SETUP-PROMPT.md, on the Claude route only. The bridge is the
course's multi-agent helper: from a thread in the Claude app it hands a team job
to a terminal Claude running out of sight, which messages the result back into
the thread. The bridge scripts arrive later with the Workforce program; this
step makes sure the computer underneath them is ready, so a student never has
to paste a Terminal command for it.

What the bridge needs, and what this script does about each:

  Mac      tmux                  installs it with Homebrew, only if missing
  both     agent teams switched  adds "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
           on                    under "env" in ~/.claude/settings.json (merged,
                                 never overwritten, backed up first to
                                 ~/.claude/backups/bridge-readiness/)
  Windows  launcher permission   adds the exact allow rules for the bridge's
                                 zero-argument launcher (bridge-go.ps1) under
                                 "permissions" "allow" in the same
                                 ~/.claude/settings.json, matching the path the
                                 bridge skills run it by from the user's skills
                                 folder (~/.claude/skills/aibl-bridge), so it
                                 holds from any folder; the agent cannot add
                                 these itself, the app treats that as
                                 self-modification
  both     terminal Claude       checks it is installed and signed in with a
           signed in             Claude subscription, and that no API key
                                 outranks it; the script never signs in itself

Windows needs no tmux: the Windows port opens its own console window instead,
and WSL would not help (the desktop thread's inbox is a Windows named pipe).

Modes:
  --plan            (default) say what is in place and exactly what --apply
                    would change. Writes nothing.
  --apply --yes     make those changes. Refuses without --yes, which the agent
                    passes only after the student said yes to the plan.
  --verify          one plain-English PASS or FAIL line per item. Exit 0 when
                    every item passes, 1 otherwise.

Safe to re-run. When nothing needs changing, nothing is written and no backup
is made. A settings file that is not valid JSON is never touched. Nothing here
prints a credential or the account's email; the sign-in check reads only
whether the terminal Claude is signed in and by which method.
"""
from __future__ import annotations

import argparse
import copy
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path, PureWindowsPath

TEAMS_KEY = 'CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS'
TEAMS_VALUE = '1'
# The bridge skills live in the user's skills folder (the workbench template copies them there on Windows), so they
# work from any folder. aibl-bridge tells the agent to run `<this skill's base directory>/scripts/windows/bridge-go.ps1`
# by its bare path; aibl-bridge-setup runs the same file as `<its base directory>/../aibl-bridge/scripts/windows/...`.
SKILLS_DIR = ('.claude', 'skills')
BRIDGE_SKILL = 'aibl-bridge'
SETUP_SKILL = 'aibl-bridge-setup'
BRIDGE_GO = 'scripts/windows/bridge-go.ps1'
TMUX_FALLBACKS = ('/opt/homebrew/bin/tmux', '/usr/local/bin/tmux')
BREW_FALLBACKS = ('/opt/homebrew/bin/brew', '/usr/local/bin/brew')
# Backups live outside every repository (the workbench's .gitignore does not cover backup names), beside the
# app's own backups folder.
BACKUP_DIR = ('.claude', 'backups', 'bridge-readiness')
# The only sign-in methods that bill the student's Claude subscription. `claude auth status --json` reports one of:
# none, third_party, claude.ai, api_key_helper, oauth_token, api_key.
SUBSCRIPTION_METHODS = ('claude.ai', 'oauth_token')


class Paused(Exception):
    """A file this step must not touch as it stands. Nothing was changed."""


def run_command(args, timeout=120):
    return subprocess.run(args, text=True, encoding='utf-8', errors='replace', capture_output=True, timeout=timeout)


def system_name(override=None):
    if override:
        return override
    if sys.platform == 'darwin':
        return 'mac'
    if sys.platform.startswith('win'):
        return 'windows'
    return 'other'


class Machine:
    """Everything the checks read from the computer, injectable for tests."""

    def __init__(self, home=None, system=None, which=shutil.which, run=run_command, env=None,
                 is_file=lambda path: Path(path).is_file()):
        self.home = Path(home) if home else Path.home()
        self.system = system_name(system)
        self.which = which
        self.run = run
        self.env = os.environ if env is None else env
        self.is_file = is_file

    @property
    def user_settings(self):
        return self.home / '.claude' / 'settings.json'

    @property
    def bridge_skill_dir(self):
        return self.home.joinpath(*SKILLS_DIR, BRIDGE_SKILL)

    @property
    def backup_dir(self):
        return self.home.joinpath(*BACKUP_DIR)

    def windows_allow_rules(self):
        """Exact rules, no wildcard (auto mode drops wildcarded interpreter rules).

        One rule per way the bridge skills run the launcher from the user's skills folder: aibl-bridge's
        `<base>/scripts/windows/bridge-go.ps1` and aibl-bridge-setup's `<base>/../aibl-bridge/scripts/windows/...`.
        Absolute, with forward slashes, the form Wade's allow-rule receipts proved (09-20). Empty when the account
        folder has a space: that path has to be quoted to run, so the typed command could never equal a rule.
        """
        skills = PureWindowsPath(str(self.home.joinpath(*SKILLS_DIR))).as_posix().rstrip('/')
        if any(ch.isspace() for ch in skills):
            return []
        return [f'PowerShell({skills}/{BRIDGE_SKILL}/{BRIDGE_GO})',
                f'PowerShell({skills}/{SETUP_SKILL}/../{BRIDGE_SKILL}/{BRIDGE_GO})']


# ---------------------------------------------------------------- settings merge

def read_settings(path):
    """Return the settings object, or None when the file does not exist. Raise Paused when it cannot be merged into."""
    path = Path(path)
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding='utf-8-sig')
    except UnicodeDecodeError:
        raise Paused(f'{display(path)} is not saved as UTF-8 text (it may be UTF-16), so it cannot be merged into. '
                     'Nothing was changed and it was not overwritten. Fix that file with the student; never delete it.')
    except OSError as exc:
        raise Paused(f'{display(path)} could not be read ({exc.strerror or exc}). Nothing was changed.')
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise Paused(f'{display(path)} is not valid JSON ({exc}). Nothing was changed and it was not overwritten. '
                     'Fix that file with the student; never delete it.')
    if not isinstance(data, dict):
        raise Paused(f'{display(path)} must contain a JSON object. Nothing was changed and it was not overwritten.')
    return data


def merge(data, env=None, allow=()):
    """Return (new settings, list of plain-English changes). Never removes or reorders anything already there."""
    new = copy.deepcopy(data) if data else {}
    changes = []
    if env:
        current = new.get('env')
        if current is None:
            current = new['env'] = {}
        elif not isinstance(current, dict):
            raise Paused('"env" in the settings file is not an object, so it cannot be merged into. Nothing was changed.')
        for key, value in env.items():
            if key not in current:
                current[key] = value
                changes.append(f'add "{key}": "{value}" under "env"')
            elif current[key] != value:
                changes.append(f'set "{key}" under "env" to "{value}" (it was {json.dumps(current[key])})')
                current[key] = value
    if allow:
        perms = new.get('permissions')
        if perms is None:
            perms = new['permissions'] = {}
        elif not isinstance(perms, dict):
            raise Paused('"permissions" in the settings file is not an object, so it cannot be merged into. Nothing was changed.')
        rules = perms.get('allow')
        if rules is None:
            rules = perms['allow'] = []
        elif not isinstance(rules, list):
            raise Paused('"permissions.allow" in the settings file is not a list, so it cannot be merged into. Nothing was changed.')
        for rule in allow:
            if rule not in rules:
                rules.append(rule)
                changes.append(f'allow {rule}')
    return new, changes


def _create_private(path):
    """Open a new file for writing that is 0600 from its first byte. Fails if the name is taken."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0), 0o600)
    return os.fdopen(fd, 'wb')


def write_settings(path, original, new, backup_dir, label, stamp=None):
    """Back up the existing file, write the merged one atomically, read it back. Return the backup path or None.

    A symlinked settings file (dotfiles users) is written through to its target, so the link survives.
    Any failure leaves the original file as it was, removes the temporary file, and raises Paused.
    """
    path = Path(path)
    target = Path(os.path.realpath(path)) if path.is_symlink() else path
    backup = temp = None
    try:
        mode = None
        if target.exists():
            mode = target.stat().st_mode & 0o777
            stamp = stamp or datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
            Path(backup_dir).mkdir(parents=True, exist_ok=True)
            backup = Path(backup_dir) / f'{label}.{stamp}'
            n = 1
            while backup.exists():
                n += 1
                backup = Path(backup_dir) / f'{label}.{stamp}-{n}'
            with _create_private(backup) as out:
                out.write(target.read_bytes())
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(f'{target.name}.bridge-readiness-{os.getpid()}.tmp')
        with _create_private(temp) as out:
            out.write((json.dumps(new, indent=2, ensure_ascii=False) + '\n').encode('utf-8'))
        if mode is not None and os.name != 'nt':
            os.chmod(temp, mode)
        os.replace(temp, target)
        temp = None
    except OSError as exc:
        if temp is not None:
            try:
                temp.unlink()
            except OSError:
                pass
        kept = f' A copy of the file as it was is at {backup}.' if backup else ''
        raise Paused(f'{display(path)} could not be written ({exc.strerror or exc}). It was left as it was.{kept}')
    readback = read_settings(target)
    if readback != new or not set(original or {}) <= set(readback):
        raise Paused(f'{display(path)} did not read back as written. The backup is at {backup}.')
    return backup


def display(path):
    path = Path(path)
    try:
        return '~/' + path.relative_to(Path.home()).as_posix()
    except ValueError:
        return str(path)


# ---------------------------------------------------------------- the four items

def item(name, ok, detail, fix=None, change=None):
    return {'item': name, 'pass': ok, 'detail': detail, 'fix': fix, 'change': change}


def find_tool(machine, name, fallbacks):
    """(path, on_path). A tool installed at its usual location but missing from PATH still counts as installed."""
    found = machine.which(name)
    if found:
        return found, True
    for candidate in fallbacks:
        if machine.is_file(candidate):
            return candidate, False
    return None, False


def check_tmux(machine):
    if machine.system == 'windows':
        return None
    path, on_path = find_tool(machine, 'tmux', TMUX_FALLBACKS if machine.system == 'mac' else ())
    if path:
        note = '' if on_path else ' (not on this shell\'s PATH yet; the Homebrew line from step 4.5 fixes that)'
        return item('tmux', True, f'installed at {path}{note}')
    if machine.system != 'mac':
        return item('tmux', False, 'not installed', fix='This installer supports macOS and Windows. Install tmux with your system\'s package manager.')
    brew, _ = find_tool(machine, 'brew', BREW_FALLBACKS)
    if not brew:
        return item('tmux', False, 'not installed, and Homebrew is missing',
                    fix='Homebrew installs tmux. Go back to step 4.2 (Homebrew), then run this step again.')
    return item('tmux', False, 'not installed', fix='(Agent: rerun this script with --apply --yes after the student\'s yes; it installs tmux with Homebrew.)',
                change={'kind': 'brew', 'brew': brew, 'text': 'install tmux with Homebrew (no password needed)'})


def check_teams(machine):
    try:
        data = read_settings(machine.user_settings)
        new, changes = merge(data, env={TEAMS_KEY: TEAMS_VALUE})
    except Paused as exc:
        return item('agent teams', False, str(exc), fix='Fix the settings file with the student, then run this step again.')
    if not changes:
        return item('agent teams', True, f'switched on in {display(machine.user_settings)}')
    return item('agent teams', False, f'switched off in {display(machine.user_settings)}',
                fix='(Agent: rerun this script with --apply --yes after the student\'s yes; it adds one line under "env" in that file.)',
                change={'kind': 'settings', 'path': str(machine.user_settings), 'env': {TEAMS_KEY: TEAMS_VALUE},
                        'label': 'settings.json',
                        'text': f'in {display(machine.user_settings)}: ' + '; '.join(changes)})


def check_allow_rule(machine):
    rules = machine.windows_allow_rules() if machine.system == 'windows' else []
    if not rules:
        return None
    try:
        data = read_settings(machine.user_settings)
        new, changes = merge(data, allow=rules)
    except Paused as exc:
        return item('launcher permission', False, str(exc), fix='Fix the settings file with the student, then run this step again.')
    if not changes:
        return item('launcher permission', True, f'the bridge launcher is allowed in {display(machine.user_settings)}')
    return item('launcher permission', False, 'the bridge launcher is not allowed yet, so the agent could be stopped from starting the bridge',
                fix='(Agent: rerun this script with --apply --yes after the student\'s yes; it adds the launcher\'s exact allow rules to that settings file.)',
                change={'kind': 'settings', 'path': str(machine.user_settings), 'allow': rules,
                        'label': 'settings.json',
                        'text': f'in {display(machine.user_settings)}: ' + '; '.join(changes)})


def find_claude(machine):
    found = machine.which('claude')
    if found:
        return found
    home = machine.home
    if machine.system == 'windows':
        candidates = [home / '.local' / 'bin' / 'claude.exe']
        appdata = machine.env.get('APPDATA')
        if appdata:
            candidates.append(Path(appdata) / 'npm' / 'claude.cmd')
    else:
        candidates = [home / '.local' / 'bin' / 'claude', Path('/opt/homebrew/bin/claude'), Path('/usr/local/bin/claude')]
    for candidate in candidates:
        if machine.is_file(candidate):
            return str(candidate)
    return None


def auth_status(machine, claude):
    """Ask the terminal Claude whether it is signed in. On a Mac, ask it the way the bridge starts it: zsh -ic."""
    if machine.system == 'mac' and machine.which('zsh'):
        args = ['zsh', '-ic', 'claude auth status --json']
    else:
        args = [claude, 'auth', 'status', '--json']
    try:
        result = machine.run(args, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None, 'unanswered'
    out = result.stdout or ''
    if result.returncode == 127 or 'command not found' in (out + (result.stderr or '')).lower():
        return None, 'terminal_cannot_find'
    data = parse_auth(out)
    return (data, 'ok') if data is not None else (None, 'unreadable')


def parse_auth(out):
    """Find the status object in output that may carry shell noise before or after it (zsh -ic reads ~/.zshrc).

    Decodes one JSON value at each '{' in turn, so a stray brace in a greeting cannot swallow or split the object.
    """
    decoder = json.JSONDecoder()
    i = out.find('{')
    while i >= 0:
        try:
            obj, _ = decoder.raw_decode(out, i)
        except ValueError:
            obj = None
        if isinstance(obj, dict) and 'loggedIn' in obj:
            return obj
        i = out.find('{', i + 1)
    return None


def safe_name(value):
    """A key source is a setting's name (ANTHROPIC_API_KEY, apiKeyHelper), never a value; print it only if it looks like one."""
    text = str(value or '')
    return text if re.fullmatch(r'[A-Za-z0-9_ ./-]{1,40}', text) else None


def check_claude(machine):
    """Two items: the CLI is there, and it is signed in with a subscription. Only the sign-in method is ever reported."""
    claude = find_claude(machine)
    if not claude:
        cli = item('claude CLI', False, 'the terminal Claude (Claude Code CLI) is not installed',
                   fix='Go back to step 4.4 (Mac) or 5.3 (Windows), then run this step again.')
        return [cli, item('claude login', False, 'cannot check until the terminal Claude is installed', fix=cli['fix'])]
    cli = item('claude CLI', True, f'installed at {claude}')
    data, why = auth_status(machine, claude)
    login_fix = ('Agent: start claude auth login --claudeai in the background (a foreground run can time out and hide the sign-in '
                 'link), watch its output, and show the student any sign-in link it prints. The student picks the Claude account '
                 'they use in this app (not an API console) and approves it in the browser. The student never types a command, and you '
                 'never ask for or see a password or code. Then run this check again.')
    key_fix = ('Do not remove the key yourself. Tell the student plainly that bridge runs would be billed to an API key, not their '
               'subscription, and point them to their program channel.')
    if why == 'terminal_cannot_find':
        return [cli, item('claude login', False, 'your Terminal cannot find the terminal Claude, and the bridge starts it from there',
                          fix='Redo step 4.5 so ~/.zshrc has the ~/.local/bin line, then run this check again.')]
    if data is None:
        return [cli, item('claude login', False, 'the terminal Claude did not say whether it is signed in', fix=login_fix)]
    if data.get('loggedIn') is not True:
        return [cli, item('claude login', False, 'the terminal Claude is not signed in', fix=login_fix)]
    method = str(data.get('authMethod') or 'none')
    provider = str(data.get('apiProvider') or 'firstParty')
    if data.get('apiKeySource') is not None:
        # An API key in the environment or a key helper outranks the subscription sign-in, whatever authMethod says.
        source = safe_name(data.get('apiKeySource'))
        where = f' (from {source})' if source else ''
        return [cli, item('claude login', False, f'the terminal Claude would use an API key{where}, not the Claude subscription, '
                          'so bridge runs would be billed to that key', fix=key_fix)]
    if method in ('api_key', 'api_key_helper'):
        return [cli, item('claude login', False, 'the terminal Claude is signed in with an API key, not a Claude subscription, '
                          'so bridge runs would be billed to that key', fix=key_fix)]
    if provider != 'firstParty' or method == 'third_party':
        return [cli, item('claude login', False, f'the terminal Claude is signed in through {provider}, not a Claude subscription',
                          fix='Tell the student plainly and ask in their program channel before using the bridge.')]
    if method not in SUBSCRIPTION_METHODS:
        return [cli, item('claude login', False, f'the terminal Claude is not signed in with a Claude subscription (method: {safe_name(method) or "unrecognized"})',
                          fix=login_fix)]
    return [cli, item('claude login', True, f'signed in with a Claude subscription (method: {method})')]


def check_all(machine):
    items = [check_tmux(machine), check_teams(machine), check_allow_rule(machine), *check_claude(machine)]
    return [i for i in items if i]


def notes(machine):
    out = []
    if machine.system == 'windows':
        out.append('Windows opens a small console window for the bridge instead of tmux, so tmux is not needed here.')
        out.append('The Windows bridge has a round-trip receipt with VS Code as the receiving thread. With the Claude desktop app '
                   'as the receiver it is not proven yet; say so plainly.')
        if not machine.windows_allow_rules():
            out.append('This Windows account folder has a space in its name, so no exact allow rule can match the bridge '
                       'launcher (its path has to be quoted to run). Nothing was added for it. The app will ask before the '
                       'first bridge launch, and the student can allow it from then on.')
    if not machine.bridge_skill_dir.is_dir():
        out.append('The bridge itself arrives with the Workforce program. Once it is there, the aibl-bridge-setup skill proves a round trip.')
    return out


# ---------------------------------------------------------------- modes

def plan(machine):
    items = check_all(machine)
    return {'mode': 'plan', 'system': machine.system, 'items': items,
            'will_change': [i['change']['text'] for i in items if i.get('change')], 'notes': notes(machine)}


def apply(machine, yes=False, stamp=None):
    if not yes:
        return {'mode': 'apply', 'refused': True,
                'message': 'Nothing was changed. Show the student the plan (--plan) and run again with --apply --yes only after they say yes.'}
    changed, skipped, backups = [], [], []
    pending = {}  # settings path -> everything to merge into it, so each file is backed up and written once
    for entry in check_all(machine):
        change = entry.get('change')
        if not change:
            if not entry['pass'] and entry['item'] in ('tmux', 'agent teams', 'launcher permission'):
                skipped.append(f"{entry['item']}: {entry['detail']}")
            continue
        if change['kind'] == 'brew':
            result = machine.run([change['brew'], 'install', 'tmux'], timeout=900)
            if result.returncode:
                tail = ' '.join((result.stderr or result.stdout or '').strip().splitlines()[-3:])
                skipped.append(f'tmux: Homebrew could not install it (exit {result.returncode}). {tail}'.strip())
            else:
                changed.append('installed tmux with Homebrew')
        elif change['kind'] == 'settings':
            want = pending.setdefault(change['path'], {'env': {}, 'allow': [], 'label': change['label']})
            want['env'].update(change.get('env') or {})
            want['allow'].extend(change.get('allow', ()))
    for path, want in pending.items():
        path = Path(path)
        data = read_settings(path)
        new, changes = merge(data, env=want['env'], allow=want['allow'])
        if changes:
            backup = write_settings(path, data, new, machine.backup_dir, want['label'], stamp=stamp)
            if backup:
                backups.append(str(backup))
            changed.append(f'{display(path)}: ' + '; '.join(changes))
    report = verify(machine)
    report.update({'mode': 'apply', 'changed': changed, 'skipped': skipped, 'backups': backups})
    return report


def verify(machine):
    items = check_all(machine)
    return {'mode': 'verify', 'system': machine.system, 'items': items,
            'ready': all(i['pass'] for i in items), 'notes': notes(machine)}


def render(report):
    lines = []
    if report.get('refused'):
        return report['message']
    if report['mode'] == 'apply':
        lines += ['Changed:'] + ([f'  - {c}' for c in report['changed']] or ['  - nothing; everything this step manages was already in place'])
        for b in report['backups']:
            lines.append(f'  backup of the file as it was: {b}')
        if report['skipped']:
            lines += ['Not changed:'] + [f'  - {s}' for s in report['skipped']]
        lines.append('')
    for i in report['items']:
        lines.append(f"{'PASS' if i['pass'] else 'FAIL'}  {i['item']}: {i['detail']}")
        if not i['pass'] and i.get('fix') and report['mode'] != 'plan':
            lines.append(f"      Fix: {i['fix']}")
    if report['mode'] == 'plan':
        lines.append('')
        if report['will_change']:
            lines += ['Will change, after the student says yes (--apply --yes):'] + [f'  - {c}' for c in report['will_change']]
            lines.append('  Each settings file is backed up first; nothing else in it changes.')
        else:
            lines.append('Nothing to change.')
        left = [i for i in report['items'] if not i['pass'] and not i.get('change')]
        if left:
            lines += ['Not something this step changes:'] + [f"  - {i['item']}: {i['fix']}" for i in left]
    else:
        failed = sum(1 for i in report['items'] if not i['pass'])
        lines.append('')
        lines.append('BRIDGE READY' if not failed else f'BRIDGE NOT READY ({failed} to fix)')
    for n in report.get('notes', []):
        lines.append(f'Note: {n}')
    return '\n'.join(lines)


def main(argv=None, machine=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument('--plan', action='store_true', help='Say what is in place and what --apply would change. Default.')
    mode.add_argument('--apply', action='store_true', help='Make the changes. Needs --yes.')
    mode.add_argument('--verify', action='store_true', help='PASS or FAIL per item.')
    p.add_argument('--yes', action='store_true', help='The student said yes to the plan.')
    p.add_argument('--json', action='store_true', help='Print JSON instead of plain lines.')
    p.add_argument('--system', choices=('mac', 'windows', 'other'), help=argparse.SUPPRESS)
    a = p.parse_args(argv)
    machine = machine or Machine(system=a.system)
    try:
        if a.apply:
            report = apply(machine, yes=a.yes)
        elif a.verify:
            report = verify(machine)
        else:
            report = plan(machine)
    except Paused as exc:
        print('Paused: ' + str(exc))
        return 2
    print(json.dumps(report, indent=2) if a.json else render(report))
    if report.get('refused'):
        return 2
    if report['mode'] == 'plan':
        return 0
    return 0 if report['ready'] else 1


if __name__ == '__main__':
    sys.exit(main())
