"""Explicit private backup and reviewed restoration of selected local learning state.

Separate from Git. No upload, account access, global settings or release backup.
"""
import argparse,io,json,os,re,stat,sys,zipfile
from pathlib import Path
from release_files import ReleaseError,under,atomic,digest,encoded,lock
PREFIX='.aibl-local/learning/'
LIMIT=32*1024*1024
MAX_FILES=4096
JOURNAL='.aibl-local/learning-restore.json'
HISTORY='.aibl-local/learning-recovery'

def backup(root,destination,paths=None):
 root=checked_root(root);target=external_file(root,destination,new=True)
 files={};rows={};total=0
 with lock(root):
  if under(root,JOURNAL).exists():raise ReleaseError('Recover pending learning restore before backup')
  folder=under(root,PREFIX.rstrip('/'))
  candidates=[under(root,n) for n in selected(root,paths)] if paths is not None else (sorted(folder.rglob('*')) if folder.exists() else [])
  for p in candidates:
   name=p.relative_to(root).as_posix();under(root,name)
   if p.is_file():
    total+=p.stat().st_size
    if total>LIMIT or len(files)>=MAX_FILES:raise ReleaseError('Learning backup exceeds limit')
    raw=p.read_bytes();files[name]=raw;rows[name]=digest(raw)
   elif paths is not None:raise ReleaseError('Selected learning file is missing or not regular')
  if not files:raise ReleaseError('No local learning files to back up')
  if len(files)>MAX_FILES or sum(map(len,files.values()))>LIMIT:raise ReleaseError('Learning backup exceeds limit')
  b=io.BytesIO()
  with zipfile.ZipFile(b,'w') as z:
   z.writestr('manifest.json',encoded({'schema_version':'aibl.local-learning-backup/v1','files':rows}))
   for name,raw in files.items():z.writestr(name,raw)
  if len(b.getvalue())>LIMIT or any(digest(under(root,n).read_bytes())!=h for n,h in rows.items()):raise ReleaseError('Learning state changed or archive exceeds limit; retry after closing active sessions')
  # Exclusive creation prevents accidental replacement of an existing private backup.
  fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  with os.fdopen(fd,'wb') as stream:stream.write(b.getvalue());stream.flush();os.fsync(stream.fileno())
 return {'status':'backed_up','files':len(files),'sha256':digest(b.getvalue()),'scope':'local learning only; store privately'}

def restore(root,archive,expected):
 root=checked_root(root);files=read_payload(root,archive,expected)
 with lock(root):
  if under(root,JOURNAL).exists():raise ReleaseError('Recover pending learning restore before historical missing-file restoration')
  for name,content in files.items():
   p=under(root,name)
   if p.exists() and (not p.is_file() or p.read_bytes()!=content):raise ReleaseError('Existing learning state differs; preserve and review before restoring: '+name)
  for name,content in files.items():
   p=under(root,name)
   if not p.exists():atomic(p,content,0o600)
 return {'status':'restored','files':len(files),'scope':'local learning only; no course credit inferred'}

def checked_root(root):
 p=Path(root).expanduser().absolute()
 if '..' in p.parts or p.is_symlink() or not p.is_dir():raise ReleaseError('Use the existing unlinked workbench root')
 return p.resolve()

def external_file(root,value,new=False):
 p=Path(value).expanduser().absolute()
 if '..' in p.parts or any(x.is_symlink() for x in (p,*p.parents)) or p.resolve().is_relative_to(root):raise ReleaseError('Use an unlinked private file outside the workbench')
 if (new and p.exists()) or (not new and not p.is_file()):raise ReleaseError('Choose a new backup or an existing archive as requested')
 return p

def selected(root,names):
 if not isinstance(names,(list,tuple)) or not names or len(names)>MAX_FILES or any(not isinstance(n,str) for n in names):raise ReleaseError('Select bounded learning files')
 if len({n.casefold() for n in names})!=len(names):raise ReleaseError('Duplicate learning selection')
 for n in names:
  if not n.startswith(PREFIX):raise ReleaseError('Only .aibl-local/learning files can be selected')
  under(root,n)
 return sorted(names)

def state(root,name):
 selected(root,[name]);p=under(root,name)
 if not p.exists():return None
 if not p.is_file() or not stat.S_ISREG(p.stat().st_mode) or p.stat().st_size>LIMIT:raise ReleaseError('Learning state must be a bounded regular file')
 return {'sha256':digest(p.read_bytes()),'mode':stat.S_IMODE(p.stat().st_mode)}

