"""Journaled normalization of reviewed supplied files before a Git fast-forward.

Caller holds both update-operation and package guards. Never stash/reset, touch
student-owned paths, discard changed bytes, or remove a Git lock after failure.
"""
import re
import subprocess
from pathlib import Path

import workbench_packages as packages
from release_files import ReleaseError, atomic, digest, encoded, under

LIMIT = 32 * 1024 * 1024
PREFIX = '.aibl-local/update-sync/'


def location(root, operation, name):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', operation):
        raise ReleaseError('Invalid local synchronization operation')
    return under(root, PREFIX + operation + '/' + name)


def git_bytes(root, *args):
    result = subprocess.run(['git', *args], cwd=root, capture_output=True)
    if result.returncode or len(result.stdout) > LIMIT:
        raise ReleaseError('Cannot read bounded local Git object for synchronization')
    return result.stdout


def tracked(root, revision, name):
    under(root, name)
    if not re.fullmatch('[0-9a-f]{40}', revision):
        raise ReleaseError('Exact local synchronization revision required')
    listing = git_bytes(root, 'ls-tree', '-z', revision, '--', name)
    if not listing:
        return None, None
    if not listing.endswith(b'\0') or listing.count(b'\0') != 1:
        raise ReleaseError('Ambiguous tracked synchronization path')
    metadata, actual = listing[:-1].split(b'\t', 1)
    mode, kind, oid = metadata.decode('ascii').split()
    if actual.decode('utf-8') != name or kind != 'blob' or mode not in ('100644', '100755'):
        raise ReleaseError('Nonregular tracked synchronization path')
    raw = git_bytes(root, 'cat-file', 'blob', oid)
    return {'hash': digest(raw), 'mode': packages.filesystem_mode(int(mode, 8) & 0o777)}, raw


def retained(path, raw):
    if path.exists():
        if not path.is_file() or path.stat().st_size > LIMIT or path.read_bytes() != raw:
            raise ReleaseError('Retained synchronization bytes differ; preserve the operation')
    else:
        atomic(path, raw, 0o600)


def pending_record(root, state, plan_sha):
    return {'schema_version': 'aibl.student-update-sync-pending/v1',
            'operation': state['operation'], 'workbench': str(root),
            'plan_sha256': plan_sha, 'merge_revision': state['merge_revision']}


def finish(root, state, git):
    """Reconcile a lost final-clear response without replaying normalization."""
    pending = under(root, packages.SYNC_PENDING)
    if not pending.exists():
        return
    expected = encoded(pending_record(root, state, state.get('sync_plan_sha256')))
    if pending.stat().st_size > LIMIT or pending.read_bytes() != expected:
        raise ReleaseError('Another or damaged synchronization journal must be preserved')
    if state['stage'] not in ('local_synchronized', 'observation_recorded', 'verified') or state.get('local_synchronized_revision') != state['merge_revision']:
        raise ReleaseError('Do not clear unfinished synchronization')
    if git(root, 'rev-parse', 'HEAD') != state['merge_revision']:
        raise ReleaseError('Local HEAD changed before synchronization closeout; preserve the journal')
    pending.unlink()


def plan_for(root, state):
    # These keys are produced from supplied ownership rows, never seed/student rows.
    names = sorted(set(state['managed_before']) | set(state['managed_after']))
    if not names or len(names) > 4096 or not set(names) <= set(state['transition_before']):
        raise ReleaseError('Synchronization supplied-path inventory differs')
    rows = {}
    for name in names:
        before = state['transition_before'][name]
        old, _ = tracked(root, state['local_revision'], name)
        after, _ = tracked(root, state['merge_revision'], name)
        if after != state['transition_after'][name]:
            raise ReleaseError('Approved merge differs from reviewed supplied bytes')
        rows[name] = {'before': before, 'tracked': old, 'after': after}
    return {'schema_version': 'aibl.student-update-sync/v1',
            'operation': state['operation'], 'workbench': str(root),
            'local_revision': state['local_revision'],
            'merge_revision': state['merge_revision'], 'files': rows}


def verify_retained(root, plan):
    for name, row in plan['files'].items():
        if row['before'] is not None:
            path = location(root, plan['operation'], 'before/' + name)
            if not path.is_file() or path.stat().st_size > LIMIT or digest(path.read_bytes()) != row['before']['hash']:
                raise ReleaseError('Superseded local synchronization bytes are missing or damaged')


def working_fence(root, state, plan, merged=False):
    for name, before in state['transition_before'].items():
        current = packages.snapshot(root, name)
        if name in plan['files']:
            row = plan['files'][name]
            allowed = (row['after'],) if merged else (row['before'], row['tracked'])
        else:
            allowed = (state['transition_after'][name],) if merged else (before,)
        if current not in allowed:
            raise ReleaseError('Local learning or supplied bytes changed during synchronization; preserve later edits: ' + name)


def index_fence(root, git):
    if git(root, 'diff', '--cached', '--name-only', '-z', 'HEAD', '--'):
        raise ReleaseError('Index contains staged work or an interrupted Git transition; preserve it for review')


