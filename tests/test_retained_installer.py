"""Execute the launcher's retention block against local Git fixtures, no installs."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = 'https://github.com/aibuild-lab/aibl-installer.git'

class RetainedInstallerTests(unittest.TestCase):
    def git(self, folder, *args):
        return subprocess.check_output(['git', '-C', str(folder), *args], text=True).strip()

    def seed(self, folder):
        folder.mkdir(parents=True)
        self.git(folder, 'init', '--quiet')
        self.git(folder, 'config', 'user.name', 'Fixture')
        self.git(folder, 'config', 'user.email', 'fixture@example.invalid')
        (folder/'scripts').mkdir()
        (folder/'scripts/enroll.py').write_text('# fixture\n')
        self.git(folder, 'add', '.')
        self.git(folder, 'commit', '--quiet', '-m', 'fixture')
        self.git(folder, 'remote', 'add', 'origin', ORIGIN)
        return self.git(folder, 'rev-parse', 'HEAD')

    def run_block(self, home, commit=''):
        launcher = (ROOT/'start.sh').read_text()
        block = launcher[launcher.index('# Keep the enrollment engine'):launcher.index('if [[ -n "$INSTALLER_COMMIT" ]]; then exec')]
        return subprocess.run(['bash', '-c', 'set -euo pipefail\n'+block], env={**os.environ, 'HOME':str(home), 'INSTALLER_COMMIT':commit}, text=True, capture_output=True)

    def test_reuse_preserves_exact_head_and_does_not_need_network(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d);folder=home/'GitHub/aibl-installer';head=self.seed(folder)
            for _ in range(2):
                result=self.run_block(home)
                self.assertEqual(result.returncode,0,result.stderr+result.stdout)
                self.assertEqual(self.git(folder,'rev-parse','HEAD'),head)
            self.assertEqual(list((home/'GitHub').iterdir()),[folder])

    def test_dirty_installer_and_path_collision_are_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d);folder=home/'GitHub/aibl-installer';self.seed(folder)
            (folder/'scripts/enroll.py').write_text('local changes')
            self.assertNotEqual(self.run_block(home).returncode,0)
            self.assertEqual((folder/'scripts/enroll.py').read_text(),'local changes')
        with tempfile.TemporaryDirectory() as d:
            home=Path(d);folder=home/'GitHub/aibl-installer';folder.mkdir(parents=True)
            (folder/'notes').write_text('keep')
            self.assertNotEqual(self.run_block(home).returncode,0)
            self.assertEqual((folder/'notes').read_text(),'keep')

    def test_frozen_cache_is_separate_and_rejects_wrong_head(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d);seed=home/'seed';head=self.seed(seed)
            cache=home/'.aibl/installers'/head;cache.parent.mkdir(parents=True);seed.rename(cache)
            self.assertEqual(self.run_block(home,head).returncode,0)
            self.assertFalse((home/'GitHub/aibl-installer').exists())
            wrong=home/'.aibl/installers'/('a'*40);cache.rename(wrong)
            self.assertNotEqual(self.run_block(home,'a'*40).returncode,0)
            self.assertEqual(self.git(wrong,'rev-parse','HEAD'),head)

    def test_wrong_origin_is_rejected_without_changes(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d);folder=home/'GitHub/aibl-installer';head=self.seed(folder)
            self.git(folder,'remote','set-url','origin','https://example.invalid/other.git')
            self.assertNotEqual(self.run_block(home).returncode,0)
            self.assertEqual(self.git(folder,'rev-parse','HEAD'),head)

if __name__=='__main__':unittest.main()