def private_mode():
 # Windows chmod is not an ACL: report its actual regular-file mode, not POSIX privacy.
 return 0o666 if os.name=='nt' else 0o600

def snapshot(value,missing=True):
 if value is None and missing:return
 if not isinstance(value,dict) or set(value)!={'sha256','mode'} or type(value['mode']) is not int or not 0<=value['mode']<=0o777 or not isinstance(value['sha256'],str) or not re.fullmatch('[a-f0-9]{64}',value['sha256']):raise ReleaseError('Invalid learning snapshot')

def read_payload(root,archive,expected):
 p=external_file(root,archive)
 if not isinstance(expected,str) or not re.fullmatch('[a-f0-9]{64}',expected) or p.stat().st_size>LIMIT:raise ReleaseError('Backup integrity mismatch')
 raw=p.read_bytes()
 if len(raw)>LIMIT or digest(raw)!=expected:raise ReleaseError('Backup integrity mismatch')
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  infos=z.infolist()
  if not infos or len(infos)>MAX_FILES+1 or sum(i.file_size for i in infos)>LIMIT or len({i.filename.casefold() for i in infos})!=len(infos) or any(i.is_dir() or stat.S_IFMT(i.external_attr>>16) not in (0,stat.S_IFREG) for i in infos):raise ReleaseError('Invalid backup members')
  m=json.loads(z.read('manifest.json'))
  if not isinstance(m,dict) or set(m)!={'schema_version','files'} or m['schema_version']!='aibl.local-learning-backup/v1' or not isinstance(m['files'],dict) or set(i.filename for i in infos)!=set(m['files'])|{'manifest.json'}:raise ReleaseError('Backup manifest contract')
  files={}
  for n in selected(root,list(m['files'])):
   h=m['files'][n]
   if not isinstance(h,str) or not re.fullmatch('[a-f0-9]{64}',h):raise ReleaseError('Invalid backup file hash')
   content=z.read(n)
   if digest(content)!=h:raise ReleaseError('Backup file integrity mismatch')
   files[n]=content
 return files

def preview_restore(root,archive,expected,paths=None):
 root=checked_root(root);files=read_payload(root,archive,expected)
 names=selected(root,list(files) if paths is None else paths)
 if not set(names)<=set(files):raise ReleaseError('Selected file is absent from this backup')
 rows={n:{'before':state(root,n),'after':{'sha256':digest(files[n]),'mode':private_mode()}} for n in names}
 if any(state(root,n)!=row['before'] for n,row in rows.items()):raise ReleaseError('Learning state changed during preview')
 plan={'schema_version':'aibl.learning-restore-plan/v1','root':str(root),'archive_sha256':expected,'files':rows}
 return {'plan':plan,'review_sha256':digest(encoded(plan))}

def check_review(root,plan,expected,schema):
 if not isinstance(plan,dict) or plan.get('schema_version')!=schema or plan.get('root')!=str(root):raise ReleaseError('Reviewed learning plan identity differs')
 if not isinstance(expected,str) or not re.fullmatch('[a-f0-9]{64}',expected) or digest(encoded(plan))!=expected:raise ReleaseError('Reviewed learning plan digest differs')
 if not isinstance(plan.get('files'),dict):raise ReleaseError('Reviewed learning files contract')
 selected(root,list(plan['files']))

def tx_folder(root,ident):
 if not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{64}',ident):raise ReleaseError('Invalid learning recovery identity')
 return under(root,HISTORY+'/'+ident)

def tx_file(root,ident,side,name):return under(root,HISTORY+'/'+ident+'/'+side+'/'+name)

def record(path):
 if not path.is_file() or path.stat().st_size>LIMIT:raise ReleaseError('Learning record must be a bounded regular file')
 return json.loads(path.read_text(encoding='utf-8'))

def transaction(root,ident):
 folder=tx_folder(root,ident)
 plan=record(under(root,HISTORY+'/'+ident+'/plan.json'));check_review(root,plan,ident,'aibl.learning-restore-plan/v1')
 phase=record(under(root,HISTORY+'/'+ident+'/state.json'))
 if not isinstance(phase,dict) or set(phase)!={'phase','review_sha256'} or phase['review_sha256']!=ident or phase['phase'] not in ('prepared','restored','undone'):raise ReleaseError('Invalid learning recovery record')
 for name,row in plan['files'].items():
  if not isinstance(row,dict) or set(row)!={'before','after'}:raise ReleaseError('Invalid learning snapshot')
  for side in ('before','after'):
   value=row[side]
   snapshot(value,missing=side=='before')
   if value is not None:
    p=tx_file(root,ident,side,name)
    if not p.is_file() or p.stat().st_size>LIMIT or digest(p.read_bytes())!=value['sha256']:raise ReleaseError('Learning recovery bytes are damaged')
 return folder,plan,phase

