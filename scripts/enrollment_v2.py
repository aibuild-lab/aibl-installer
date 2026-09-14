"""Confirmed enrollment into a standalone workbench. No PR updates or native-use claims."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import uuid
from pathlib import Path

from course_setup import ROOT, SetupError, command, registry, setup_lock, write
from release_files import under
from standalone_setup import private_owner
from workbench_packages import compose, filesystem_mode, load_lock, snapshot, verify


def installed_record(root):
    value = json.loads(under(root, '.aibl/family.json').read_text())
    if (value.get('schema_version') != 'aibl.installed-family/v1'
            or value.get('family', {}).get('schema_version') != 'aibl.family-lock/v2'
            or not {'agent-workbench', 'workbench-core'} <= set(value.get('packages', {}))):
        raise SetupError('Use the setup and enrollment route recorded by this workbench.', 'local_state')
    return value


def identity(root, runner=command):
    user = json.loads(runner(['gh', 'api', 'user']))
    remote = runner(['git', 'remote', 'get-url', 'origin'], cwd=root)
    match = re.fullmatch(r'(?:https://github.com/|git@github.com:)([^/]+/[^/]+?)(?:\.git)?', remote)
    if not match:
        raise SetupError('Use a verified GitHub workbench origin.')
    private_owner(match[1], user, runner)
    return user, match[1]


def available(root, runner=command, reg=None):
    from enroll import access
    current = installed_record(root)
    user, full = identity(root, runner)
    rows = []
    for p in (reg or registry())['programs']:
        if p.get('kind') == 'foundation':
            continue
        product = p['id']
        if product not in current['family']['packages']:
            continue
        publisher = 'aibuild-lab/agent-workforce' if product == 'agent-workforce' else p['publisher']
        if access(publisher, runner) != 'readable':
            continue
        pin = current['packages'].get(product)
        rows.append({'id': product, 'label': p['label'].split(' (')[0], 'publisher': publisher,
                     'access': 'readable', 'installed': pin['version'] if pin else None,
                     'state': 'Already connected' if pin else 'Ready to add',
                     'supported': product == 'agent-workforce'})
    return {'status': 'checked', 'workbench': str(root), 'repository': full,
            'github_username': user['login'], 'programs': rows, 'chosen': [],
            'help': 'Missing a program? Give the course team its name and your GitHub username: ' + user['login'] + '. Access and invitation status need their own check.'}


def git_state(root, runner=command):
    """Fingerprint Git and all untracked work without refreshing the index."""
    def git(*args):
        return runner(['git', '--no-optional-locks', *args], cwd=root)
    index = Path(git('rev-parse', '--git-path', 'index'))
    if not index.is_absolute():
        index = Path(root) / index
    untracked = {}
    for name in filter(None, git('ls-files', '--others', '--exclude-standard', '-z').split('\0')):
        path = Path(root) / name
        info = path.lstat()
        content = os.readlink(path).encode() if stat.S_ISLNK(info.st_mode) else path.read_bytes()
        untracked[name] = {'sha256': hashlib.sha256(content).hexdigest(), 'mode': stat.S_IMODE(info.st_mode)}
    return {'head': git('rev-parse', 'HEAD'), 'branch': git('symbolic-ref', '--quiet', '--short', 'HEAD'),
            'origin': git('remote', 'get-url', 'origin'),
            'index': hashlib.sha256(index.read_bytes()).hexdigest() if index.exists() else None,
            'diff': hashlib.sha256(git('diff', '--binary', 'HEAD').encode()).hexdigest(),
            'untracked': untracked}


def connection(bundles, family, product):
    manifest, payload = verify(bundles, product, family['packages'][product])
    if product == 'agent-essentials':
        name = 'course/essentials/START-HERE.md'
        if name not in payload:
            raise SetupError('Essentials support has no verified first action.')
        return {'first_action': {'path': name, 'prompt': 'Open the lesson 8 support and follow the YouTube transcript blueprint.'}, 'native': {}}
    name = 'course/workforce/connection.json'
    if name not in payload:
        raise SetupError('Workforce package has no verified connection manifest.')
    value = json.loads(payload[name])
    if (set(value) != {'schema_version', 'product', 'requires', 'first_action', 'native'}
            or value['schema_version'] != 'aibl.program-connection/v1'
            or value['product'] != product or value['requires'] != ['agent-workbench', 'workbench-core']):
        raise SetupError('Workforce connection contract is invalid.')
    first = value['first_action']
    if (not isinstance(first, dict) or set(first) != {'path', 'prompt'}
            or first['path'] not in payload or not isinstance(first['prompt'], str) or not first['prompt'].strip()):
        raise SetupError('Workforce first action is not an included verified file.')
    if not isinstance(value['native'], dict) or set(value['native']) != {'claude', 'codex'}:
        raise SetupError('Workforce must declare both supported native exposures.')
    for paths in value['native'].values():
        if not isinstance(paths, list) or not paths or any(not isinstance(p, str) or p not in payload for p in paths) or len(paths) != len(set(paths)):
            raise SetupError('Native exposure must name exact verified package paths.')
    return {'first_action': first, 'native': value['native']}


def inputs(lock_path, lock_sha256, bundles, root):
    family = load_lock(lock_path, lock_sha256, ROOT)
    if family['schema_version'] != 'aibl.family-lock/v2':
        raise SetupError('Confirmed enrollment requires the standalone family-lock v2 route.')
    current = installed_record(root)
    if current['family']['installer_revision'] != family['installer_revision']:
        raise SetupError('Enrollment cannot update the retained installer. Use the student update PR route.')
    if any(family['packages'].get(p) != pin for p, pin in current['packages'].items()):
        raise SetupError('Enrollment would update installed packages. Use the student update PR route.')
    return family


def preview(root, product, lock_path, lock_sha256, bundles, *, runner=command, state_root=None):
    if product not in ('agent-workforce', 'agent-essentials'):
        raise SetupError('This release supports Workforce and optional lesson-8 Essentials support only.')
    root = Path(root).resolve()
    current = installed_record(root)
    user, full = identity(root, runner)
    family = inputs(lock_path, lock_sha256, bundles, root)
    if product not in family['packages']:
        raise SetupError('Selected program has no independently admitted package in this family.')
    runner(['gh', 'api', 'repos/' + family['packages'][product]['publisher']])
    if product in current['packages']:
        return {'status': 'already_connected', 'program': product, 'native_verification': 'pending'}
    contract = connection(bundles, family, product)
    before = git_state(root, runner)
    comparison = compose(root, bundles, family, [product], preview=True)
    if git_state(root, runner) != before:
        raise SetupError('Work changed while preparing enrollment. Run preview again.')
    if comparison['status'] != 'ready':
        return {'status': 'needs_review', 'program': product, 'preview': comparison}
    state_root = Path(state_root) if state_root else Path.home() / '.aibl' / 'enrollment'
    plan_id = uuid.uuid4().hex
    value = {'schema_version': 'aibl.enrollment-plan/v1', 'plan_id': plan_id, 'phase': 'previewed',
             'workbench': str(root), 'repository': full, 'github_username': user['login'], 'program': product,
             'family_lock': str(Path(lock_path).resolve()), 'family_sha256': lock_sha256,
             'family_bundles': str(Path(bundles).resolve()), 'family': family,
             'git_state': before, 'preview': comparison, 'connection': contract,
             'before_marker': snapshot(root, '.aibl/family.json')}
    with setup_lock(state_root, plan_id):
        write(state_root / (plan_id + '.json'), value)
    return {'status': 'previewed', 'plan_id': plan_id, 'program': product, 'preview': comparison,
            'first_action': contract['first_action'], 'confirmation': 'After student confirmation, apply this exact plan_id.'}


def finish(root, plan, result):
    current = installed_record(root)
    for product, pin in plan['family']['packages'].items():
        if product in current['packages'] and current['packages'][product] != pin:
            raise SetupError('Installed package identity differs after enrollment.')
    if current['packages'].get(plan['program']) != plan['family']['packages'][plan['program']]:
        raise SetupError('Selected package was not installed.')
    for name, row in current['files'].items():
        if row['product'] == plan['program'] and snapshot(root, name) != {'hash': row['sha256'], 'mode': filesystem_mode(row['mode'])}:
            raise SetupError('Installed program files differ; preserve them and review recovery.')
    return {'status': 'installed', 'plan_id': plan['plan_id'], 'program': plan['program'],
            'version': current['packages'][plan['program']]['version'], 'rollback': result.get('rollback'),
            'native_verification': 'pending', 'first_action': plan['connection']['first_action'],
            'native_paths': plan['connection']['native'],
            'next': 'Refresh your selected app, discover the installed capabilities and perform the first action. Native use remains unverified.'}


def completed_backup(root, plan):
    """Reconcile a lost apply response against the engine's completed transaction."""
    before = {change['path']: change['actual'] for change in plan['preview']['changes']}
    before['.aibl/family.json'] = plan['before_marker']
    matches = []
    directory = under(root, '.aibl-local/family-backups')
    for candidate in directory.iterdir():
        if not re.fullmatch('[0-9]+', candidate.name) or candidate.is_symlink():
            continue
        path = candidate / 'transaction.json'
        if not path.is_file() or path.is_symlink():
            continue
        tx = json.loads(path.read_text())
        if tx.get('complete') and tx.get('before') == before and all(snapshot(root, n) == value for n, value in tx.get('after', {}).items()):
            matches.append(candidate.name)
    if len(matches) != 1:
        raise SetupError('Installed bytes exist but their completed recovery receipt is ambiguous. Preserve the workbench for review.')
    return {'rollback': matches[0]}


