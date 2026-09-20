"""The producer's output must satisfy the readers a student's machine runs, not just look right."""
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

import test_frozen_family as frozen_fixtures
import test_enrollment_bridge as bridge_fixtures
from test_family_v2 import core_components
import family_distribution as producer
import frozen_family as frozen
import workbench_packages as packages
from release_files import encoded

NOW = frozen_fixtures.NOW
REVISION = 'a' * 40
TEMPLATE = 'b' * 40
WORKFORCE = 'd' * 40


def synthetic_candidates(root):
    """Three minimal packages that pass workbench_packages.verify, on disk like family_packages.py writes them."""
    root = Path(root)
    skills = {client + '/skills/' + skill + '/SKILL.md': b'method ' + skill.encode()
              for client in ('.agents', '.claude') for skill in packages.CORE_SKILLS}
    contract = {'schema_version': 'aibl.program-connection/v1', 'product': 'agent-workforce',
                'requires': ['agent-workbench', 'workbench-core'],
                'first_action': {'path': 'course/workforce/START-HERE.md', 'prompt': 'Use aibl-workforce.'},
                'native': {'claude': ['.claude/skills/aibl-workforce/SKILL.md'], 'codex': ['.agents/skills/aibl-workforce/SKILL.md']}}
    plans = {
        'agent-workbench': ('0.0.12', 'seed', {'README.md': b'seed readme\n'}, []),
        'workbench-core': ('0.0.11', 'supplied', skills, core_components(skills, '0.0.11')),
        'agent-workforce': ('0.0.12', 'supplied', {'course/workforce/START-HERE.md': b'first action\n',
                                                    'course/workforce/connection.json': encoded(contract),
                                                    '.claude/skills/aibl-workforce/SKILL.md': b'entry\n',
                                                    '.agents/skills/aibl-workforce/SKILL.md': b'entry\n'}, []),
    }
    for product, (version, policy, files, components) in plans.items():
        folder = root / product
        folder.mkdir(parents=True)
        manifest = {'schema_version': 'aibl.family-package/v2', 'product': product, 'version': version,
                    'source_repository': 'aibuild-lab/agent-native-workforce-internal', 'source_revision': 'c' * 40,
                    'components': components,
                    'files': [{'path': n, 'sha256': packages.digest(raw), 'mode': 420, 'policy': policy} for n, raw in sorted(files.items())]}
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            for name, raw in sorted(files.items()):
                archive.writestr(name, raw)
        (folder / 'manifest.json').write_bytes(encoded(manifest))
        (folder / 'payload.zip').write_bytes(stream.getvalue())
        (folder / 'source-map.json').write_bytes(encoded({'product': product, 'rows': []}))
    return root


def engine_runner(engine, revision, base=None):
    """Answer the Git questions the producer and the readers ask, against a synthetic checkout."""
    engine = Path(engine)
    def runner(args, cwd):
        if 'ls-files' in args:
            return '\n'.join(sorted(p.relative_to(engine).as_posix() for p in engine.rglob('*') if p.is_file()))
        if 'status' in args:
            return ''
        if '--show-toplevel' in args:
            return str(engine)
        if 'remote.origin.url' in args:
            return 'https://github.com/aibuild-lab/aibl-installer'
        if base:
            return base(args, cwd)
        return revision
    return runner