def drive(root,ident,direction,fail_after=None):
 # Caller holds the shared process guard. Ordinary learning sessions must be closed.
 folder,plan,phase=transaction(root,ident);target='after' if direction=='restore' else 'before'
 if phase['phase'] not in (('prepared','restored') if direction=='restore' else ('restored','undone')):raise ReleaseError('Learning journal conflicts with transaction phase')
 for n,row in plan['files'].items():
  if state(root,n) not in (row['before'],row['after']):raise ReleaseError('Learning state changed after review; preserve it before recovery: '+n)
 changed=0;removed=[]
 for n,row in plan['files'].items():
  actual=state(root,n);wanted=row[target]
  if actual not in (row['before'],row['after']):raise ReleaseError('Learning state changed during restore; preserve the pending transaction')
  if actual==wanted:continue
  if wanted is None:under(root,n).unlink();removed.append(n)
  else:atomic(under(root,n),tx_file(root,ident,target,n).read_bytes(),wanted['mode'])
  changed+=1
  if fail_after and changed>=fail_after:raise ReleaseError('Synthetic learning interruption; run recover')
 phase['phase']='restored' if direction=='restore' else 'undone';atomic(folder/'state.json',encoded(phase),0o600);under(root,JOURNAL).unlink()
 return {'status':phase['phase'],'transaction':ident,'files':len(plan['files']),'removed':removed,'scope':'selected local learning only; no course credit inferred'}

def retain(path,raw):
 # A preparation interrupted before its journal may be resumed, never overwritten.
 if path.exists():
  if not path.is_file() or path.stat().st_size>LIMIT or path.read_bytes()!=raw:raise ReleaseError('Retained learning recovery bytes differ; preserve this transaction')
 else:atomic(path,raw,0o600)

def apply_restore(root,archive,expected,plan,review_sha256,*,confirmed=False,fail_after=None):
 if not confirmed:raise ReleaseError('Explicit confirmation of this reviewed learning restore is required')
 root=checked_root(root);check_review(root,plan,review_sha256,'aibl.learning-restore-plan/v1')
 if set(plan)!={'schema_version','root','archive_sha256','files'} or plan['archive_sha256']!=expected:raise ReleaseError('Reviewed archive binding differs')
 files=read_payload(root,archive,expected);names=selected(root,list(plan['files']))
 for n in names:
  row=plan['files'][n]
  if n not in files or not isinstance(row,dict) or set(row)!={'before','after'} or row['after']!={'sha256':digest(files[n]),'mode':private_mode()}:raise ReleaseError('Reviewed selection differs from backup bytes')
  snapshot(row['before'])
 with lock(root):
  folder=tx_folder(root,review_sha256);journal=under(root,JOURNAL)
  if journal.exists():raise ReleaseError('Recover the pending learning restore before another operation')
  phase_file=under(root,HISTORY+'/'+review_sha256+'/state.json')
  if phase_file.exists():
   _,saved,phase=transaction(root,review_sha256)
   if saved!=plan:raise ReleaseError('Retained learning plan differs')
   if phase['phase']=='restored' and all(state(root,n)==row['after'] for n,row in saved['files'].items()):return {'status':'already_restored','transaction':review_sha256,'files':len(names)}
   if phase['phase']!='prepared':raise ReleaseError('Restore was already used or state changed; preserve work and prepare a fresh preview')
  if any(state(root,n)!=plan['files'][n]['before'] for n in names):raise ReleaseError('Learning state changed since preview; review a new plan')
  folder.mkdir(parents=True,mode=0o700,exist_ok=True)
  for n in names:
   row=plan['files'][n]
   if row['before'] is not None:
    raw=under(root,n).read_bytes()
    if digest(raw)!=row['before']['sha256']:raise ReleaseError('Learning state changed while saving undo')
    retain(tx_file(root,review_sha256,'before',n),raw)
   retain(tx_file(root,review_sha256,'after',n),files[n])
  retain(under(root,HISTORY+'/'+review_sha256+'/plan.json'),encoded(plan));retain(phase_file,encoded({'phase':'prepared','review_sha256':review_sha256}))
  if any(state(root,n)!=plan['files'][n]['before'] for n in names):raise ReleaseError('Learning state changed while preparing restore; no learning files were replaced')
  atomic(journal,encoded({'transaction':review_sha256,'direction':'restore'}),0o600)
  return drive(root,review_sha256,'restore',fail_after)

