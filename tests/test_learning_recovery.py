"""Synthetic local recovery checks, no account, network, or native-app proof."""
import copy
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import local_learning_backup as b

A = b.PREFIX + 'lesson-one.json'
B = b.PREFIX + 'lesson-two.json'
OTHER = b.PREFIX + 'keep.json'


class LearningRecovery(unittest.TestCase):
 def setUp(self):
  self.tmp = tempfile.TemporaryDirectory()
  self.addCleanup(self.tmp.cleanup)
  self.base = Path(self.tmp.name).resolve()
  self.root = self.base / 'work'
  (self.root / b.PREFIX).mkdir(parents=True)
  self.write(A, 'backup one')
  self.write(B, 'backup two')
  self.write(OTHER, 'unrelated learning')
  self.write('.aibl-local/package-history.json', 'package history')
  self.write('.git/HEAD', 'unrelated Git state')
  self.archive = self.base / 'private.zip'
  self.sha = b.backup(self.root, self.archive, [A, B])['sha256']
  self.write(A, 'newer local answer')
  (self.root / B).unlink()
  self.preview = b.preview_restore(self.root, self.archive, self.sha)
  self.plan = self.preview['plan']
  self.ident = self.preview['review_sha256']

 def write(self, name, text):
  target = self.root / name
  target.parent.mkdir(parents=True, exist_ok=True)
  target.write_text(text)

 def apply(self, **kwargs):
  return b.apply_restore(self.root, self.archive, self.sha, self.plan, self.ident, confirmed=True, **kwargs)

 def untouched(self):
  self.assertEqual((self.root / OTHER).read_text(), 'unrelated learning')
  self.assertEqual((self.root / '.aibl-local/package-history.json').read_text(), 'package history')
  self.assertEqual((self.root / '.git/HEAD').read_text(), 'unrelated Git state')

 def test_explicit_selection_private_backup_and_readonly_preview(self):
  with zipfile.ZipFile(self.archive) as z:
   self.assertEqual(set(z.namelist()), {'manifest.json', A, B})
  if os.name != 'nt': self.assertEqual(stat.S_IMODE(self.archive.stat().st_mode), 0o600)
  def census():
   return {p.relative_to(self.root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
           for p in self.root.rglob('*') if p.is_file()}
  before = census()
  self.assertEqual(b.preview_restore(self.root, self.archive, self.sha), self.preview)
  self.assertEqual(census(), before)
  self.untouched()

 def test_confirm_restore_idempotency_and_reviewed_undo(self):
  with self.assertRaises(b.ReleaseError):
   b.apply_restore(self.root, self.archive, self.sha, self.plan, self.ident)
  self.assertEqual(self.apply()['status'], 'restored')
  self.assertEqual(self.apply()['status'], 'already_restored')
  self.assertEqual((self.root / A).read_text(), 'backup one')
  saved = b.tx_file(self.root, self.ident, 'before', A)
  self.assertEqual(saved.read_text(), 'newer local answer')
  preview = b.preview_undo(self.root, self.ident)
  with self.assertRaises(b.ReleaseError): b.undo(self.root, preview['plan'], preview['review_sha256'])
  result = b.undo(self.root, preview['plan'], preview['review_sha256'], confirmed=True)
  self.assertEqual(result['removed'], [B])
  self.assertEqual((self.root / A).read_text(), 'newer local answer')
  self.assertFalse((self.root / B).exists())
  self.assertEqual(b.undo(self.root, preview['plan'], preview['review_sha256'], confirmed=True)['status'], 'already_undone')
  self.assertEqual(b.tx_file(self.root, self.ident, 'after', B).read_text(), 'backup two')
  self.untouched()

 def test_changed_current_state_requires_new_preview(self):
  self.write(A, 'later edit')
  with self.assertRaises(b.ReleaseError): self.apply()
  self.assertEqual((self.root / A).read_text(), 'later edit')
  self.assertFalse((self.root / B).exists())
  self.untouched()

 def test_changed_review_or_archive_is_rejected(self):
  changed = copy.deepcopy(self.plan)
  changed['files'][A]['before'] = None
  with self.assertRaises(b.ReleaseError): b.apply_restore(self.root, self.archive, self.sha, changed, self.ident, confirmed=True)
  with self.assertRaises(b.ReleaseError): b.apply_restore(self.root, self.archive, '0' * 64, self.plan, self.ident, confirmed=True)
  changed = copy.deepcopy(self.plan)
  changed['root'] = str(self.base)
  with self.assertRaises(b.ReleaseError): b.apply_restore(self.root, self.archive, self.sha, changed, b.digest(b.encoded(changed)), confirmed=True)
  self.assertEqual((self.root / A).read_text(), 'newer local answer')

 def test_partial_restore_recovers_without_rewriting_completed_file(self):
  with self.assertRaises(b.ReleaseError): self.apply(fail_after=1)
  before = (self.root / A).stat().st_mtime_ns
  self.assertEqual(b.recover(self.root)['status'], 'restored')
  self.assertEqual((self.root / A).stat().st_mtime_ns, before)
  self.assertEqual(b.recover(self.root)['status'], 'no_pending_learning_restore')
  self.untouched()

 def test_later_edit_holds_interrupted_recovery_and_undo(self):
  with self.assertRaises(b.ReleaseError): self.apply(fail_after=1)
  self.write(A, 'later edit during interrupted restore')
  with self.assertRaises(b.ReleaseError): b.recover(self.root)
  self.assertEqual((self.root / A).read_text(), 'later edit during interrupted restore')
  self.assertFalse((self.root / B).exists())
  self.assertTrue((self.root / b.JOURNAL).exists())
  self.untouched()

 def test_undo_refuses_later_edits_after_preview(self):
  self.apply()
  preview = b.preview_undo(self.root, self.ident)
  self.write(B, 'later course work')
  with self.assertRaises(b.ReleaseError): b.undo(self.root, preview['plan'], preview['review_sha256'], confirmed=True)
  with self.assertRaises(b.ReleaseError): b.preview_undo(self.root, self.ident)
  self.assertEqual((self.root / B).read_text(), 'later course work')
  self.untouched()

 def test_interrupted_undo_and_recovery_preserve_bytes(self):
  self.apply()
  preview = b.preview_undo(self.root, self.ident)
  with self.assertRaises(b.ReleaseError): b.undo(self.root, preview['plan'], preview['review_sha256'], confirmed=True, fail_after=1)
  self.assertEqual(b.recover(self.root)['status'], 'undone')
  self.assertEqual((self.root / A).read_text(), 'newer local answer')
  self.assertFalse((self.root / B).exists())
  self.untouched()

 def test_undo_damaged_retained_bytes_refused_before_any_write(self):
  self.apply()
  b.tx_file(self.root, self.ident, 'before', A).write_text('corrupted')
  with self.assertRaises(b.ReleaseError): b.preview_undo(self.root, self.ident)
  self.assertEqual((self.root / A).read_text(), 'backup one')

 def test_every_atomic_interruption_can_resume_or_recover(self):
  # Actual replace first, then injected lost response at each of nine durable writes.
  original = b.atomic
  for stop in range(1, 10):
   with self.subTest(stop=stop), tempfile.TemporaryDirectory() as td:
    root = Path(td).resolve() / 'work'
    (root / b.PREFIX).mkdir(parents=True)
    (root / A).write_text('superseded')
    preview = b.preview_restore(root, self.archive, self.sha)
    count = [0]
    def interrupted(*args, **kwargs):
     original(*args, **kwargs)
     count[0] += 1
     if count[0] == stop: raise OSError('synthetic process termination')
    with patch.object(b, 'atomic', side_effect=interrupted):
     with self.assertRaises(OSError): b.apply_restore(root, self.archive, self.sha, preview['plan'], preview['review_sha256'], confirmed=True)
    if (root / b.JOURNAL).exists(): b.recover(root)
    else: b.apply_restore(root, self.archive, self.sha, preview['plan'], preview['review_sha256'], confirmed=True)
    self.assertEqual((root / A).read_text(), 'backup one')
    self.assertEqual((root / B).read_text(), 'backup two')
    self.assertEqual(b.tx_file(root, preview['review_sha256'], 'before', A).read_text(), 'superseded')

 def test_partial_preparation_never_discards_later_edits(self):
  original = b.atomic
  def interrupted(*args, **kwargs):
   original(*args, **kwargs)
   raise OSError('synthetic interruption')
  with patch.object(b, 'atomic', side_effect=interrupted):
   with self.assertRaises(OSError): self.apply()
  self.write(A, 'edit after partial preparation')
  with self.assertRaises(b.ReleaseError): self.apply()
  self.assertEqual((self.root / A).read_text(), 'edit after partial preparation')
  self.assertEqual(b.tx_file(self.root, self.ident, 'before', A).read_text(), 'newer local answer')

 def test_selection_boundary_and_backup_recursion(self):
  for names in ([], [A, A], [A, A.upper()], ['.aibl-local/package-history.json'], [b.PREFIX + '../package-history.json'], ['/tmp/no'], [b.PREFIX + 'nested\\file']):
   with self.subTest(names=names), self.assertRaises(b.ReleaseError): b.preview_restore(self.root, self.archive, self.sha, names)
  with self.assertRaises(b.ReleaseError): b.backup(self.root, self.root / 'backup.zip', [A])
  with self.assertRaises(b.ReleaseError): b.backup(self.root, self.archive, [A])
  self.assertEqual(b.preview_restore(self.root, self.archive, self.sha, [A])['plan']['files'].keys(), {A})

 @unittest.skipIf(os.name == 'nt', 'Symlink permission is an independent Windows gate')
 def test_symlink_source_external_parent_and_history_refused(self):
  link = self.root / b.PREFIX / 'link.json'
  link.symlink_to(self.root / A)
  with self.assertRaises(b.ReleaseError): b.backup(self.root, self.base / 'link.zip', [b.PREFIX + 'link.json'])
  alias = self.base / 'alias'
  alias.symlink_to(self.base, target_is_directory=True)
  with self.assertRaises(b.ReleaseError): b.preview_restore(self.root, alias / 'private.zip', self.sha)
  with self.assertRaises(b.ReleaseError): b.backup(self.root, alias / 'new.zip', [A])
  (self.root / b.HISTORY).symlink_to(self.base, target_is_directory=True)
  with self.assertRaises(b.ReleaseError): self.apply()

 def test_archive_member_contract(self):
  cases = [('.aibl-local/package-history.json', stat.S_IFREG),
           (b.PREFIX + '../other.json', stat.S_IFREG),
           (A, stat.S_IFLNK), (A, stat.S_IFIFO)]
  for i, (name, mode) in enumerate(cases):
   with self.subTest(name=name, mode=mode):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as z:
     z.writestr('manifest.json', b.encoded({'schema_version': 'aibl.local-learning-backup/v1', 'files': {name: b.digest(b'value')}}))
     info = zipfile.ZipInfo(name); info.external_attr = (mode | 0o600) << 16
     z.writestr(info, b'value')
    archive = self.base / f'bad-{i}.zip'; archive.write_bytes(out.getvalue())
    with self.assertRaises(b.ReleaseError): b.preview_restore(self.root, archive, b.digest(out.getvalue()))

 def test_mode_change_invalidates_review(self):
  if os.name == 'nt': self.skipTest('Windows ACLs require native qualification')
  (self.root / A).chmod(0o444)
  with self.assertRaises(b.ReleaseError): self.apply()

 def test_cli_plan_and_confirmation(self):
  script = Path(b.__file__)
  plan = self.base / 'restore-plan.json'
  def run(*args):
   result = subprocess.run([sys.executable, str(script), *args, '--root', str(self.root)], capture_output=True, text=True)
   self.assertNotIn('newer local answer', result.stdout)
   self.assertNotIn('backup one', result.stdout)
   return result, json.loads(result.stdout)
  result, preview = run('preview', '--file', str(self.archive), '--sha256', self.sha, '--plan', str(plan))
  self.assertEqual(result.returncode, 0)
  args = ('apply', '--file', str(self.archive), '--sha256', self.sha, '--plan', str(plan), '--review-sha256', preview['review_sha256'])
  self.assertEqual(run(*args)[0].returncode, 1)
  self.assertEqual(run(*args, '--confirm')[1]['status'], 'restored')
  self.untouched()


if __name__ == '__main__': unittest.main()
