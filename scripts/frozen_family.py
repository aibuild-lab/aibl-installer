"""Acquire verified family bundles from an independently admitted distribution."""
import argparse
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

from github_assets import INSTALLER
from release_files import encoded
from release_discovery import acquire_v2, validate_trust
from workbench_packages import ReleaseError, digest, validate_family

REQUIRED_ENGINE_FILES = {
    'start.sh', 'start.ps1', 'SETUP-PROMPT.md', 'course-options.json',
    'scripts/course_setup.py', 'scripts/enroll.py', 'scripts/release_files.py',
    'scripts/workbench_packages.py', 'scripts/github_assets.py',
    'scripts/release_discovery.py', 'scripts/frozen_family.py',
    'scripts/standalone_setup.py', 'scripts/enrollment_v2.py',
    'scripts/student_updates.py', 'scripts/family_setup_handoff.py',
    'scripts/local_learning_backup.py',
    'scripts/workbench_distribution.py',
    'scripts/student_update_sync.py',
}


def safe_file(name):
    if not isinstance(name, str) or not name or '\\' in name or ':' in name:
        raise ReleaseError('Unsafe distribution file')
    path = PurePosixPath(name)
    if path.is_absolute() or path.as_posix() != name or '..' in path.parts or '.git' in path.parts:
        raise ReleaseError('Unsafe distribution file')
    return name


def exact_digest(value):
    return isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value)


def verify_engine(root, installer, runner=None):
    runner = runner or (lambda args, cwd: subprocess.check_output(args, cwd=cwd, text=True).strip())
    root = Path(root).absolute()
    if root.is_symlink() or (root/'.git').is_symlink() or not root.is_dir():
        raise ReleaseError('Retained installer is missing or linked')
    if Path(runner(['git', 'rev-parse', '--show-toplevel'], root)).resolve() != root.resolve():
        raise ReleaseError('Retained installer is not its own checkout')
    # Compare the stored repository identity; Git may rewrite its transport to SSH.
    if runner(['git', 'config', '--local', '--get', 'remote.origin.url'], root) not in ('https://github.com/'+INSTALLER, 'https://github.com/'+INSTALLER+'.git'):
        raise ReleaseError('Retained installer repository differs')
    if runner(['git', 'rev-parse', 'HEAD'], root) != installer['revision'] or runner(['git', 'status', '--porcelain'], root):
        raise ReleaseError('Use the clean exact retained installer')
    for name, sha in installer['files'].items():
        path = root / safe_file(name)
        cursor = path
        while cursor != root:
            if cursor.is_symlink():
                raise ReleaseError('Linked installer file')
            cursor = cursor.parent
        if not path.is_file() or digest(path.read_bytes()) != sha:
            raise ReleaseError('Retained installer file differs: '+name)


def load_distribution(path, expected_sha256, engine_root, *, runner=None):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ReleaseError('Invalid distribution file')
    raw = path.read_bytes()
    if not exact_digest(expected_sha256) or digest(raw) != expected_sha256:
        raise ReleaseError('Independent distribution digest mismatch')
    value = json.loads(raw)
    if not isinstance(value, dict) or set(value) != {'schema_version', 'installer', 'family_lock', 'family_sha256', 'trust'} or value['schema_version'] != 'aibl.family-distribution/v1' or raw != encoded(value):
        raise ReleaseError('Frozen family distribution contract')
    installer = value['installer']
    if not isinstance(installer, dict) or set(installer) != {'repository', 'revision', 'files'} or installer['repository'] != INSTALLER or not isinstance(installer['revision'], str) or not re.fullmatch('[a-f0-9]{40}', installer['revision']):
        raise ReleaseError('Distribution installer identity')
    files = installer['files']
    if not isinstance(files, dict) or not REQUIRED_ENGINE_FILES <= set(files):
        raise ReleaseError('Distribution installer inventory incomplete')
    for name, sha in files.items():
        safe_file(name)
        if not exact_digest(sha):
            raise ReleaseError('Distribution installer file digest')
    family = validate_family(value['family_lock'])
    if family['schema_version'] != 'aibl.family-lock/v2' or family['installer_revision'] != installer['revision'] or not exact_digest(value['family_sha256']) or digest(encoded(family)) != value['family_sha256']:
        raise ReleaseError('Distribution family binding differs')
    if not isinstance(value['trust'], dict) or set(value['trust']) != set(family['packages']):
        raise ReleaseError('Distribution descriptors must cover its exact family')
    for product, row in value['trust'].items():
        if not isinstance(row, dict) or set(row) != {'descriptor', 'sha256'}:
            raise ReleaseError('Distribution descriptor record')
        trust = validate_trust(row['descriptor'], row['sha256'])
        if trust['product'] != product or trust['index_release']['release_target'] != installer['revision']:
            raise ReleaseError('Distribution descriptor product or engine differs')
    verify_engine(engine_root, installer, runner)
    return value


def acquire(distribution_path, expected_sha256, engine_root, output_root, products, *, github=None, now=None, runner=None):
    """Return family_lock/family_sha256/family_bundles for setup or preview.

    Only selected products are downloaded. The caller must include every package
    its composition needs, including already installed packages during updates.
    """
    value = load_distribution(distribution_path, expected_sha256, engine_root, runner=runner)
    products = list(products)
    if not products or len(products) != len(set(products)) or not set(products) <= set(value['family_lock']['packages']):
        raise ReleaseError('Choose explicit products from the admitted family')
    output = Path(output_root).expanduser().absolute()
    if '..' in output.parts:
        raise ReleaseError('Acquisition destination contains traversal')
    if output.exists() or any(p.is_symlink() for p in (output, *output.parents)):
        raise ReleaseError('Choose a new unlinked external acquisition directory')
    engine = Path(engine_root).resolve()
    if output.resolve().is_relative_to(engine):
        raise ReleaseError('Acquisition must remain outside the retained installer')
    output.mkdir(parents=True, mode=0o700)
    bundle_root = output / 'bundles'
    results = {}
    for product in sorted(products):
        row = value['trust'][product]
        result = acquire_v2(row['descriptor'], row['sha256'], value['installer']['revision'], bundle_root,
                            expected_pin=value['family_lock']['packages'][product], github=github, now=now)
        if result['update_availability'] != 'verified_candidate':
            raise ReleaseError('Selected package is withdrawn: '+product)
        results[product] = result
    # Recheck the retained engine after network operations, before exposing inputs.
    verify_engine(engine_root, value['installer'], runner)
    # Emit the usable trio only after every selected package is independently verified.
    lock_path = output / 'family-lock.json'
    lock_path.write_bytes(encoded(value['family_lock']))
    (output / 'distribution.json').write_bytes(encoded(value))
    receipt = {'schema_version': 'aibl.family-acquisition/v1', 'distribution_sha256': expected_sha256,
               'installer_revision': value['installer']['revision'], 'products': sorted(products),
               'family_lock': str(lock_path), 'family_sha256': value['family_sha256'],
               'family_bundles': str(bundle_root), 'status': 'verified_candidate', 'active_use': 'unverified'}
    (output / 'acquisition.json').write_bytes(encoded(receipt))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--distribution', required=True)
    parser.add_argument('--distribution-sha256', required=True)
    parser.add_argument('--engine-root', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--product', action='append', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(acquire(args.distribution, args.distribution_sha256, args.engine_root, args.output, args.product)))
    except (ValueError, TypeError, KeyError, AttributeError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        parser.exit(1, 'Distribution acquisition paused: '+str(exc)+'\n')


if __name__ == '__main__':
    main()
