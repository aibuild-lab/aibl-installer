"""SETUP-PROMPT.md step 2 contract: an out-of-date ~/GitHub/aibl-installer is refreshed, not reused as-is.

Step 2 used to reuse any clean existing copy at its current revision and check only for scripts/enroll.py
(present since 09-11). A copy from before 09-16 has no scripts/hub_setup.py, so setup passed step 2 and failed
at step 8, and step 7 installed the secrets guard from the old copy. These tests pin the refresh, the move-aside
fallback and the stop for folders that are not safe to touch, and prove with real Git that the prompt's pull
brings a shallow launcher-style clone up to date.
"""
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEXT = (ROOT / 'SETUP-PROMPT.md').read_text(encoding='utf-8')
STEP2 = TEXT.split('## Step 2:', 1)[1].split('## Step 3:', 1)[0]
FLAT2 = re.sub(r'\s+', ' ', STEP2)
RULES = TEXT.split('## Your behavioral rules', 1)[1].split('## Step 1:', 1)[0]


class StepTwoWording(unittest.TestCase):
    def test_an_existing_copy_is_no_longer_reused_as_is(self):
        self.assertNotIn('Reuse its current revision', STEP2)
        self.assertIn('git -C ~/GitHub/aibl-installer pull --ff-only origin main', STEP2)
        self.assertIn('branch --show-current', STEP2)

    def test_unsafe_folders_still_stop_untouched(self):
        self.assertIn('`git status --porcelain` is empty', STEP2)
        self.assertIn('origin is `https://github.com/aibuild-lab/aibl-installer.git`', STEP2)
        self.assertIn('stop and preserve it for the course team to review', FLAT2)
        self.assertIn('do not reset, pull, move or overwrite it', FLAT2)

    def test_a_copy_that_cannot_fast_forward_is_moved_aside_not_repaired(self):
        self.assertIn('mv ~/GitHub/aibl-installer ~/GitHub/aibl-installer-old-', STEP2)
        self.assertIn('Nothing was deleted.', STEP2)
        self.assertNotRegex(FLAT2, r'reset --hard|rm -rf|git clean')

    def test_files_later_steps_run_are_verified(self):
        for path in ('scripts/hub_setup.py', 'hooks/refresh-guard.mjs'):
            with self.subTest(path=path):
                self.assertIn(path, STEP2)
                self.assertTrue((ROOT / path).exists(), path)

    def test_rule_eleven_names_the_moved_aside_folder(self):
        self.assertIn('~/GitHub/aibl-installer-old-<date>', RULES)


@unittest.skipUnless(shutil.which('git'), 'git not available')
class StaleShallowCloneRefresh(unittest.TestCase):
    def git(self, *args, cwd=None):
        return subprocess.run(['git', '-c', 'core.autocrlf=false', *args], cwd=cwd, check=True,
                              capture_output=True, text=True).stdout.strip()

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        source = self.tmp / 'source'
        source.mkdir()
        self.git('init', '-q', '-b', 'main', cwd=source)
        self.git('config', 'user.email', 'test@example.invalid', cwd=source)
        self.git('config', 'user.name', 'test', cwd=source)
        (source / 'scripts').mkdir()
        (source / 'scripts' / 'enroll.py').write_text('# 09-11\n')
        self.git('add', '.', cwd=source)
        self.git('commit', '-q', '-m', 'old installer', cwd=source)
        self.source = source

    def add_hub_setup(self):
        (self.source / 'scripts' / 'hub_setup.py').write_text('# 09-16\n')
        self.git('add', '.', cwd=self.source)
        self.git('commit', '-q', '-m', 'hub setup', cwd=self.source)

    def test_prompt_pull_brings_a_shallow_launcher_clone_up_to_date(self):
        student = self.tmp / 'aibl-installer'
        self.git('clone', '-q', '--depth', '1', self.source.as_uri(), str(student))
        self.add_hub_setup()
        self.assertEqual(self.git('branch', '--show-current', cwd=student), 'main')
        self.assertEqual(self.git('status', '--porcelain', cwd=student), '')
        self.git('pull', '-q', '--ff-only', 'origin', 'main', cwd=student)
        self.assertTrue((student / 'scripts' / 'hub_setup.py').exists())

    def test_a_detached_copy_is_not_on_main_so_it_takes_the_move_aside_branch(self):
        student = self.tmp / 'aibl-installer'
        self.git('clone', '-q', self.source.as_uri(), str(student))
        self.git('checkout', '-q', '--detach', cwd=student)
        self.assertEqual(self.git('branch', '--show-current', cwd=student), '')


if __name__ == '__main__':
    unittest.main()
