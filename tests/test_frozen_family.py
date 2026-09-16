"""Synthetic release and account fixtures; no provider or student writes."""
import copy
import datetime as dt
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import frozen_family as f
import github_assets as g
import release_discovery as d
import workbench_packages as w
from release_files import encoded, digest

NOW = dt.datetime(2026, 9, 14, tzinfo=dt.timezone.utc)


class GitHubTransport(unittest.TestCase):
    def setUp(self):
        repo = 'aibuild-lab/my-workbench-template'
        self.locator = dict(repository=repo, release_tag='v0.0.12', release_target='a'*40)
        self.route = f'repos/{repo}/releases/assets/2'
        self.release_route = f'repos/{repo}/releases/tags/v0.0.12'
        self.ref_route = f'repos/{repo}/git/ref/tags/v0.0.12'
        self.assets_route = f'repos/{repo}/releases/1/assets?per_page=100&page=1'
        self.values = {
            self.release_route: dict(id=1, tag_name='v0.0.12', draft=False, url=f'https://api.github.com/repos/{repo}/releases/1'),
            self.ref_route: dict(ref='refs/tags/v0.0.12', object=dict(type='commit', sha='a'*40)),
            self.assets_route: [dict(id=2, name='payload.zip', state='uploaded', size=4, url='https://api.github.com/'+self.route)],
            self.route: b'data',
        }
        self.calls = []
        def transport(args, limit):
            self.calls.append(args)
            value = self.values[args[-1]]
            return value if isinstance(value, bytes) else json.dumps(value).encode()
        self.github = g.GitHubAssets(transport)

    def test_exact_read_only_release_and_asset_ids(self):
        self.assertEqual(self.github.fetch(self.locator, 'payload.zip', 10), b'data')
        self.assertEqual(self.calls[-1], ['-H', 'Accept: application/octet-stream', self.route])
        self.assertFalse(any('POST' in call or 'PATCH' in call for call in self.calls))

    def test_wrong_repository_tag_target_and_draft(self):
        for key, value in (('tag_name', 'other'), ('draft', True), ('url', 'https://api.github.com/repos/other/repo/releases/1')):
            original = self.values[self.release_route][key]
            self.values[self.release_route][key] = value
            with self.assertRaises(w.ReleaseError):
                self.github.fetch(self.locator, 'payload.zip', 10)
            self.values[self.release_route][key] = original
        self.values[self.ref_route]['object']['sha'] = 'b'*40
        with self.assertRaisesRegex(w.ReleaseError, 'target'):
            self.github.fetch(self.locator, 'payload.zip', 10)

    def test_annotated_tag_and_duplicate_missing_or_oversized_asset(self):
        self.values[self.ref_route]['object'] = dict(type='tag', sha='b'*40)
        self.values['repos/'+self.locator['repository']+'/git/tags/'+'b'*40] = dict(sha='b'*40, object=dict(type='commit', sha='a'*40))
        self.assertEqual(self.github.fetch(self.locator, 'payload.zip', 10), b'data')
        asset = self.values[self.assets_route][0]
        for rows in ([], [asset, asset], [dict(asset, size=11)], [dict(asset, state='new')], [dict(asset, url='https://other.invalid/asset')]):
            self.values[self.assets_route] = rows
            with self.assertRaises(w.ReleaseError):
                self.github.fetch(self.locator, 'payload.zip', 10)
        self.values[self.assets_route] = [asset]
        self.values[self.route] = b'too many bytes'
        with self.assertRaises(w.ReleaseError):
            self.github.fetch(self.locator, 'payload.zip', 10)


class MemoryAssets:
    def __init__(self):
        self.values = {}
        self.calls = []
    def put(self, locator, name, data):
        self.values[(locator['repository'], locator['release_tag'], name)] = data
    def fetch(self, locator, name, limit):
        g.validate_locator(locator)
        self.calls.append((locator['repository'], name))
        raw = self.values[(locator['repository'], locator['release_tag'], name)]
        if len(raw) > limit:
            raise w.ReleaseError('Synthetic oversized asset')
        return raw