def recover(root,*,fail_after=None):
 root=checked_root(root)
 if not under(root,JOURNAL).exists():return {'status':'no_pending_learning_restore'}
 with lock(root):
  pending=record(under(root,JOURNAL))
  if not isinstance(pending,dict) or set(pending)!={'transaction','direction'} or pending['direction'] not in ('restore','undo'):raise ReleaseError('Invalid learning restore journal')
  return drive(root,pending['transaction'],pending['direction'],fail_after)

def preview_undo(root,ident):
 root=checked_root(root);_,saved,phase=transaction(root,ident)
 if phase['phase']!='restored' or under(root,JOURNAL).exists():raise ReleaseError('Complete pending restore before reviewing undo')
 if any(state(root,n)!=row['after'] for n,row in saved['files'].items()):raise ReleaseError('Learning state changed after restore; preserve later work before undo')
 plan={'schema_version':'aibl.learning-undo-plan/v1','root':str(root),'transaction':ident,'files':{n:{'before':row['after'],'after':row['before']} for n,row in saved['files'].items()}}
 return {'plan':plan,'review_sha256':digest(encoded(plan))}

def undo(root,plan,review_sha256,*,confirmed=False,fail_after=None):
 if not confirmed:raise ReleaseError('Explicit confirmation of this reviewed learning undo is required')
 root=checked_root(root);check_review(root,plan,review_sha256,'aibl.learning-undo-plan/v1')
 if set(plan)!={'schema_version','root','transaction','files'}:raise ReleaseError('Learning undo plan contract')
 with lock(root):
  folder,saved,phase=transaction(root,plan['transaction']);expected={n:{'before':row['after'],'after':row['before']} for n,row in saved['files'].items()}
  if plan['files']!=expected or under(root,JOURNAL).exists():raise ReleaseError('Undo differs from the reviewed restore or recovery is pending')
  if phase['phase']=='undone' and all(state(root,n)==row['before'] for n,row in saved['files'].items()):return {'status':'already_undone','transaction':plan['transaction']}
  if phase['phase']!='restored' or any(state(root,n)!=row['after'] for n,row in saved['files'].items()):raise ReleaseError('Learning state changed since undo preview; preserve it')
  atomic(under(root,JOURNAL),encoded({'transaction':plan['transaction'],'direction':'undo'}),0o600)
  return drive(root,plan['transaction'],'undo',fail_after)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['backup','restore','preview','apply','recover','undo-preview','undo']);p.add_argument('--root',required=True);p.add_argument('--file');p.add_argument('--sha256');p.add_argument('--path',action='append');p.add_argument('--plan');p.add_argument('--review-sha256');p.add_argument('--confirm',action='store_true');p.add_argument('--transaction');a=p.parse_args()
 try:
  root=checked_root(a.root)
  if a.command in ('backup','restore','preview','apply') and not a.file:raise ReleaseError('Explicit private archive path required')
  if a.command=='backup':result=backup(root,a.file,a.path)
  elif a.command=='restore':
   if a.path:raise ReleaseError('Selected replacements require preview and apply')
   result=restore(root,a.file,a.sha256)
  elif a.command in ('preview','undo-preview'):
   if not a.plan:raise ReleaseError('Choose a new external review-plan file')
   result=preview_restore(root,a.file,a.sha256,a.path) if a.command=='preview' else preview_undo(root,a.transaction)
   target=external_file(root,a.plan,new=True);fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
   with os.fdopen(fd,'wb') as stream:stream.write(encoded(result['plan']));stream.flush();os.fsync(stream.fileno())
   result={'status':'previewed','plan':str(target),'review_sha256':result['review_sha256'],'files':result['plan']['files']}
  elif a.command in ('apply','undo'):
   if not a.plan:raise ReleaseError('Supply the reviewed plan and digest')
   path=external_file(root,a.plan)
   plan=record(path);result=apply_restore(root,a.file,a.sha256,plan,a.review_sha256,confirmed=a.confirm) if a.command=='apply' else undo(root,plan,a.review_sha256,confirmed=a.confirm)
  else:result=recover(root)
  print(json.dumps(result));return 0
 except (ValueError,TypeError,OSError,KeyError,AttributeError,zipfile.BadZipFile) as e:print(json.dumps({'status':'blocked','recovery':str(e)}));return 1
if __name__=='__main__':sys.exit(main())
