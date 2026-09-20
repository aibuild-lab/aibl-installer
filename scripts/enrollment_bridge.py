"""Explicit first-enrollment admission for known Essentials templates."""
import json
import tempfile
from pathlib import Path

from course_setup import ROOT, SetupError
from release_files import atomic, encoded, under
from workbench_packages import snapshot, filesystem_mode

PRODUCTS = ['agent-workbench', 'workbench-core', 'agent-workforce']


def baseline(root, revision=None):
    root = Path(root)
    if under(root, '.aibl/family.json').exists():
        raise SetupError('Template adoption requires an unconnected workbench.')
    if list(under(root, '.aibl').glob('installed-*.json')) or under(root, '.aibl/distribution.json').exists():
        raise SetupError('Historical course records need their original supported migration route.')
    rows = json.loads((Path(__file__).with_name('enrollment_templates.json')).read_text())['snapshots']
    for row in rows:
        if revision and row['revision'] != revision:
            continue
        if all(snapshot(root, name) == {'hash': item['sha256'], 'mode': filesystem_mode(item['mode'])}
               for name, item in row['files'].items()):
            return row
    raise SetupError('Unsupported template or edited supplied skills. Preserve changes for review; do not replace skills by hand.')


def prepare(root, distribution, sha, harness, *, state_root=None):
    from frozen_family import acquire
    if harness not in ('claude', 'codex'):
        raise SetupError('Select the existing workbench client explicitly: claude or codex.')
    row = baseline(root)
    value = admitted_distribution(distribution, sha)
    expected = Path.home() / '.aibl/installers' / value['installer']['revision']
    if Path(ROOT).resolve() != expected.resolve():
        raise SetupError('Use the exact retained installer from the official Workforce handoff.')
    parent = Path(state_root) if state_root else Path.home() / '.aibl/enrollment'
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    folder = Path(tempfile.mkdtemp(prefix='bridge-inputs-', dir=parent))
    saved = folder / 'distribution.json'
    atomic(saved, encoded(value), 0o600)
    inputs = acquire(saved, sha, ROOT, folder / 'bundles', PRODUCTS)
    return inputs, {'distribution': str(saved), 'distribution_sha256': sha,
                    'harness': harness, 'template_revision': row['revision']}


def validate(plan):
    bridge = plan['bridge']
    value = admitted_distribution(bridge['distribution'], bridge['distribution_sha256'])
    if value['family_lock'] != plan['family'] or bridge['harness'] not in ('claude', 'codex'):
        raise SetupError('Bridge distribution or selected client changed since preview.')
    return value


def admit(root, plan):
    """Retain official admission only after confirmation, with expiry checked again."""
    from workbench_distribution import retain, cached_inputs
    validate(plan)
    bridge = plan['bridge']
    folder, association, value = retain(root, plan['repository'], ROOT,
        bridge['distribution'], bridge['distribution_sha256'],
        template_revision=bridge['template_revision'])
    cached_inputs(folder, association, value, ROOT, PRODUCTS)


def finish(root, plan):
    from workbench_distribution import read_association
    from workbench_packages import filesystem_mode
    bridge = plan['bridge']
    _, association, value = read_association(root, ROOT, plan['repository'])
    if association['distribution_sha256'] != bridge['distribution_sha256'] or value['family_lock'] != plan['family']:
        raise SetupError('Installed bridge association differs.')
    record = json.loads(under(root, '.aibl/family.json').read_text())
    for name, row in record['files'].items():
        if row['policy'] == 'supplied' and snapshot(root, name) != {'hash': row['sha256'], 'mode': filesystem_mode(row['mode'])}:
            raise SetupError('Installed supplied file differs: ' + name)
    paths = plan['connection']['native'][bridge['harness']]
    expected = ('.agents' if bridge['harness'] == 'codex' else '.claude') + '/skills/aibl-workforce/SKILL.md'
    if expected not in paths:
        raise SetupError('Workforce is missing the selected client entry skill.')


def available(root, runner):
    from enrollment_v2 import identity
    from enroll import access
    user, full = identity(root, runner)
    try:
        row = baseline(root)
        compatibility = 'supported_template'
    except ValueError as error:
        compatibility = str(error)
    readable = access('aibuild-lab/agent-workforce', runner) == 'readable'
    return {'status': 'checked', 'workbench': str(root), 'repository': full,
            'github_username': user['login'], 'chosen': [],
            'compatibility': compatibility,
            'programs': [{'id': 'agent-workforce', 'label': 'Agent Workforce',
                         'publisher': 'aibuild-lab/agent-workforce', 'access': 'readable',
                         'installed': None, 'supported': False,
                         'state': 'Independent distribution preview required'}] if readable else [],
            'help': 'Obtain the official Workforce handoff and independently admitted distribution. Repository access is not proof of available delivery; invitation status is unknown.'}


def admitted_distribution(path, sha):
    from frozen_family import load_distribution
    value = load_distribution(path, sha, ROOT)
    required = {'scripts/enrollment_bridge.py', 'scripts/enrollment_templates.json'}
    if not required <= set(value['installer']['files']):
        raise SetupError('Official distribution does not admit the enrollment bridge files.')
    return value