class FrozenFamily(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.github = MemoryAssets()
        self.revision = 'a'*40
        self.engine = self.root/'engine'
        self.engine.mkdir()
        files = {}
        for name in f.REQUIRED_ENGINE_FILES:
            path = self.engine/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'synthetic engine file\n')
            files[name] = digest(path.read_bytes())
        self.family = dict(schema_version='aibl.family-lock/v2', installer_revision=self.revision,
                           template_revision='b'*40, packages={}, compatibility={
                           'legacy_template': 'aibuild-lab/agent-essentials',
                           'legacy_workforce_product': 'agent-native-workforce',
                           'legacy_workforce_publisher': 'aibuild-lab/agent-native-workforce'})
        self.distribution = dict(schema_version='aibl.family-distribution/v1', installer={
                                 'repository': g.INSTALLER, 'revision': self.revision, 'files': files},
                                 family_lock=self.family, family_sha256='', trust={})
        self.indexes = {}
        for product, path, policy in [('agent-workbench', 'README.md', 'seed'),
                                      ('workbench-core', '.agents/skills/aibl-enroll/SKILL.md', 'supplied'),
                                      ('agent-essentials', 'blueprints/youtube-transcripts.md', 'supplied'),
                                      ('agent-workforce', 'course/workforce/START-HERE.md', 'supplied')]:
            content = ('Synthetic '+product).encode()
            manifest = dict(schema_version='aibl.family-package/v2', product=product, version='0.0.12',
                            source_repository='aibuild-lab/agent-native-workforce-internal', source_revision='c'*40,
                            files=[dict(path=path, sha256=digest(content), mode=420, policy=policy)], components=[])
            contents={path:content}
            if product=='workbench-core':
                from test_family_v2 import core_components
                contents={client+'/skills/'+skill+'/SKILL.md':content for client in ('.agents','.claude') for skill in w.CORE_SKILLS}
                manifest['files']=[dict(path=name,sha256=digest(raw),mode=420,policy=policy) for name,raw in contents.items()]
                manifest['components']=core_components(contents,'0.0.12')
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w') as archive:
                for name,raw in contents.items():archive.writestr(name,raw)
            mb, ab = encoded(manifest), stream.getvalue()
            pin = dict(version='0.0.12', manifest_sha256=digest(mb), archive_sha256=digest(ab),
                       publisher=w.V2_PUBLISHERS[product], release_tag=w.release_tag(product, '0.0.12'), release_target='b'*40)
            self.family['packages'][product] = pin
            locator = dict(repository=pin['publisher'], release_tag=pin['release_tag'], release_target=pin['release_target'])
            self.github.put(locator, 'manifest.json', mb)
            self.github.put(locator, 'payload.zip', ab)
            index = dict(schema_version='aibl.release-index/v2', product=product, sequence=1,
                         generated_at='2026-09-13T00:00:00Z', expires_at='2026-09-15T00:00:00Z',
                         package=pin, installer_revision=self.revision, withdrawn=False)
            self.indexes[product] = index
            index_release = dict(repository=g.INSTALLER, release_tag='cohort-synthetic-1', release_target=self.revision)
            trust = dict(schema_version='aibl.release-trust/v2', product=product, index_release=index_release,
                         index_asset='index-'+product+'.json', index_sha256='', minimum_sequence=1)
            self.distribution['trust'][product] = dict(descriptor=trust, sha256='')
        self.save()

    def save(self):
        for product, row in self.distribution['trust'].items():
            raw = encoded(self.indexes[product])
            trust = row['descriptor']
            trust['index_sha256'] = digest(raw)
            row['sha256'] = digest(encoded(trust))
            self.github.put(trust['index_release'], trust['index_asset'], raw)
        self.distribution['family_sha256'] = digest(encoded(self.family))
        self.path = self.root/'distribution.json'
        self.path.write_bytes(encoded(self.distribution))
        self.sha = digest(self.path.read_bytes())

    def runner(self, args, cwd):
        if '--show-toplevel' in args:
            return str(self.engine)
        if 'remote.origin.url' in args:
            return 'https://github.com/aibuild-lab/aibl-installer.git'
        if 'status' in args:
            return ''
        return self.revision

    def acquire(self, products=('agent-workbench', 'workbench-core'), name='out'):
        return f.acquire(self.path, self.sha, self.engine, self.root/name, products,
                         github=self.github, now=NOW, runner=self.runner)

    def test_usable_trio_downloads_only_selected_public_packages(self):
        receipt = self.acquire()
        self.assertEqual(receipt['status'], 'verified_candidate')
        w.load_lock(receipt['family_lock'], receipt['family_sha256'])
        for product in receipt['products']:
            w.verify(receipt['family_bundles'], product, self.family['packages'][product])
        self.assertFalse(any(repo == 'aibuild-lab/agent-workforce' for repo, name in self.github.calls))
        self.assertFalse((Path(receipt['family_bundles'])/'agent-essentials').exists())
        with self.assertRaises(w.ReleaseError):
            self.acquire()

    def test_lesson8_and_workforce_explicit_acquisition(self):
        receipt = self.acquire(('agent-essentials', 'agent-workforce'))
        self.assertEqual(receipt['products'], ['agent-essentials', 'agent-workforce'])
        self.assertTrue(any(repo == 'aibuild-lab/agent-workforce' for repo, name in self.github.calls))

    def test_independent_distribution_and_descriptor_hashes_required(self):
        with self.assertRaisesRegex(w.ReleaseError, 'Independent distribution'):
            f.load_distribution(self.path, '0'*64, self.engine, runner=self.runner)
        trust = self.distribution['trust']['agent-workbench']['descriptor']
        self.assertEqual(d.discover(trust, self.revision, github=self.github, now=NOW)['update_availability'], 'unknown')
        sha = self.distribution['trust']['agent-workbench']['sha256']
        self.assertEqual(d.discover(trust, self.revision, descriptor_sha256=sha, github=self.github, now=NOW)['update_availability'], 'verified_candidate')

    def test_expiry_withdrawal_wrong_engine_and_family_mismatch(self):
        original = copy.deepcopy(self.indexes['agent-workbench'])
        for key, value in [('expires_at', '2026-09-13T00:00:00Z'), ('withdrawn', True), ('installer_revision', 'f'*40), ('sequence', 0)]:
            self.indexes['agent-workbench'] = dict(original, **{key: value})
            self.save()
            with self.assertRaises(w.ReleaseError):
                self.acquire(name='out-'+key)
        self.indexes['agent-workbench'] = copy.deepcopy(original)
        self.indexes['agent-workbench']['package']['archive_sha256'] = 'f'*64
        self.save()
        with self.assertRaisesRegex(w.ReleaseError, 'family lock'):
            self.acquire(name='mismatch')

    def test_tampered_payload_never_emits_usable_trio(self):
        pin = self.family['packages']['agent-workbench']
        self.github.values[(pin['publisher'], pin['release_tag'], 'payload.zip')] = b'tampered'
        with self.assertRaisesRegex(w.ReleaseError, 'integrity'):
            self.acquire()
        self.assertFalse((self.root/'out/family-lock.json').exists())
        self.assertFalse((self.root/'out/acquisition.json').exists())

    def test_engine_changed_files_dirty_state_and_linked_output(self):
        (self.engine/'scripts/enroll.py').write_text('changed')
        with self.assertRaisesRegex(w.ReleaseError, 'file differs'):
            self.acquire()
        (self.engine/'scripts/enroll.py').write_bytes(b'synthetic engine file\n')
        with self.assertRaisesRegex(w.ReleaseError, 'clean exact'):
            f.load_distribution(self.path, self.sha, self.engine,
                                runner=lambda args, cwd: ' M changed' if 'status' in args else self.runner(args, cwd))
        (self.root/'linked').symlink_to(self.root/'absent')
        with self.assertRaises(w.ReleaseError):
            self.acquire(name='linked')

    def test_real_git_engine_and_post_download_drift(self):
        def git(*args):
            return subprocess.check_output(['git', *args], cwd=self.engine, stderr=subprocess.DEVNULL, text=True).strip()
        git('init')
        git('remote', 'add', 'origin', 'https://github.com/aibuild-lab/aibl-installer.git')
        git('config', 'url.git@github.com:.insteadOf', 'https://github.com/')
        self.assertEqual(git('remote', 'get-url', 'origin'), 'git@github.com:aibuild-lab/aibl-installer.git')
        git('add', '.')
        git('-c', 'user.name=Synthetic test', '-c', 'user.email=synthetic@example.invalid', 'commit', '-m', 'Synthetic engine')
        self.revision = git('rev-parse', 'HEAD')
        self.distribution['installer']['revision'] = self.revision
        self.family['installer_revision'] = self.revision
        for product, row in self.distribution['trust'].items():
            row['descriptor']['index_release']['release_target'] = self.revision
            self.indexes[product]['installer_revision'] = self.revision
        self.save()
        self.assertEqual(f.load_distribution(self.path, self.sha, self.engine)['installer']['revision'], self.revision)
        original_fetch = self.github.fetch
        def changing_fetch(locator, name, limit):
            result = original_fetch(locator, name, limit)
            if name == 'payload.zip':
                (self.engine/'scripts/enroll.py').write_text('changed during download')
            return result
        self.github.fetch = changing_fetch
        with self.assertRaisesRegex(w.ReleaseError, 'clean exact'):
            f.acquire(self.path, self.sha, self.engine, self.root/'out', ['agent-workbench'], github=self.github, now=NOW)
        self.assertFalse((self.root/'out/acquisition.json').exists())

    def test_nested_admission_mismatch_is_rejected_before_download(self):
        self.distribution['trust']['agent-workbench']['sha256'] = 'f'*64
        self.path.write_bytes(encoded(self.distribution))
        self.sha = digest(self.path.read_bytes())
        with self.assertRaisesRegex(w.ReleaseError, 'descriptor digest'):
            self.acquire()
        self.assertEqual(self.github.calls, [])


if __name__ == '__main__':
    unittest.main()
