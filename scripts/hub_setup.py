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
import argparse, datetime, json, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from course_setup import (HARNESSES, SetupError, check_tools, command, registry, remote_matches, repo_name,
                          safe_workspace, verify_existing, write)

SKILLS = ('aibl-personalize', 'aibl-checkpoint', 'aibl-enroll')

# cloned_existing: the repository came back from GitHub, for example onto a new computer. Some
# things never go to GitHub (the template's .gitignore and the course's library/.gitignore keep
# them on the computer), so they were only on the old one. SETUP-PROMPT.md step 8 says these
# same words when an older copy of this script gives no left_behind; tests keep the two equal.
LEFT_BEHIND = (
    "Your workbench came back from GitHub, but not everything comes with it. Anything in your library, "
    "your job folders and your voice samples was only on your old computer, so it isn't here. "
    "If that computer still works, copy them across before you go on:\n"
    "1. On the old computer, open your home folder, then GitHub, then my-workbench.\n"
    "2. Copy the library folder, the runs folder, and every file in work/course/staff whose name starts "
    "with voice or ends with -accounts.yaml onto a USB drive.\n"
    "3. On this computer, put each one back in the same place inside my-workbench. Add them in; "
    "don't replace the whole folder.\n"
    "If you worked on the old computer after your last save, save there first, then ask your assistant here "
    "to bring that save in.\n"
    "Keys you saved on the old computer aren't here either. Add them again when a lesson asks for them.\n"
    "If the old computer is gone, your saved work came back from GitHub; sign-ins, keys and your mail "
    "account records start fresh here.\n"
    "Already in a program? It came back with your workbench. To bring it up to date, paste the Update prompt; "
    "don't enroll again."
)
LEFT_BEHIND_NIGHT_SHIFT = ("Your Team HQ night shift ran on the old computer only. To run it on this one, "
                           "ask your assistant to put the night shift on a schedule.")
LEFT_BEHIND_PATHS = ('library/', 'runs/', 'work/course/staff/voice*', 'work/course/staff/*-accounts.yaml', '.env')

# Agent Native Camp alumni were set up by the Agent Native OS workshop installer, which made
# ~/GitHub/agent-native-os; Camp's reference clone sits beside it at ~/GitHub/agent-native-camp
# (Camp's scripts/diagnose-course-repo.mjs). Setup never touches Camp; on a verified Camp sign it
# says so, once, ever. Verified signs, the same as the template's update-check.mjs --joining-from:
#   - a Camp clone holding Camp's descriptor (id repo.agent-native-camp, on Camp main since
#     09-02-2026, so an older clone has none);
#   - a Camp clone whose own .git/config names aibuild-lab/agent-native-camp or a private
#     <name>/agent-native-camp-private mirror;
#   - ~/context-repo holding Camp's .camp-context-repo marker (Week 2, on the camper's computer).
# The clone is looked for at ~/GitHub first, then a few fixed places, under either name. Setup only
# checks those fixed paths and reads those small files; it never lists, opens or changes anything
# else there, and it never asks about Camp. Weak signs are left to aibl-enroll, which asks once.
CAMP_ID = 'repo.agent-native-camp'
CAMP_SAY = ("I can see your Camp folder. I didn't touch it, and setup never will. "
            "Your workbench is its own folder, my-workbench.")
CAMP_REMOTE = re.compile(r'(?:^|[@/])github\.com[:/](?:aibuild-lab/agent-native-camp|[A-Za-z0-9-]+/agent-native-camp-private)(?:\.git)?/?$', re.I)
CAMP_CONTEXT_MARKER = re.compile(r'^camp-context-repo-schema=\d+$')
CAMP_PARENTS = (('GitHub',), (), ('Documents', 'GitHub'), ('Documents',), ('Desktop',),
                ('OneDrive', 'Documents', 'GitHub'), ('OneDrive', 'Documents'), ('OneDrive', 'Desktop'))
CAMP_NAMES = ('agent-native-camp', 'agent-native-camp-private')
# ~/.aibl/camp.json: the one record, shared with the template's aibl-enroll, that the Camp line was
# said or the Camp question answered. Once it exists, neither surface asks or says it again.
CAMP_RECORD = ('.aibl', 'camp.json')
CAMP_RECORD_SCHEMA = 'aibl.camp-answer/v1'


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


