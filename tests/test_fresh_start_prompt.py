"""FRESH-START-PROMPT.md keeps a retired-course workbench and builds a fresh one; it never deletes."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPT = (ROOT / 'FRESH-START-PROMPT.md').read_text(encoding='utf-8')
START = (ROOT / 'START-HERE.md').read_text(encoding='utf-8')


class FreshStartPrompt(unittest.TestCase):
    def test_never_deletes(self):
        self.assertIn('**Never delete anything.**', PROMPT)
        for word in ('rm -rf', 'Remove-Item', 'gh repo delete', 'git reset', 'git clean'):
            self.assertNotIn(word, PROMPT)

    def test_renames_repository_and_folder(self):
        self.assertIn('gh repo rename <old> --repo <login>/my-workbench --yes', PROMPT)
        self.assertIn('mv ~/GitHub/my-workbench ~/GitHub/<old>', PROMPT)
        self.assertIn('Move-Item "$HOME\GitHub\my-workbench" "$HOME\GitHub\<old>"', PROMPT)
        self.assertIn('--json visibility --jq .visibility` prints `PRIVATE`', PROMPT)

    def test_only_retired_course_workbenches(self):
        self.assertIn('**Already current.**', PROMPT)
        self.assertIn('aibuild-lab/agent-essentials', PROMPT)
        self.assertIn('/aibl-teach', PROMPT)

    def test_runs_from_home_folder_and_fresh_setup_creates(self):
        self.assertIn('must be open on the home folder', PROMPT)
        self.assertIn('**through its step 8**', PROMPT)
        self.assertIn('`"status": "created"`', PROMPT)

    def test_carries_over_only_chosen_files_into_one_folder(self):
        self.assertIn('library/from-old-workbench/', PROMPT)
        self.assertIn('never overwrite a file', PROMPT)

    def test_the_rename_it_makes_is_expected_to_forward(self):
        # GitHub forwards an old name after a rename (gh api and gh repo view both follow it, checked 10-03),
        # so "now fails with not found" could never come true and the prompt stopped at its own rename.
        self.assertNotIn('now fails with "not found", and', PROMPT)
        self.assertIn('now prints `<login>/<old>`', PROMPT)

    def test_setup_step_eight_is_told_the_forward_is_this_rename(self):
        self.assertIn('add `--forwards-to <login>/<old>` to step 8', PROMPT)
        self.assertIn('Do not show the student those choices here.', PROMPT)
        self.assertIn("Its rule 12 applies here too", PROMPT)

    def test_start_here_links_it(self):
        self.assertIn('https://raw.githubusercontent.com/aibuild-lab/aibl-installer/main/FRESH-START-PROMPT.md', START)


class NoFixedSkillCount(unittest.TestCase):
    def test_student_docs_do_not_count_skills(self):
        for name in ('SETUP-PROMPT.md', 'START-HERE.md', 'README.md'):
            text = (ROOT / name).read_text(encoding='utf-8')
            self.assertIsNone(re.search(r'\bthree (skills|aibl|items|starter)', text, re.I), name)


if __name__ == '__main__':
    unittest.main()