class Producer(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.engine = self.root / 'engine'
        for name in frozen.REQUIRED_ENGINE_FILES | producer.BRIDGE_FILES | {'hooks/guard.mjs', 'tests/test_ignored.py'}:
            path = self.engine / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'synthetic ' + name.encode() + b'\n')
        self.candidates = synthetic_candidates(self.root / 'candidates')
        self.runner = engine_runner(self.engine, REVISION)

    def produce(self, **extra):
        return producer.produce(self.engine, self.candidates, TEMPLATE, WORKFORCE, 'cohort-test-1', self.root / 'out',
                                runner=self.runner, now=NOW, **extra)

    def seed_assets(self, out, candidates):
        github = frozen_fixtures.MemoryAssets()
        distribution = json.loads((out / 'distribution.json').read_text())
        for product, row in distribution['trust'].items():
            github.put(row['descriptor']['index_release'], row['descriptor']['index_asset'], (out / row['descriptor']['index_asset']).read_bytes())
            pin = distribution['family_lock']['packages'][product]
            locator = {'repository': pin['publisher'], 'release_tag': pin['release_tag'], 'release_target': pin['release_target']}
            for name in ('manifest.json', 'payload.zip'):
                github.put(locator, name, (Path(candidates) / product / name).read_bytes())
        return github, distribution

    def test_output_is_accepted_by_the_readers_and_acquirable(self):
        result = self.produce()
        out = Path(result['output'])
        self.assertEqual(result['installer_revision'], REVISION)
        names = {p.name for p in out.iterdir()}
        for product in ('agent-workbench', 'workbench-core', 'agent-workforce'):
            self.assertTrue({'index-%s.json' % product, 'trust-%s.json' % product, 'admission-%s.json' % product} <= names)
        self.assertTrue({'family-lock.json', 'distribution.json', 'SHA256SUMS', 'PUBLISH.md'} <= names)
        # Tests are never part of the pinned engine; the guard and every script are.
        distribution = json.loads((out / 'distribution.json').read_text())
        self.assertIn('hooks/guard.mjs', distribution['installer']['files'])
        self.assertNotIn('tests/test_ignored.py', distribution['installer']['files'])
        self.assertEqual(distribution['family_lock']['packages']['agent-workbench']['release_target'], TEMPLATE)
        self.assertEqual(distribution['family_lock']['packages']['agent-workforce']['release_target'], WORKFORCE)
        # The digest the LMS page will carry is the digest of the bytes on disk.
        raw = (out / 'distribution.json').read_bytes()
        self.assertEqual(packages.digest(raw), result['distribution_sha256'])
        self.assertIn(result['distribution_sha256'], (out / 'PUBLISH.md').read_text())
        # A student's engine acquires the selected packages from exactly these assets.
        github, _ = self.seed_assets(out, self.candidates)
        receipt = frozen.acquire(out / 'distribution.json', result['distribution_sha256'], self.engine, self.root / 'acquired',
                                 ['agent-workbench', 'workbench-core', 'agent-workforce'], github=github, now=NOW + frozen_fixtures.dt.timedelta(days=1), runner=self.runner)
        self.assertEqual(receipt['status'], 'verified_candidate')
        self.assertTrue((self.root / 'acquired/bundles/agent-workforce/payload.zip').is_file())

    def test_admissions_match_internal_publish_contract(self):
        out = Path(self.produce()['output'])
        for product in ('agent-workbench', 'workbench-core', 'agent-workforce'):
            admission = json.loads((out / ('admission-%s.json' % product)).read_text())
            self.assertEqual(set(admission), {'schema_version', 'state', 'source_revision', 'product', 'version', 'manifest_sha256',
                                              'archive_sha256', 'publisher', 'accepted_source_map_sha256', 'target_revision', 'release_tag'})
            self.assertEqual(admission['release_tag'], packages.release_tag(product, admission['version']))
            self.assertEqual(admission['accepted_source_map_sha256'], packages.digest((self.candidates / product / 'source-map.json').read_bytes()))
        sums = dict(line.split('  ', 1)[::-1] for line in (out / 'SHA256SUMS').read_text().splitlines())
        self.assertEqual(sums['admission-agent-workforce.json'], packages.digest((out / 'admission-agent-workforce.json').read_bytes()))

    def test_dirty_engine_and_missing_candidate_stop(self):
        dirty = engine_runner(self.engine, REVISION)
        def runner(args, cwd):
            return ' M scripts/enroll.py' if 'status' in args else dirty(args, cwd)
        with self.assertRaisesRegex(packages.ReleaseError, 'clean'):
            producer.produce(self.engine, self.candidates, TEMPLATE, WORKFORCE, 't', self.root / 'x', runner=runner, now=NOW)
        import shutil
        shutil.rmtree(self.candidates / 'workbench-core')
        with self.assertRaisesRegex(packages.ReleaseError, 'workbench-core'):
            self.produce()

    def test_expired_index_is_refused_at_acquire_time(self):
        result = self.produce(valid_days=2)
        out = Path(result['output'])
        github, _ = self.seed_assets(out, self.candidates)
        with self.assertRaisesRegex(packages.ReleaseError, 'expired'):
            frozen.acquire(out / 'distribution.json', result['distribution_sha256'], self.engine, self.root / 'late',
                           ['agent-workbench'], github=github, now=NOW + frozen_fixtures.dt.timedelta(days=3), runner=self.runner)


class ProducedBridge(unittest.TestCase):
    """The produced distribution drives the real bridge: preview, confirm, apply, entry skill lands.

    The bridge fixture is used as a fixture (real template tree, real Git, simulated provider and engine
    identity), not inherited: its own cases rebuild their synthetic distribution mid-test."""

    def setUp(self):
        self.fixture = bridge_fixtures.EnrollmentBridge('test_cli_check_uses_new_access_route')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        fixture = self.fixture
        candidates = os.environ.get('AIBL_BRIDGE_CANDIDATE_BUNDLES')
        self.candidates = Path(candidates) if candidates else synthetic_candidates(fixture.root / 'candidates')
        runner = engine_runner(fixture.engine, fixture.revision, base=fixture.runner)
        result = producer.produce(fixture.engine, self.candidates, fixture.sources[0]['revision'], WORKFORCE, 'cohort-test-1',
                                  fixture.root / 'produced', runner=runner, now=NOW - frozen_fixtures.dt.timedelta(days=1))
        out = Path(result['output'])
        fixture.github = frozen_fixtures.MemoryAssets()
        distribution = json.loads((out / 'distribution.json').read_text())
        for product, row in distribution['trust'].items():
            fixture.github.put(row['descriptor']['index_release'], row['descriptor']['index_asset'], (out / row['descriptor']['index_asset']).read_bytes())
            pin = distribution['family_lock']['packages'][product]
            locator = {'repository': pin['publisher'], 'release_tag': pin['release_tag'], 'release_target': pin['release_target']}
            for name in ('manifest.json', 'payload.zip'):
                fixture.github.put(locator, name, (self.candidates / product / name).read_bytes())
        fixture.path, fixture.sha = out / 'distribution.json', result['distribution_sha256']

    def test_produced_distribution_enrolls_a_template_workbench(self):
        fixture = self.fixture
        plan = fixture.preview('claude')
        self.assertEqual(plan['status'], 'previewed')
        result = fixture.apply(plan)
        self.assertIn('.claude/skills/aibl-workforce/SKILL.md', result['native_paths']['claude'])
        self.assertTrue((fixture.workbench / '.claude/skills/aibl-workforce/SKILL.md').is_file())
        self.assertTrue((fixture.workbench / 'course/workforce/START-HERE.md').is_file())
        if os.environ.get('AIBL_BRIDGE_CANDIDATE_BUNDLES'):
            self.assertTrue((fixture.workbench / 'course/workforce/prompts/anw-m1-01.txt').is_file())
            self.assertTrue((fixture.workbench / 'workforce/profiles/aibl-chief-of-staff.md').is_file())


if __name__ == '__main__':
    unittest.main()
