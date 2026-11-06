"""START-HERE.md's three pastes: the blocked-fetch last line from Learn's card 0.3, and a Codex-only line before each.

In Codex the first fetch is blocked inside the sandbox, and the old last line left a student with nothing to paste.
Wording tests only; the fetch itself was walked in `codex exec`, and a first install can only be walked in the app.
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEXT = (ROOT / 'START-HERE.md').read_text(encoding='utf-8')
LAST = "If the fetch is blocked, ask me for permission to fetch it outside the sandbox with curl. If that doesn't work either, tell me to open that URL in my browser and paste what it shows."
SHIELD = '**In Codex only.** Before you paste: click the shield under the message box and choose Approve for me.'
TAIL = 'and this stops Codex asking you about every step. The app says it may use more credits. You can switch it back any time.'
STEP = "Choose **Allow once** for the step it just told you about, and **Deny** anything else, then tell us."
CMD = "Choose **Allow once** when the command uses git, gh, curl or node on this update, and **Deny** anything else, then tell us."
PASTES = re.findall(r'```text\n(You are the AI Build Lab .*?)```', TEXT, re.S)


class StartHerePastes(unittest.TestCase):
    def test_three_pastes(self):
        self.assertEqual(len(PASTES), 3)

    def test_each_ends_with_the_blocked_fetch_line(self):
        for paste in PASTES:
            self.assertTrue(paste.strip().endswith(LAST), paste[:60])

    def test_the_old_line_is_gone(self):
        self.assertNotIn('say so and I will paste the procedure into chat', TEXT)

    def test_each_paste_has_the_codex_line_just_before_it(self):
        for first in ('installer assistant', 'update assistant', 'fresh-start assistant'):
            before = TEXT.split('```text\nYou are the AI Build Lab ' + first, 1)[0].rstrip().splitlines()[-1]
            self.assertTrue(before.startswith(SHIELD), first)
            self.assertIn(TAIL, before, first)
            # Setup installs through winget or Homebrew, so only the update can name its commands.
            self.assertTrue(before.endswith(CMD if first == 'update assistant' else STEP), first)

    def test_no_dashes(self):
        for dash in ('–', '—'):
            self.assertNotIn(dash, ''.join(PASTES))


if __name__ == '__main__':
    unittest.main()