def apply_file(root, name, wanted, raw):
    if wanted is None:
        under(root, name).unlink()
    else:
        atomic(under(root, name), raw, wanted['mode'])


def restore_normalized(root, state, plan, git):
    # A failed ordinary merge should not leave previously enrolled files absent.
    # A partial Git/index transition or later edit remains held, never reset.
    if git(root, 'rev-parse', 'HEAD') != state['local_revision']:
        raise ReleaseError('Git advanced during synchronization; resume the same operation')
    index_fence(root, git)
    working_fence(root, state, plan)
    for name, row in plan['files'].items():
        actual = packages.snapshot(root, name)
        if actual == row['before']:
            continue
        if actual != row['tracked']:
            raise ReleaseError('Later edit prevents restoring normalized bytes')
        raw = None
        if row['before'] is not None:
            raw = location(root, state['operation'], 'before/' + name).read_bytes()
            if digest(raw) != row['before']['hash']:
                raise ReleaseError('Retained synchronization bytes changed')
        apply_file(root, name, row['before'], raw)


def materialize(root, state, save_state, git):
    """Normalize exact reviewed supplied bytes, fast-forward, reconcile retries.

    Saved before-bytes and an immutable plan precede any working-file change.
    A retry can see before/tracked mixtures during normalization, or the exact
    merged tree after a lost Git response. Other changes stop without discard.
    """
    root = Path(root).resolve()
    plan = plan_for(root, state)
    plan_path = location(root, state['operation'], 'plan.json')
    plan_sha = digest(encoded(plan))
    if state.get('sync_plan_sha256') not in (None, plan_sha):
        raise ReleaseError('Local synchronization review identity changed')
    pending = under(root, packages.SYNC_PENDING)
    pending_bytes = encoded(pending_record(root, state, plan_sha))
    if pending.exists() and (pending.stat().st_size > LIMIT or pending.read_bytes() != pending_bytes):
        raise ReleaseError('Another or damaged synchronization journal must be preserved')
    head = git(root, 'rev-parse', 'HEAD')
    if head not in (state['local_revision'], state['merge_revision']):
        raise ReleaseError('Local HEAD advanced; preserve unpushed or later work')
    index_fence(root, git)
    if plan_path.exists():
        if plan_path.stat().st_size > LIMIT or plan_path.read_bytes() != encoded(plan):
            raise ReleaseError('Local synchronization journal differs')
        verify_retained(root, plan)
    else:
        if head != state['local_revision'] or any(packages.snapshot(root, n) != value for n, value in state['transition_before'].items()):
            raise ReleaseError('Local HEAD, supplied files or incoming destinations changed before synchronization journal')
        git(root, 'merge-base', '--is-ancestor', state['local_revision'], state['base_revision'])
        folder = location(root, state['operation'], 'before')
        folder.mkdir(parents=True, mode=0o700, exist_ok=True)
        for name, row in plan['files'].items():
            if row['before'] is not None:
                raw = under(root, name).read_bytes()
                if digest(raw) != row['before']['hash']:
                    raise ReleaseError('Supplied bytes changed while preserving synchronization backup')
                retained(location(root, state['operation'], 'before/' + name), raw)
        if any(packages.snapshot(root, name) != value for name, value in state['transition_before'].items()):
            raise ReleaseError('Supplied bytes changed before synchronization journal; preserve later edits')
        retained(plan_path, encoded(plan))
        verify_retained(root, plan)
    state.update(stage='local_sync_pending', sync_plan_sha256=plan_sha)
    save_state(state)
    # Durable interleaving protection survives process-guard release on a crash.
    retained(pending, pending_bytes)
    if head == state['merge_revision']:
        working_fence(root, state, plan, merged=True)
        return
    working_fence(root, state, plan)
    for name, row in plan['files'].items():
        actual = packages.snapshot(root, name)
        if actual == row['tracked']:
            continue
        if actual != row['before']:
            raise ReleaseError('Later edit prevents supplied normalization')
        wanted, raw = tracked(root, state['local_revision'], name)
        if wanted != row['tracked']:
            raise ReleaseError('Original tracked object changed')
        apply_file(root, name, wanted, raw)
    index_fence(root, git)
    if git(root, 'rev-parse', 'HEAD') != state['local_revision']:
        raise ReleaseError('Local HEAD changed during normalization; preserve recovery records')
    # Recheck all paths before handing the exact known state to Git.
    if any(packages.snapshot(root, n) != row['tracked'] for n, row in plan['files'].items()):
        raise ReleaseError('Normalized supplied bytes changed before fast-forward')
    try:
        git(root, 'merge', '--ff-only', '--no-overwrite-ignore', state['merge_revision'])
    except Exception:
        if git(root, 'rev-parse', 'HEAD') != state['merge_revision']:
            restore_normalized(root, state, plan, git)
            raise
    if git(root, 'rev-parse', 'HEAD') != state['merge_revision']:
        raise ReleaseError('Local fast-forward is not confirmed')
    index_fence(root, git)
    working_fence(root, state, plan, merged=True)
