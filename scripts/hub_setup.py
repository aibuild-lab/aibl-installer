#!/usr/bin/env python3
"""Create the student's workbench from the public template. Standard library only.

This is step 8 of SETUP-PROMPT.md on the ordinary route. The guided session
(the Claude app or the Codex app, reading the prompt) has already installed the
tools, signed the student in to GitHub and the app's command-line twin, and
installed the secrets guard. This script does the one part that should never
be improvised: it creates the private repository <user>/my-workbench from the
public template, clones it to ~/GitHub/my-workbench, sets a repo-local Git
identity, checks that the three starter skills landed, and prints JSON.

No invitation, no course package, no release pin. The template is public, so
any signed-in GitHub account can use it. A folder or repository from an earlier
attempt is reused when it is the student's own workbench, and never replaced.
Nothing here deletes anything.

The frozen cohort route (family_setup_handoff.py) is separate and unchanged.
"""
from __future__ import annotations
import argparse, datetime, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from course_setup import (HARNESSES, SetupError, check_tools, command, registry, remote_matches, repo_name,
                          safe_workspace, verify_existing, write)

SKILLS = ('aibl-personalize', 'aibl-checkpoint', 'aibl-enroll')


def public_template(reg=None):
    reg = reg or registry()
    value = (reg.get('hub') or {}).get('public_template')
    if not isinstance(value, str) or value.count('/') != 1:
        raise SetupError('The program registry has no public template for the workbench; ask the course team.')
    return value


def github_user(runner):
    try:
        user = json.loads(runner(['gh', 'api', 'user']))
    except SetupError as exc:
        if exc.reason == 'authentication_missing':
            raise SetupError('GitHub is not signed in yet. Run gh auth login --web (step 6), then run this again.', 'authentication_missing')
        raise
    if not isinstance(user, dict) or not user.get('login'):
        raise SetupError('GitHub did not return a signed-in user. Run gh auth login --web and try again.', 'authentication_missing')
    return user


def template_head(runner, template):
    try:
        meta = json.loads(runner(['gh', 'api', 'repos/' + template]))
    except SetupError as exc:
        if exc.reason == 'not_found':
            raise SetupError(f'Cannot read the template {template}. Check the network, then ask in your program channel.', 'not_found')
        raise
    if not meta.get('is_template'):
        raise SetupError(f'{template} is not marked as a template repository; ask the course team.')
    branch = meta.get('default_branch') or 'main'
    head = json.loads(runner(['gh', 'api', f'repos/{template}/commits/{branch}']))
    return {'repository': template, 'default_branch': branch, 'revision': head.get('sha')}


def existing_repository(runner, full):
    """The student's repository if it exists, else None. Network and auth failures are raised, never treated as absence."""
    try:
        return json.loads(runner(['gh', 'api', 'repos/' + full]))
    except SetupError as exc:
        if exc.reason == 'not_found':
            return None
        raise


def wait_for_first_commit(runner, full, branch, tries=12, pause=2.5, sleep=time.sleep):
    """A repository made from a template fills in a few seconds later. Wait for its first commit before cloning."""
    for attempt in range(tries):
        try:
            head = json.loads(runner(['gh', 'api', f'repos/{full}/commits/{branch}']))
            if head.get('sha'):
                return head['sha']
        except SetupError as exc:
            if exc.reason not in ('not_found', 'operation'):
                raise
        if attempt + 1 < tries:
            sleep(pause)
    raise SetupError('GitHub is still preparing the new repository. Wait a minute and run this same command again; nothing needs to be undone.')


def clone(runner, full, folder):
    temporary = folder.parent / (folder.name + '.cloning')
    if temporary.exists():
        raise SetupError(f'An unfinished clone is at {temporary}. Move it aside (do not delete anything you are unsure of) and run this again.')
    runner(['gh', 'repo', 'clone', full, str(temporary)])
    verify_existing(temporary, full, runner)
    if folder.exists():
        raise SetupError('The workbench folder appeared while cloning. Both folders are kept; review before continuing.')
    temporary.rename(folder)