def template_version(folder):
    """The template's own version stamp (.aibl/template.json), when it ships one. Step 10 of the prompt reports it;
    without it here the assistant goes hunting through the workbench for a number that may not exist."""
    try:
        meta = json.loads((folder / '.aibl' / 'template.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    value = meta.get('version') if isinstance(meta, dict) else None
    return value if isinstance(value, str) and value else None


def skills_present(folder):
    found = {}
    for app_dir in ('.claude/skills', '.agents/skills'):
        found[app_dir] = [s for s in SKILLS if (folder / app_dir / s / 'SKILL.md').is_file()]
    return found


def left_behind(folder):
    """What a workbench cloned back from GitHub is missing, in words for the student. Looks only."""
    say = LEFT_BEHIND
    team_hq = (folder / 'work' / 'team-hq').is_dir() or (folder / '.aibl' / 'programs' / 'agent-team-hq.json').is_file()
    if team_hq:
        say += '\n' + LEFT_BEHIND_NIGHT_SHIFT
    return {'what': list(LEFT_BEHIND_PATHS), 'team_hq_night_shift': team_hq, 'say': say}


def _small_text(path, limit):
    """A small regular file's text, or None. Never follows a link."""
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
            return None
        return path.read_text(encoding='utf-8')
    except (OSError, ValueError):
        return None


def camp_descriptor(folder):
    text = _small_text(Path(folder) / '.aibl' / 'repository.json', 64 * 1024)
    try:
        meta = json.loads(text) if text is not None else None
    except ValueError:
        return False
    return isinstance(meta, dict) and meta.get('id') == CAMP_ID


def camp_remote(folder):
    """True when the folder's own .git/config has a remote naming Camp or a private Camp mirror.
    Reads that one file as text; runs no Git command there."""
    text = _small_text(Path(folder) / '.git' / 'config', 64 * 1024)
    in_remote = False
    for line in (text or '').splitlines():
        section = re.match(r'\s*\[\s*([A-Za-z]+)', line)
        if section:
            in_remote = section.group(1).lower() == 'remote'
            continue
        url = re.match(r'\s*url\s*=\s*"?([^"\s]+)"?\s*$', line, re.I)
        if in_remote and url and CAMP_REMOTE.search(url.group(1)):
            return True
    return False


def camp_context_marker(folder):
    text = _small_text(Path(folder) / '.camp-context-repo', 1024)
    return bool(text is not None and CAMP_CONTEXT_MARKER.match(text.strip()))


def camp_folder(home):
    """The first folder with a verified Camp sign (a Camp clone, else ~/context-repo); else None."""
    home = Path(home)
    for parent in CAMP_PARENTS:
        for name in CAMP_NAMES:
            folder = home.joinpath(*parent, name)
            if folder.is_dir() and (camp_descriptor(folder) or camp_remote(folder)):
                return str(folder)
    context = home / 'context-repo'
    if context.is_dir() and camp_context_marker(context):
        return str(context)
    return None


def camp_record(home):
    """None when there is no record; the record when it is Camp's; {'unreadable': True} otherwise."""
    path = Path(home).joinpath(*CAMP_RECORD)
    if not path.exists() and not path.is_symlink():
        return None
    text = _small_text(path, 4096)
    try:
        record = json.loads(text) if text is not None else None
    except ValueError:
        record = None
    if not isinstance(record, dict) or record.get('schema') != CAMP_RECORD_SCHEMA or not isinstance(record.get('took_camp'), bool):
        return {'unreadable': True}
    return record


def camp_notice(home):
    """The Camp line for this run, at most once ever. Writes the shared record when it gives one."""
    folder = camp_folder(home)
    if not folder:
        return None
    record = camp_record(home)
    if record is not None and (record.get('unreadable') or record.get('told') is True):
        return None
    path = Path(home).joinpath(*CAMP_RECORD)
    if path.parent.is_symlink() or path.is_symlink():
        return None
    try:
        write(path, {'schema': CAMP_RECORD_SCHEMA, 'took_camp': True, 'told': True, 'by': 'aibl-installer',
                     'recorded_at': datetime.datetime.now(datetime.timezone.utc).isoformat()})
    except OSError:
        return None  # without the record the line could repeat, so it is not said
    return {'folder': folder, 'say': CAMP_SAY}


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
        try:
            verify_existing(folder, full, runner)
        except SetupError as exc:
            raise SetupError(f'A folder named {name} is already at {folder} and is not linked to github.com/{full} '
                             f'({exc}). Nothing was changed. Rename that folder (for example {name}-old), or choose another name with --repo-name, and run this again.')
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
        'template': {**source, 'version': template_version(folder)},
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
    if status == 'cloned_existing':
        receipt['left_behind'] = left_behind(folder)
    camp = camp_notice(home)
    if camp:
        receipt['camp'] = camp
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
