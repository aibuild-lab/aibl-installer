import os,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import local_learning_backup as b
class LocalLearningBackup(unittest.TestCase):
 def test_restore_independent_of_git(self):
  with tempfile.TemporaryDirectory() as td:
   td=str(Path(td).resolve())
   root=Path(td)/'work';state=root/'.aibl-local/learning/progress.json';state.parent.mkdir(parents=True);state.write_text('student response');backup=Path(td)/'private.zip';r=b.backup(root,backup);state.unlink();b.restore(root,backup,r['sha256']);self.assertEqual(state.read_text(),'student response');self.assertEqual(backup.stat().st_mode&0o777,0o600) if os.name!='nt' else None
 def test_modified_state_and_bad_digest_preserved(self):
  with tempfile.TemporaryDirectory() as td:
   td=str(Path(td).resolve())
   root=Path(td)/'work';state=root/'.aibl-local/learning/progress.json';state.parent.mkdir(parents=True);state.write_text('old');backup=Path(td)/'private.zip';r=b.backup(root,backup);state.write_text('new')
   with self.assertRaises(b.ReleaseError):b.restore(root,backup,r['sha256'])
   with self.assertRaises(b.ReleaseError):b.restore(root,backup,'0'*64)
   self.assertEqual(state.read_text(),'new')
if __name__=='__main__':unittest.main()