def local_identity(runner, folder, user):
    login = user['login']
    wanted = {'user.name': user.get('name') or login, 'user.email': f"{user.get('id')}+{login}@users.noreply.github.com"}
    for key, value in wanted.items():
        try:
            current = runner(['git', 'config', '--local', '--get', key], cwd=folder)
        except SetupError:
            current = ''
        if not current:
            runner(['git', 'config', '--local', key, value], cwd=folder)


def skills_present(folder):
    found = {}
    for app_dir in ('.claude/skills', '.agents/skills'):
        found[app_dir] = [s for s in SKILLS if (folder / app_dir / s / 'SKILL.md').is_file()]
    return found


def twin_signed_in(runner, harness):
    """Report only. Sign-in happened in step 6; a false here is a reminder, not a stop."""
    h = HARNESSES[harness]
    try:
        out = runner(h['status'])
    except SetupError:
        return False
    if harness == 'claude':
        try:
            return bool(json.loads(out).get('loggedIn'))
        except (TypeError, ValueError):
            return False
    return 'logged in' in out.lower() or 'signed in' in out.lower()


def setup(harness, workspace=None, name='my-workbench', template=None, runner=command, sleep=time.sleep, home=None):
    if harness not in HARNESSES:
        raise SetupError('Unknown app. Use claude or codex.')
    home = Path(home) if home else Path.home()
    name = repo_name(name)
    workspace = safe_workspace(workspace or (home / 'GitHub'))
    template = template or public_template()
    started = time.monotonic()

    versions = check_tools(runner, harness=harness)
    user = github_user(runner)
    full = f"{user['login']}/{name}"
    folder = workspace / name
    source = template_head(runner, template)

    created = False
    if folder.exists():
        verify_existing(folder, full, runner)
        status = 'already_initialized'
    else:
        existing = existing_repository(runner, full)
        if existing is None:
            runner(['gh', 'repo', 'create', full, '--private', '--template', template])
            created = True
            wait_for_first_commit(runner, full, source['default_branch'], sleep=sleep)
        else:
            if not existing.get('private'):
                raise SetupError(f'A repository named {name} already exists under this account and is not private. Choose a different name; nothing was changed.')
            made_from = (existing.get('template_repository') or {}).get('full_name')
            if made_from and made_from != template:
                raise SetupError(f'{full} exists but was made from {made_from}, not the workbench template. Keep it and choose a different name.')
        workspace.mkdir(parents=True, exist_ok=True)
        clone(runner, full, folder)
        status = 'created' if created else 'cloned_existing'

    local_identity(runner, folder, user)
    meta = existing_repository(runner, full) or {}
    if not meta.get('private', True):
        raise SetupError(f'{full} is not private. Make it private on github.com before continuing.')
    skills = skills_present(folder)
    missing = [s for s in SKILLS if s not in skills['.claude/skills']]
    receipt = {
        'status': status,
        'harness': harness,
        'repository': full,
        'private': bool(meta.get('private', True)),
        'workspace': str(folder),
        'template': source,
        'versions': versions,
        'skills': skills,
        'skills_missing': missing,
        'twin_signed_in': twin_signed_in(runner, harness),
        'elapsed_seconds': round(time.monotonic() - started, 2),
        'recorded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    write(folder / '.aibl-local' / 'setup.json', receipt)
    if missing:
        receipt['note'] = ('This workbench was made before the starter skills shipped in the template, or from a different template. '
                           'Nothing was changed. Ask in your program channel with this message.')
    receipt['next'] = ('Open ' + str(folder) + ' in the app you chose (step 9). Type / in Claude or $ in Codex; the three aibl- skills are there.')
    return receipt


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--harness', choices=list(HARNESSES), required=True, help='The app the student works in: claude or codex.')
    p.add_argument('--repo-name', default='my-workbench')
    p.add_argument('--workspace', help='Parent folder for the workbench. Default: ~/GitHub')
    p.add_argument('--template', help='Override the public template from course-options.json (testing only).')
    p.add_argument('--no-launch', action='store_true', help='Accepted for symmetry with course_setup.py; this script never launches an app.')
    a = p.parse_args()
    try:
        print(json.dumps(setup(a.harness, a.workspace, a.repo_name, a.template), indent=2))
    except SetupError as exc:
        print('Setup paused: ' + str(exc))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
