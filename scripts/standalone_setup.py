"""Verified standalone seeding. Setup progress lives outside the student repository."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from course_setup import (HARNESSES, SetupError, check_tools, command, remote_matches,
                          repo_name, safe_workspace, setup_lock, verify_existing, write)
from release_files import under
from workbench_packages import compose, filesystem_mode, recover, validate_family, verify

BASE_PRODUCTS = ('agent-workbench', 'workbench-core')


def private_owner(full, user, runner=command):
    meta = json.loads(runner(['gh', 'api', 'repos/' + full]))
    if (not meta.get('private') or meta.get('full_name', '').lower() != full.lower()
            or meta.get('owner', {}).get('login', '').lower() != user['login'].lower()):
        raise SetupError('Use a private workbench owned by the signed-in GitHub account.', 'permission')
    return meta


def signed_in(harness, runner=command):
    value = runner(HARNESSES[harness]['status'])
    valid = json.loads(value).get('loggedIn') if harness == 'claude' else ('logged in' in value.lower() or 'signed in' in value.lower())
    if not valid:
        raise SetupError('Sign in to the selected app, then rerun setup.', 'authentication_missing')


def established(folder, full, user, runner=command):
    """Only read local state and GitHub. Even the Git index is left untouched."""
    verify_existing(folder, full, runner)
    private_owner(full, user, runner)
    marker = under(folder, '.aibl/family.json')
    if marker.is_symlink() or not marker.is_file():
        raise SetupError('Existing repository is not a verified workbench. Preserve it for review.', 'local_state')
    record = json.loads(marker.read_text())
    if (record.get('schema_version') != 'aibl.installed-family/v1'
            or not set(BASE_PRODUCTS) <= set(record.get('packages', {}))
            or record.get('family', {}).get('schema_version') != 'aibl.family-lock/v2'):
        raise SetupError('Existing workbench needs its own retained setup or explicit migration.', 'local_state')
    validate_family(record['family'])
    if any(record['family']['packages'].get(p) != pin for p, pin in record['packages'].items()):
        raise SetupError('Installed workbench identity is inconsistent; preserve it for review.', 'local_state')
    return record


def seed_snapshot(folder, expected, partial=False, modes=None):
    actual = {}
    for base, dirs, files in os.walk(folder, followlinks=False):
        dirs[:] = [d for d in dirs if d not in ('.git', '.aibl-local')]
        for name in dirs + files:
            path = Path(base) / name
            if path.is_symlink():
                raise SetupError('Interrupted setup contains a linked path. Preserve it for review.')
        for name in files:
            path = Path(base) / name
            relative = path.relative_to(folder).as_posix()
            actual[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
            if modes and relative in modes and (path.stat().st_mode & 0o777) != filesystem_mode(modes[relative]):
                raise SetupError('Interrupted setup contains changed file permissions. Preserve them for review.')
    if (not partial and actual != expected) or any(name not in expected or value != expected[name] for name, value in actual.items()):
        raise SetupError('Interrupted setup contains changed or additional files. Preserve them for review.', 'local_state')


def setup_standalone(workspace, name, family, bundles, *, state_root=None,
                     runner=command, harness='claude', no_launch=False):
    if harness not in HARNESSES:
        raise SetupError('Choose claude or codex.')
    workspace = safe_workspace(workspace)
    name = repo_name(name)
    folder = workspace / name
    state_root = Path(state_root) if state_root else Path.home() / '.aibl' / 'setup'
    runner(['gh', 'auth', 'status'])
    user = json.loads(runner(['gh', 'api', 'user']))
    if not isinstance(user.get('login'), str) or not user.get('id'):
        raise SetupError('GitHub account identity is unavailable.', 'authentication_missing')
    full = user['login'] + '/' + name
    signed_in(harness, runner)
    # This exit deliberately precedes locks, tool setup, composition and writes.
    if folder.exists() or folder.is_symlink():
        record = established(folder, full, user, runner)
        return {'status': 'already_initialized', 'workspace': str(folder), 'repository': full,
                'student_files_changed': False, 'harness': harness,
                'packages': record['packages'], 'native_verification': 'pending',
                'next': 'Open your workbench in your selected app; use aibl-personalize or aibl-enroll.'}
    versions = check_tools(runner, harness=harness)
    validate_family(family)
    if family.get('schema_version') != 'aibl.family-lock/v2' or not set(BASE_PRODUCTS) <= set(family.get('packages', {})):
        raise SetupError('Standalone setup requires the reviewed workbench and core tuple.')
    expected = {}
    modes = {'.aibl/family.json': 0o644}
    for product in BASE_PRODUCTS:
        manifest, _ = verify(bundles, product, family['packages'][product])
        for row in manifest['files']:
            if row['path'] in expected:
                raise SetupError('Starter and core claim the same file.')
            expected[row['path']] = row['sha256']
            modes[row['path']] = row['mode']
    identity = hashlib.sha256(json.dumps(family, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    with setup_lock(state_root, name):
        statefile = state_root / (name + '-standalone.json')
        if statefile.is_symlink():
            raise SetupError('Setup progress is linked; preserve it for review.')
        stage = workspace / ('.' + name + '-seed-in-progress')
        state = json.loads(statefile.read_text()) if statefile.exists() else None
        if state:
            if (state.get('schema_version') != 'aibl.standalone-setup/v1' or state.get('repository') != full
                    or state.get('family_sha256') != identity or state.get('stage') != str(stage)):
                raise SetupError('Saved setup identity differs. Resume its original verified inputs.')
        else:
            if stage.exists() or stage.is_symlink():
                raise SetupError('A staging folder already exists without matching setup progress. Preserve it.')
            state = {'schema_version': 'aibl.standalone-setup/v1', 'repository': full,
                     'family_sha256': identity, 'stage': str(stage), 'phase': 'creation_intent'}
            write(statefile, state)
        try:
            meta = private_owner(full, user, runner)
        except SetupError as exc:
            if exc.reason != 'not_found':
                raise
            if state.get('repository_id'):
                raise SetupError('The previously created repository is unavailable. Check access before retrying.') from exc
            runner(['gh', 'repo', 'create', full, '--private'])
            meta = private_owner(full, user, runner)
        if state.get('repository_id') and state['repository_id'] != meta.get('id'):
            raise SetupError('Repository identity changed since setup. Preserve the staged project.')
        state['repository_id'] = meta.get('id')
        write(statefile, state)
        remote_url = 'https://github.com/' + full + '.git'
        remote_head = runner(['git', 'ls-remote', remote_url, 'refs/heads/*'])
        if remote_head and not state.get('commit'):
            raise SetupError('The private repository already contains work. Choose another name; it was not changed.')
        if stage.is_symlink():
            raise SetupError('Setup staging path is linked.')
        if not stage.exists():
            workspace.mkdir(parents=True, exist_ok=True)
            stage.mkdir()
        if not state.get('seed_files'):
            if (stage / '.aibl-local/family-transaction.json').exists():
                recover(stage)
            marker = stage / '.aibl/family.json'
            partial_expected = dict(expected)
            if marker.exists():
                if marker.is_symlink():
                    raise SetupError('Interrupted seed marker is linked.')
                record = json.loads(marker.read_text())
                if record.get('family') != family or record.get('packages') != {p: family['packages'][p] for p in BASE_PRODUCTS}:
                    raise SetupError('Interrupted seed has a different package identity.')
                partial_expected['.aibl/family.json'] = hashlib.sha256(marker.read_bytes()).hexdigest()
            seed_snapshot(stage, partial_expected, partial=True, modes=modes)
            compose(stage, bundles, family, list(BASE_PRODUCTS))
            expected['.aibl/family.json'] = hashlib.sha256((stage / '.aibl/family.json').read_bytes()).hexdigest()
            state['seed_files'] = expected
            state['phase'] = 'seeded'
            write(statefile, state)
        seed_snapshot(stage, state['seed_files'], modes=modes)
        if not (stage / '.git').exists():
            runner(['git', 'init', '--initial-branch=main'], cwd=stage)
        if 'origin' not in runner(['git', 'remote'], cwd=stage).splitlines():
            runner(['git', 'remote', 'add', 'origin', remote_url], cwd=stage)
        if not remote_matches(runner(['git', 'remote', 'get-url', 'origin'], cwd=stage), full):
            raise SetupError('Staging repository origin changed. Preserve it for review.')
        if not state.get('commit'):
            try:
                head = runner(['git', 'rev-parse', '--verify', 'HEAD'], cwd=stage)
            except SetupError:
                head = None
            if head is None:
                runner(['git', 'config', '--local', 'user.name', user.get('name') or user['login']], cwd=stage)
                runner(['git', 'config', '--local', 'user.email', str(user['id']) + '+' + user['login'] + '@users.noreply.github.com'], cwd=stage)
                runner(['git', 'check-ignore', '--no-index', '.aibl-local/family-history.json'], cwd=stage)
                runner(['git', 'add', '--', *sorted(state['seed_files'])], cwd=stage)
                staged = set(filter(None, runner(['git', 'diff', '--cached', '--name-only', '-z'], cwd=stage).split('\0')))
                if staged != set(state['seed_files']):
                    raise SetupError('The seed index includes unexpected files. Preserve it for review.')
                runner(['git', 'commit', '-m', 'Start my private workbench'], cwd=stage)
                head = runner(['git', 'rev-parse', 'HEAD'], cwd=stage)
            elif runner(['git', 'rev-list', '--count', 'HEAD'], cwd=stage) != '1':
                raise SetupError('Interrupted seed has additional history. Preserve it for review.')
            state['commit'] = head
            state['phase'] = 'committed'
            write(statefile, state)
        committed = set(filter(None, runner(['git', 'ls-tree', '-r', '--name-only', '-z', 'HEAD'], cwd=stage).split('\0')))
        if committed != set(state['seed_files']):
            raise SetupError('The initial commit includes unexpected files. Preserve it for review.')
        if runner(['git', '--no-optional-locks', 'status', '--porcelain'], cwd=stage):
            raise SetupError('Staged workbench has additional Git changes. Preserve them for review.')
        if runner(['git', 'rev-parse', 'HEAD'], cwd=stage) != state['commit']:
            raise SetupError('Staged workbench history changed. Preserve it for review.')
        if remote_head:
            if remote_head.split() != [state['commit'], 'refs/heads/main']:
                raise SetupError('Remote work differs from the prepared start. Preserve both histories.')
        else:
            state['phase'] = 'push_intent'
            write(statefile, state)
            runner(['git', 'push', '-u', 'origin', 'HEAD:refs/heads/main'], cwd=stage)
        readback = runner(['git', 'ls-remote', remote_url, 'refs/heads/*'])
        if readback.split() != [state['commit'], 'refs/heads/main']:
            raise SetupError('Initial push readback is uncertain. Rerun the same setup to reconcile it.')
        private_owner(full, user, runner)
        if folder.exists() or folder.is_symlink():
            raise SetupError('Destination appeared during setup. Preserve both folders for review.')
        stage.rename(folder)
        state['phase'] = 'complete'
        write(statefile, state)
    result = {'status': 'files_ready', 'workspace': str(folder), 'repository': full,
              'harness': harness, 'versions': versions, 'commit': state['commit'],
              'native_verification': 'pending', 'next': 'aibl-personalize'}
    if not no_launch:
        runner([HARNESSES[harness]['cli'], 'Use aibl-personalize in this workbench. Help me choose a useful task and make this context mine.'], cwd=folder, interactive=True)
    return result
