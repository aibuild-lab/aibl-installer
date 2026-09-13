"""Explicit private backup and missing-file restoration of local learning state.

Separate from Git. No upload, account access, global settings or release backup.
"""
import argparse,io,json,os,stat,sys,zipfile
from pathlib import Path
from release_files import ReleaseError,under,atomic,digest,encoded,lock
PREFIX='.aibl-local/learning/'
LIMIT=32*1024*1024

def backup(root,destination):
 root=Path(root).resolve();target=Path(destination).absolute()
 if target.is_symlink() or target.exists() or target.resolve().is_relative_to(root):raise ReleaseError('Choose a new private backup file outside the workbench')
 files={};rows={}
 with lock(root):
  folder=under(root,PREFIX.rstrip('/'))
  for p in sorted(folder.rglob('*')) if folder.exists() else []:
   name=p.relative_to(root).as_posix();under(root,name)
   if p.is_file():
    raw=p.read_bytes();files[name]=raw;rows[name]=digest(raw)
  if not files:raise ReleaseError('No local learning files to back up')
  if sum(map(len,files.values()))>LIMIT:raise ReleaseError('Learning backup exceeds limit')
  b=io.BytesIO()
  with zipfile.ZipFile(b,'w') as z:
   z.writestr('manifest.json',encoded({'schema_version':'aibl.local-learning-backup/v1','files':rows}))
   for name,raw in files.items():z.writestr(name,raw)
  # Exclusive creation prevents accidental replacement of an existing private backup.
  fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  with os.fdopen(fd,'wb') as stream:stream.write(b.getvalue());stream.flush();os.fsync(stream.fileno())
 return {'status':'backed_up','files':len(files),'sha256':digest(b.getvalue()),'scope':'local learning only; store privately'}

def restore(root,archive,expected):
 raw=Path(archive).read_bytes()
 if len(raw)>LIMIT or digest(raw)!=expected:raise ReleaseError('Backup integrity mismatch')
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  infos=z.infolist()
  if sum(i.file_size for i in infos)>LIMIT or len({i.filename for i in infos})!=len(infos):raise ReleaseError('Invalid backup members')
  m=json.loads(z.read('manifest.json'))
  if m.get('schema_version')!='aibl.local-learning-backup/v1' or set(i.filename for i in infos)!=set(m['files'])|{'manifest.json'}:raise ReleaseError('Backup manifest contract')
  files={}
  for name,h in m['files'].items():
   if not name.startswith(PREFIX):raise ReleaseError('Outside local learning scope')
   p=under(root,name);content=z.read(name)
   if digest(content)!=h:raise ReleaseError('Backup file integrity mismatch')
   files[name]=content
 with lock(root):
  for name,content in files.items():
   p=under(root,name)
   if p.exists() and (not p.is_file() or p.read_bytes()!=content):raise ReleaseError('Existing learning state differs; preserve and review before restoring: '+name)
  for name,content in files.items():
   p=under(root,name)
   if not p.exists():atomic(p,content,0o600)
 return {'status':'restored','files':len(files),'scope':'local learning only; no course credit inferred'}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['backup','restore']);p.add_argument('--root',required=True);p.add_argument('--file',required=True);p.add_argument('--sha256');a=p.parse_args()
 try:print(json.dumps(backup(a.root,a.file) if a.command=='backup' else restore(a.root,a.file,a.sha256)));return 0
 except (ValueError,OSError,KeyError,zipfile.BadZipFile) as e:print(json.dumps({'status':'blocked','recovery':str(e)}));return 1
if __name__=='__main__':sys.exit(main())
