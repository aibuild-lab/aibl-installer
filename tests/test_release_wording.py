"""Learner release guidance contract; does not qualify device installation."""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class ReleaseWordingTests(unittest.TestCase):
    def test_student_entries_use_cohort_access_without_fixed_schedule(self):
        for name in ('SETUP-PROMPT.md', 'START-HERE.md', 'README.md'):
            with self.subTest(name=name):
                text = (ROOT / name).read_text()
                flat = re.sub(r'\s+', ' ', text)
                self.assertIn('https://learn.aibuildlab.com/', text)
                self.assertIn('release date, time, and access status', flat)
                self.assertIn('can differ from the first live session', flat)
                self.assertIn('other accessible programs may still be listed', flat)
                self.assertNotRegex(flat, r'(?:unlocked|granted) at (?:your|its|that) (?:first live )?session|for the day your program starts|on the day your program starts|before that, `?aibl-enroll`? lists nothing')

    def test_both_app_handoffs_and_final_summary_point_to_release_status(self):
        text = (ROOT / 'SETUP-PROMPT.md').read_text()
        step9 = text.split('## Step 9:')[1].split('## Step 10:')[0]
        for app in ('Claude', 'Codex'):
            with self.subTest(app=app):
                section = step9.split(f'**{app}:**')[1].split('**')[0]
                self.assertIn('https://learn.aibuildlab.com/', section)
                self.assertIn('Before you have access, that program will not appear', section)
        summary = text.split('## Step 10:')[1].split('## When something fails')[0]
        self.assertIn('Once your course access is released', summary)
        self.assertIn('release date, time, and access status', summary)


if __name__ == '__main__':
    unittest.main()
