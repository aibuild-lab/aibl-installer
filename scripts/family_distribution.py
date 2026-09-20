"""Produce the admitted-distribution set for one family. Writes files for review; never publishes.

The bridge (WORKFORCE-HANDOFF.md) needs five things nobody produced before this
script: a release index per package, a trust descriptor per package, the family
lock, the distribution file with its independent digest, and the publication
admission each package needs for Internal's family_publish.py. Every one of them
is a strict JSON contract whose reader already lives in this repository, so this
script builds them from the same constants and then hands its own output back to
those readers (load_distribution, verify, validate_trust) before it reports success.

Inputs are the built candidates (Internal's family_packages.py output), a clean
checkout of this installer at the revision to pin, the template revision the
public packages are released against, the agent-workforce commit its release is
tagged at, and the tag of the release on this repository that will carry the
index files. Output is one folder plus PUBLISH.md, the ordered checklist of what
to create where. Publication itself stays a human step.
"""
import argparse
import datetime as dt
import json
import subprocess
from pathlib import Path

from github_assets import INSTALLER
from release_files import encoded
from workbench_packages import PRODUCTS, V2_PUBLISHERS, ReleaseError, digest, release_tag, validate_family, validate_pin, verify

BRIDGE_FILES = {'scripts/enrollment_bridge.py', 'scripts/enrollment_templates.json'}
PUBLIC = ('agent-workbench', 'workbench-core', 'agent-essentials')
COMPATIBILITY = {'legacy_template': 'aibuild-lab/agent-essentials',
                 'legacy_workforce_product': 'agent-native-workforce',
                 'legacy_workforce_publisher': 'aibuild-lab/agent-native-workforce'}


def command(args, cwd):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def stamp(value):
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def engine_inventory(engine, runner=command):
    """Pin every tracked file the student's retained copy will run, except the test tree."""
    engine = Path(engine).resolve()
    if runner(['git', 'status', '--porcelain'], engine):
        raise ReleaseError('Pin a clean installer checkout')
    revision = runner(['git', 'rev-parse', 'HEAD'], engine)
    names = [n for n in runner(['git', 'ls-files'], engine).splitlines() if n and not n.startswith('tests/')]
    files = {name: digest((engine / name).read_bytes()) for name in sorted(names)}
    missing = (set(BRIDGE_FILES) | {'scripts/enroll.py', 'SETUP-PROMPT.md'}) - set(files)
    if missing:
        raise ReleaseError('Engine checkout lacks ' + ', '.join(sorted(missing)))
    return revision, files


def package_pins(candidates, template_revision, workforce_target):
    candidates = Path(candidates)
    pins, manifests = {}, {}
    for folder in sorted(p for p in candidates.iterdir() if p.is_dir()):
        product = folder.name
        if product not in PRODUCTS:
            raise ReleaseError('Unknown candidate product ' + product)
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        if manifest.get('product') != product:
            raise ReleaseError('Candidate folder and manifest disagree: ' + product)
        target = workforce_target if product == 'agent-workforce' else template_revision
        pin = {'version': manifest['version'],
               'manifest_sha256': digest((folder / 'manifest.json').read_bytes()),
               'archive_sha256': digest((folder / 'payload.zip').read_bytes()),
               'publisher': V2_PUBLISHERS[product],
               'release_tag': release_tag(product, manifest['version']),
               'release_target': target}
        validate_pin(product, pin, True)
        verify(candidates, product, pin)
        pins[product], manifests[product] = pin, manifest
    if not {'agent-workbench', 'workbench-core', 'agent-workforce'} <= set(pins):
        raise ReleaseError('The Workforce bridge needs agent-workbench, workbench-core and agent-workforce candidates')
    return pins, manifests