def apply_plan(root, plan_id, *, runner=command, state_root=None, family_lock=None, family_sha256=None, family_bundles=None):
    if not re.fullmatch('[0-9a-f]{32}', plan_id or ''):
        raise SetupError('Use the exact enrollment plan ID returned by preview.')
    root = Path(root).resolve()
    state_root = Path(state_root) if state_root else Path.home() / '.aibl' / 'enrollment'
    with setup_lock(state_root, plan_id):
        path = state_root / (plan_id + '.json')
        if path.is_symlink():
            raise SetupError('Enrollment plan is linked. Preserve it for review.')
        plan = json.loads(path.read_text())
        if plan.get('schema_version') != 'aibl.enrollment-plan/v1' or plan.get('plan_id') != plan_id or plan.get('workbench') != str(root):
            raise SetupError('Enrollment plan identity differs.')
        supplied = (family_lock, family_sha256, family_bundles)
        if any(supplied):
            if not all(supplied) or [str(Path(family_lock).resolve()), family_sha256, str(Path(family_bundles).resolve())] != [plan['family_lock'], plan['family_sha256'], plan['family_bundles']]:
                raise SetupError('Use the exact family inputs recorded by preview.')
        user, full = identity(root, runner)
        if full != plan['repository'] or user['login'] != plan['github_username']:
            raise SetupError('GitHub identity changed since preview.')
        family = load_lock(plan['family_lock'], plan['family_sha256'], ROOT)
        if family != plan['family']:
            raise SetupError('Family changed since preview.')
        runner(['gh', 'api', 'repos/' + family['packages'][plan['program']]['publisher']])
        contract = connection(plan['family_bundles'], family, plan['program'])
        if contract != plan['connection']:
            raise SetupError('Connection metadata changed since preview.')
        if under(root, '.aibl-local/family-transaction.json').exists():
            raise SetupError('Enrollment was interrupted. Run package recover, then retry this plan.', 'recovery_required')
        if plan['phase'] == 'installed':
            return finish(root, plan, plan['result'])
        if plan['phase'] == 'applying' and installed_record(root)['packages'].get(plan['program']) == family['packages'][plan['program']]:
            result = finish(root, plan, completed_backup(root, plan))
        else:
            inputs(plan['family_lock'], plan['family_sha256'], plan['family_bundles'], root)
            if git_state(root, runner) != plan['git_state']:
                raise SetupError('Git or student work changed since preview. Create and confirm a new preview.')
            comparison = compose(root, plan['family_bundles'], family, [plan['program']], preview=True)
            if comparison != plan['preview']:
                raise SetupError('Package or local files changed since preview. Create and confirm a new preview.')
            plan['phase'] = 'applying'
            write(path, plan)
            installed = compose(root, plan['family_bundles'], family, [plan['program']])
            result = finish(root, plan, installed)
        plan['phase'] = 'installed'
        plan['result'] = result
        write(path, plan)
        return result