def produce(engine, candidates, template_revision, workforce_target, index_tag, output, *,
            sequence=1, valid_days=45, runner=command, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    output = Path(output)
    if output.exists():
        raise ReleaseError('Choose an unused output folder')
    revision, files = engine_inventory(engine, runner)
    pins, manifests = package_pins(candidates, template_revision, workforce_target)
    family = validate_family({'schema_version': 'aibl.family-lock/v2', 'installer_revision': revision,
                              'template_revision': template_revision, 'packages': pins,
                              'compatibility': COMPATIBILITY})
    index_release = {'repository': INSTALLER, 'release_tag': index_tag, 'release_target': revision}
    generated, expires = stamp(now), stamp(now + dt.timedelta(days=valid_days))
    output.mkdir(parents=True)
    written = {}

    def put(name, data):
        (output / name).write_bytes(data)
        written[name] = digest(data)

    trust = {}
    for product, pin in pins.items():
        index = encoded({'schema_version': 'aibl.release-index/v2', 'product': product, 'sequence': sequence,
                         'generated_at': generated, 'expires_at': expires, 'package': pin,
                         'installer_revision': revision, 'withdrawn': False})
        put('index-' + product + '.json', index)
        descriptor = {'schema_version': 'aibl.release-trust/v2', 'product': product, 'index_release': index_release,
                      'index_asset': 'index-' + product + '.json', 'index_sha256': digest(index),
                      'minimum_sequence': sequence}
        put('trust-' + product + '.json', encoded(descriptor))
        trust[product] = {'descriptor': descriptor, 'sha256': digest(encoded(descriptor))}
        manifest = manifests[product]
        admission = encoded({'schema_version': 'aibl.publication-admission/v2', 'state': 'accepted',
                             'source_revision': manifest['source_revision'], 'product': product,
                             'version': pin['version'], 'manifest_sha256': pin['manifest_sha256'],
                             'archive_sha256': pin['archive_sha256'], 'publisher': pin['publisher'],
                             'accepted_source_map_sha256': digest((Path(candidates) / product / 'source-map.json').read_bytes()),
                             'target_revision': pin['release_target'], 'release_tag': pin['release_tag']})
        put('admission-' + product + '.json', admission)
    lock = encoded(family)
    put('family-lock.json', lock)
    distribution = encoded({'schema_version': 'aibl.family-distribution/v1',
                            'installer': {'repository': INSTALLER, 'revision': revision, 'files': files},
                            'family_lock': family, 'family_sha256': digest(lock), 'trust': trust})
    put('distribution.json', distribution)
    (output / 'SHA256SUMS').write_text(''.join('%s  %s\n' % (h, n) for n, h in sorted(written.items())), encoding='utf-8')
    (output / 'PUBLISH.md').write_text(checklist(revision, template_revision, workforce_target, index_tag, pins, written, expires),
                                        encoding='utf-8')

    # Hand the output back to the readers that will judge it on a student's machine.
    from frozen_family import load_distribution
    from release_discovery import validate_trust
    load_distribution(output / 'distribution.json', written['distribution.json'], engine, runner=runner)
    for product, row in trust.items():
        validate_trust(row['descriptor'], row['sha256'])
        if digest((output / ('index-' + product + '.json')).read_bytes()) != row['descriptor']['index_sha256']:
            raise ReleaseError('Index digest drifted: ' + product)
    return {'status': 'produced', 'output': str(output), 'installer_revision': revision,
            'distribution_sha256': written['distribution.json'], 'expires_at': expires,
            'packages': {p: pin['version'] for p, pin in pins.items()}}


def checklist(revision, template_revision, workforce_target, index_tag, pins, written, expires):
    lines = ['# Publish this family, in this order', '',
             'Nothing below is done by the producer. Each release is created immutable (draft first, then',
             'published) by Internal\'s `scripts/family_publish.py` with the matching `admission-<product>.json`',
             'and its SHA-256 from `SHA256SUMS`. Internal must be checked out clean at the candidates\' source',
             'revision, on a Mac (family_publish imports fcntl). Read every release back before moving on.', '',
             '## 1. Package releases (the shelves)', '',
             '| Product | Repository | Tag | Target commit | Assets |', '|---|---|---|---|---|']
    for product, pin in pins.items():
        lines.append('| %s | %s | `%s` | `%s` | manifest.json, payload.zip |' % (product, pin['publisher'], pin['release_tag'], pin['release_target']))
    lines += ['', 'Public packages target the template revision `%s`; agent-workforce targets `%s`.' % (template_revision, workforce_target), '',
              '## 2. Index release on the installer', '',
              'Repository `%s`, tag `%s`, target `%s` (the pinned installer commit). Attach every' % (INSTALLER, index_tag, revision),
              '`index-<product>.json` from this folder, byte for byte. Their digests are inside the trust descriptors,',
              'so a re-encoded upload fails on the student\'s machine.', '',
              '## 3. Hand the distribution to students', '',
              'Attach `distribution.json` to the agent-workforce package release (only enrolled accounts can read it).',
              'Put its digest on the LMS setup lesson, never beside the file:', '',
              '    distribution.json  SHA-256  %s' % written['distribution.json'], '',
              'The indexes expire at `%s`. After that, enrollment stops with "Index expired" until a new' % expires,
              'sequence is produced and published; installed workbenches are unaffected.', '',
              '## 4. Before any student runs it', '',
              '- Merge order already satisfied: this installer revision contains the bridge files and the handoff.',
              '- Team grant on aibuild-lab/agent-workforce for the cohort team.',
              '- Fresh-workbench walk on macOS and Windows, Claude and Codex: paste route, aibl-enroll, aibl-workforce, first prompt.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--engine', required=True, help='Clean checkout of this installer at the revision to pin')
    parser.add_argument('--candidates', required=True, help="Internal's family_packages.py output folder")
    parser.add_argument('--template-revision', required=True, help='my-workbench-template commit the public packages are released against')
    parser.add_argument('--workforce-target', required=True, help='agent-workforce commit its package release is tagged at')
    parser.add_argument('--index-tag', required=True, help='Tag of the release on this repository that carries the index files')
    parser.add_argument('--output', required=True, help='New folder for the produced files')
    parser.add_argument('--sequence', type=int, default=1)
    parser.add_argument('--valid-days', type=int, default=45)
    args = parser.parse_args()
    try:
        print(json.dumps(produce(args.engine, args.candidates, args.template_revision, args.workforce_target,
                                 args.index_tag, args.output, sequence=args.sequence, valid_days=args.valid_days), indent=2))
    except (ReleaseError, OSError, subprocess.SubprocessError, ValueError, KeyError) as error:
        print(json.dumps({'status': 'failed', 'reason': str(error)}, indent=2))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
