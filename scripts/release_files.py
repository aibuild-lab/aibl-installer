"""Portable, standard-library release verification and recoverable file adoption.

The caller supplies a reviewed pin through a trusted channel. Hashes prove bytes,
not that an arbitrary author or pin is trusted. Never accept a pin from an archive.
"""
from __future__ import annotations
import argparse, contextlib, hashlib, json, os, re, shutil, stat, sys, tempfile, zipfile
from pathlib import Path, PurePosixPath

PRODUCTS = {'agent-essentials', 'agent-native-workforce'}
MAX_BYTES = 16 * 1024 * 1024
class ReleaseError(ValueError): pass

def digest(data): return hashlib.sha256(data).hexdigest()
def encoded(data): return (json.dumps(data, sort_keys=True, indent=2)+'\n').encode()
def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))
@contextlib.contextmanager
def process_guard(path):
    """Kernel-owned lock; a crashed process releases it automatically.

    The small guard file persists, so file existence is never interpreted as a
    live process. Each caller separately preserves historical O_EXCL locks.
    """
    path=Path(path)
    if path.is_symlink():raise ReleaseError('Operation guard must not be a symlink')
    fd=os.open(path,os.O_RDWR|os.O_CREAT|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(fd,'r+b',buffering=0) as stream:
        try:
            if os.fstat(stream.fileno()).st_size==0:stream.write(b'0')
            stream.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc:raise ReleaseError('Another process holds this operation lock. Close the duplicate operation and retry.') from exc
        try:yield
        finally:
            stream.seek(0)
            if os.name=='nt':msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)
def atomic(path, data, mode=None):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.aibl-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(data);f.flush()
            if mode is not None:os.chmod(tmp,mode)
            os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
def safe(path):
    if not isinstance(path,str) or not path or '\\' in path or ':' in path or '\x00' in path: raise ReleaseError('unsafe path')
    p=PurePosixPath(path)
    if p.is_absolute() or p.as_posix()!=path or any(x in {'','.','..'} or x.endswith((' ','.')) or re.match(r'(?i)^(con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\.|$)',x) for x in p.parts):raise ReleaseError('unsafe path: '+path)
    if any(x.lower() in {'.git','.env','answers','private','facilitator','intake','node_modules','__pycache__'} for x in p.parts):raise ReleaseError('forbidden path: '+path)
    return p

def under(root, name):
    safe(name);root=Path(root).resolve();path=root/name
    for p in [path,*path.parents]:
        if p==root:break
        if p.is_symlink():raise ReleaseError('symlink collision: '+name)
    if not path.resolve().is_relative_to(root):raise ReleaseError('path escaped root')
    return path

def destination(name, product):
    safe(name)
    if name=='.aibl/capabilities-'+product+'.json':return
    # Reviewed v3 discovery representations only. Configuration, global client
    # settings and student-owned profiles are deliberately not release targets.
    if re.fullmatch(r'\.agents/skills/aibl-[a-z0-9-]+/SKILL\.md', name):return
    if product=='agent-native-workforce' and re.fullmatch(r'\.codex/agents/aibl-[a-z0-9-]+\.toml', name):return
    allowed=('course/','workflows/','starter/','.claude/agents/','.claude/skills/','scripts/')
    if product=='agent-essentials' and name in {'README.md','CLAUDE.md','AGENTS.md','.gitignore','NOTICE.md'}:return
    if not name.startswith(allowed):raise ReleaseError('unreviewable destination: '+name)
    if name.startswith('scripts/') and '/' in name[len('scripts/'):]:raise ReleaseError('nested executable destination')

def verify(bundle, pin, product):
    bundle=Path(bundle); pin=read(pin) if not isinstance(pin,dict) else pin
    if product not in PRODUCTS or set(pin)!= {'schema_version','product','release_id','source_revision','manifest_sha256','archive_sha256'} or pin['schema_version']!='aibl.release-pin/v3' or pin['product']!=product:raise ReleaseError('wrong release target or pin contract')
    mb=(bundle/'manifest.json').read_bytes();ab=(bundle/'payload.zip').read_bytes()
    if len(ab)>MAX_BYTES or digest(mb)!=pin['manifest_sha256'] or digest(ab)!=pin['archive_sha256']:raise ReleaseError('release integrity mismatch')
    m=json.loads(mb)
    if set(m)!= {'schema_version','product','release_id','source_repository','source_revision','files'} or m['schema_version']!='aibl.course-release/v3' or m['source_repository']!='aibuild-lab/agent-native-workforce-internal':raise ReleaseError('manifest contract')
    for k in ('product','release_id','source_revision'):
        if m[k]!=pin[k]:raise ReleaseError('pin identity mismatch: '+k)
    if not re.fullmatch('[0-9a-f]{40}',m['source_revision']) or not re.fullmatch('[a-z0-9.-]+',m['release_id']):raise ReleaseError('invalid release identity')
    entries={};sources=set();fold=set()
    for f in m['files']:
        if set(f)!={'source','path','sha256','mode'} or f['mode'] not in [420,493] or not re.fullmatch('[0-9a-f]{64}',f['sha256']):raise ReleaseError('invalid file contract')
        destination(f['path'],product);safe(f['source'])
        if f['path'].casefold() in fold or f['source'] in sources:raise ReleaseError('duplicate source or destination')
        fold.add(f['path'].casefold());sources.add(f['source']);entries[f['path']]=f
    if not entries:raise ReleaseError('empty release')
    import io
    payload={}
    with zipfile.ZipFile(io.BytesIO(ab)) as z:
        infos=z.infolist()
        if len(infos)!=len(entries) or {x.filename for x in infos}!=set(entries) or sum(x.file_size for x in infos)>MAX_BYTES:raise ReleaseError('undeclared, duplicate or oversized archive member')
        for info in infos:
            mode=info.external_attr>>16
            if info.is_dir() or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0,stat.S_IFREG)):raise ReleaseError('nonregular archive member')
            value=z.read(info)
            if digest(value)!=entries[info.filename]['sha256']:raise ReleaseError('payload hash mismatch')
            payload[info.filename]=value
    verify_capability_payload(payload,product)
    return m,payload

def verify_capability_payload(payload, product):
    """Validate declared reusable files before writes; historical releases omit catalogs."""
    name='.aibl/capabilities-'+product+'.json'
    if name not in payload:return
    import posixpath
    catalog=json.loads(payload[name])
    if catalog.get('schema_version')!='aibl.capability-catalog/v1' or not isinstance(catalog.get('capabilities'),list):raise ReleaseError('Invalid capability catalog')
    items={};declared={}
    for item in catalog['capabilities']:
        if not isinstance(item,dict) or set(item)!={'name','kind','files','requires','ownership','license','provenance'}:raise ReleaseError('Invalid capability declaration')
        if item['name'] in items or item['ownership']!='supplied' or item['license']!='MIT' or not item['provenance']:raise ReleaseError('Invalid capability ownership or provenance')
        items[item['name']]=item
        for path,expected in item['files'].items():
            safe(path)
            if path not in payload or digest(payload[path])!=expected:raise ReleaseError('Missing capability file: '+path)
            if not (path.startswith(('.claude/skills/aibl-','.claude/agents/aibl-','scripts/aibl','scripts/anw','starter/licenses/','workflows/licenses/'))
                    or re.fullmatch(r'\.agents/skills/aibl-[a-z0-9-]+/SKILL\.md',path)
                    or re.fullmatch(r'\.codex/agents/aibl-[a-z0-9-]+\.toml',path)):raise ReleaseError('Curriculum cannot enter reusable capability scope')
            declared[path]=expected
    essentials={'aibl-'+x for x in ['setup','checkpoint','diagnose','teach','adopt-workforce','next-project','personalize','what-do-i-have','clarity-brief']}
    external=essentials if product=='agent-native-workforce' else set()
    active=set();done=set()
    def visit(name):
        if name in external and name not in items:return
        if name not in items:raise ReleaseError('Missing capability dependency: '+str(name))
        if name in active:raise ReleaseError('Cyclic capability dependency: '+name)
        if name in done:return
        active.add(name)
        for dep in items[name]['requires']:visit(dep)
        active.remove(name);done.add(name)
    for name in items:visit(name)
    for path in declared:
        if not path.endswith('.md') or not path.startswith('.claude/'):continue
        content=payload[path].decode('utf-8')
        for link in re.findall(r'\[[^\]]*\]\(([^)]+)\)',content):
            if re.match(r'[a-zA-Z]+://',link) or link.startswith('#'):continue
            reference=posixpath.normpath(posixpath.join(posixpath.dirname(path),link.split('#')[0]))
            if reference not in declared:raise ReleaseError('Missing capability supporting reference: '+reference)
        if path.startswith('.claude/agents/'):
            front=content.split('---',2)[1] if content.startswith('---') else ''
            block=re.search(r'^skills:\s*\n((?:[ \t]+-[^\n]+\n?)+)',front,re.M)
            owner=next((v for v in items.values() if path in v['files'] and v['kind']=='profile'),None)
            if block:
                for dep in re.findall(r'-\s*(aibl-[a-z-]+)',block[1]):
                    if not owner or dep not in owner['requires']:raise ReleaseError('Undeclared preloaded skill: '+dep)

@contextlib.contextmanager
def lock(root):
    d=Path(root)/'.aibl-local'
    for part in [d,Path(root)/'.aibl',d/'release-backups']:
        if part.is_symlink():raise ReleaseError('State directory must not be a symlink')
    d.mkdir(exist_ok=True)
    if (d/'release.lock').exists() or (d/'release.lock').is_symlink():raise ReleaseError('A historical release lock exists. Diagnose that older operation before recovery; do not delete it blindly.')
    with process_guard(d/'release.guard'):yield d

def installed(root,product):
    p=Path(root)/'.aibl'/('installed-'+product+'.json')
    if p.is_symlink():raise ReleaseError('installed state symlink')
    return read(p) if p.exists() else None

def check_distribution_pin(root,pin,product):
    """A qualified workbench cannot silently replace its frozen product tuple."""
    path=under(root,'.aibl/distribution.json')
    if not path.exists():return
    if not path.is_file() or path.stat().st_size>65536:raise ReleaseError('Frozen distribution record is invalid; preserve it for review')
    record=read(path)
    pins=record.get('source_release_pins') if isinstance(record,dict) else None
    if (not isinstance(record,dict) or record.get('schema_version')!='aibl.installed-distribution/v1'
            or not isinstance(pins,dict) or set(pins)!=PRODUCTS
            or any(not isinstance(pins[p],dict) or pins[p].get('product')!=p for p in PRODUCTS)):
        raise ReleaseError('Frozen distribution record is invalid; preserve it for review')
    if pin!=pins[product]:raise ReleaseError('Release differs from this workbench frozen distribution. Review a new distribution explicitly before changing its release tuple; no files were changed.')

def candidate_path(value, directory=False):
    """Explicit local transport only; reject links before resolving ancestors."""
    if not isinstance(value,str) or not value or not Path(value).is_absolute():raise ReleaseError('Candidate transport needs an explicit absolute local path')
    path=Path(value)
    if '..' in path.parts or any(p.is_symlink() for p in [path,*path.parents]):raise ReleaseError('Candidate transport cannot use symlink or traversal paths')
    if not (path.is_dir() if directory else path.is_file()):raise ReleaseError('Candidate input is missing; explicitly relink the same frozen distribution')
    if not directory and path.stat().st_size>MAX_BYTES:raise ReleaseError('Candidate input exceeds the reviewed release size limit')
    return path

def candidate_inputs(root,bundle,distribution_lock,distribution_sha256):
    root=Path(root).resolve();bundle=candidate_path(bundle,True);lock_path=candidate_path(distribution_lock)
    if lock_path.stat().st_size>65536:raise ReleaseError('Candidate distribution lock is oversized')
    data=lock_path.read_bytes()
    if not re.fullmatch('[a-f0-9]{64}',distribution_sha256 or '') or digest(data)!=distribution_sha256:raise ReleaseError('Candidate lock differs from its independent digest')
    distribution=json.loads(data);installed_record=read(under(root,'.aibl/distribution.json'))
    if (not isinstance(distribution,dict) or set(distribution)!={'schema_version','course_id','installer','source_release_pins'}
            or distribution['schema_version']!='aibl.course-distribution/v1' or distribution['course_id']!='agent-native-workforce'
            or not isinstance(distribution['source_release_pins'],dict) or set(distribution['source_release_pins'])!=PRODUCTS
            or not isinstance(distribution['installer'],dict)
            or distribution['installer'].get('repository')!='aibuild-lab/workshop-installer'):
        raise ReleaseError('Candidate distribution has an invalid source contract')
    installer=distribution['installer']
    expected_files={'start.sh','start.ps1','course-options.json','scripts/course_setup.py','scripts/pinned_distribution.py'}
    if (set(installer)!={'repository','commit','files'} or not isinstance(installer['commit'],str)
            or not re.fullmatch('[a-f0-9]{40}',installer['commit']) or not isinstance(installer['files'],dict)
            or set(installer['files'])!=expected_files
            or any(not isinstance(sha,str) or not re.fullmatch('[a-f0-9]{64}',sha) for sha in installer['files'].values())):
        raise ReleaseError('Candidate installer provenance is incomplete or invalid')
    if (not isinstance(installed_record,dict) or installed_record.get('delivery_mode')!='local_candidate'
            or installed_record.get('distribution_sha256')!=distribution_sha256
            or installed_record.get('source_release_pins')!=distribution['source_release_pins']
            or installed_record.get('installer_commit')!=distribution['installer'].get('commit')):
        raise ReleaseError('Candidate transport differs from the project frozen distribution; no fallback is allowed')
    if any(not isinstance(p,dict) for p in distribution['source_release_pins'].values()) or len({p.get('source_revision') for p in distribution['source_release_pins'].values()})!=1:
        raise ReleaseError('Candidate products have different source revisions')
    for product in sorted(PRODUCTS):
        candidate_path(str(bundle/product),True)
        for name in ('manifest.json','payload.zip'):candidate_path(str(bundle/product/name))
        pin=distribution['source_release_pins'][product]
        check_distribution_pin(root,pin,product)
        verify(bundle/product,pin,product)
    return distribution

def candidate_relink(root,bundle,distribution_lock,distribution_sha256):
    """After a move or re-clone, reverify both products before changing transport."""
    root=Path(root).resolve()
    distribution=candidate_inputs(root,bundle,distribution_lock,distribution_sha256)
    record={'schema_version':'aibl.candidate-transport/v1','project_root':str(root),
            'bundle_root':str(candidate_path(bundle,True)),
            'distribution_lock':str(candidate_path(distribution_lock)),
            'distribution_sha256':distribution_sha256,
            'source_revision':distribution['source_release_pins']['agent-essentials']['source_revision']}
    path=under(root,'.aibl-local/candidate-distribution.json')
    path.parent.mkdir(parents=True,exist_ok=True)
    with process_guard(under(root,'.aibl-local/candidate-transport.lock')):
        atomic(path,encoded(record),0o600)
    return {'status':'candidate_transport_verified','distribution_sha256':distribution_sha256,'source_revision':record['source_revision']}

def candidate(root,product,apply_files=False):
    root=Path(root).resolve();record=read(under(root,'.aibl-local/candidate-distribution.json'))
    if (not isinstance(record,dict) or set(record)!={'schema_version','project_root','bundle_root','distribution_lock','distribution_sha256','source_revision'}
            or record['schema_version']!='aibl.candidate-transport/v1' or record['project_root']!=str(root)):
        raise ReleaseError('Candidate transport is missing or moved; explicitly relink and verify the frozen distribution')
    distribution=candidate_inputs(root,record['bundle_root'],record['distribution_lock'],record['distribution_sha256'])
    if product not in PRODUCTS or record['source_revision']!=distribution['source_release_pins'][product]['source_revision']:
        raise ReleaseError('Candidate source revision or product differs from local provenance')
    bundle=Path(record['bundle_root'])/product;pin=distribution['source_release_pins'][product]
    # apply rereads and verifies exact pinned bytes, then checks the frozen tuple
    # again under its existing transaction lock. Earlier verification is never
    # used as permission to apply a different buffer.
    if apply_files:return apply(root,bundle,pin,product)
    manifest,payload=verify(bundle,pin,product);preflight(root,manifest,payload)
    return {'status':'candidate_verified','release_id':manifest['release_id'],'files':len(manifest['files'])}

def preflight(root,m,payload):
    root=Path(root);previous=installed(root,m['product']);old={x['path']:x for x in previous['files']} if previous else {}
    new={x['path']:x for x in m['files']};conflicts=[]
    for name in sorted(set(old)|set(new)):
        p=under(root,name)
        if name in old:
            if not p.is_file() or digest(p.read_bytes())!=old[name]['sha256']:conflicts.append(name)
        elif p.exists() and (not p.is_file() or p.read_bytes()!=payload[name]):conflicts.append(name)
    if conflicts:raise ReleaseError('Local changes or collisions: '+', '.join(conflicts)+'. Save or review them; no files were changed.')
    return previous,old,new

def apply(root,bundle,pin,product, fail_after=None):
    root=Path(root).resolve();pin=read(pin) if not isinstance(pin,dict) else dict(pin);m,payload=verify(bundle,pin,product)
    with lock(root) as local:
        check_distribution_pin(root,pin,product)
        journal=local/'release-transaction.json'
        if journal.exists():raise ReleaseError('Interrupted transaction exists. Run recover before importing.')
        previous,old,new=preflight(root,m,payload)
        if previous==m:return {'status':'already_installed','release_id':m['release_id']}
        tx=local/'release-backups'/m['release_id']
        if tx.exists():raise ReleaseError('Backup identity already exists; recover or choose a new immutable release.')
        tx.mkdir(parents=True)
        touched=sorted(set(old)|set(new));before={};before_modes={}
        for name in touched:
            p=under(root,name)
            before[name]=digest(p.read_bytes()) if p.exists() else None
            before_modes[name]=stat.S_IMODE(p.stat().st_mode) if p.exists() else None
            if p.exists(): atomic(tx/name,p.read_bytes())
        state=Path('.aibl')/('installed-'+product+'.json')
        plan={'product':product,'previous':previous,'next':m,'before':before,'before_modes':before_modes,'after':{x:new[x]['sha256'] if x in new else None for x in touched},'backup':m['release_id'],'applied':[],'complete':False}
        atomic(journal,encoded(plan))
        for i,name in enumerate(touched):
            p=under(root,name)
            if name in new:atomic(p,payload[name],new[name]['mode'])
            else:p.unlink()
            plan['applied'].append(name);atomic(journal,encoded(plan))
            if fail_after is not None and i+1>=fail_after:raise ReleaseError('Synthetic interrupted apply; recover the journal')
        atomic(root/state,encoded(m));plan['complete']=True
        atomic(tx/'transaction.json',encoded(plan));journal.unlink()
        return {'status':'installed','release_id':m['release_id'],'files':len(new)}

def restore(root,plan,tx):
    root=Path(root);tx=Path(tx)
    prior_modes={entry['path']:entry['mode'] for entry in (plan.get('previous') or {}).get('files',[])}
    modes={}
    # Inspect all files before any write, including a crash between write and journal update.
    for name,before in plan['before'].items():
        p=under(root,name);current=digest(p.read_bytes()) if p.is_file() else None
        if p.exists() and not p.is_file():raise ReleaseError('Recovery collision: '+name)
        if current not in {before,plan['after'][name]}:raise ReleaseError('Work changed since import; preserve and resolve: '+name)
        if before is not None and (not (tx/name).is_file() or digest((tx/name).read_bytes())!=before):raise ReleaseError('Backup integrity mismatch')
        if before is not None:
            mode=plan.get('before_modes',prior_modes).get(name)
            if type(mode) is not int or not 0<=mode<=0o7777:raise ReleaseError('Prior file permissions are unavailable; preserve the transaction for review: '+name)
            modes[name]=mode
    for name,before in plan['before'].items():
        p=under(root,name)
        if before is None:p.unlink(missing_ok=True)
        else:atomic(p,(tx/name).read_bytes(),modes[name])
    state=root/'.aibl'/('installed-'+plan['product']+'.json')
    if plan['previous'] is None:state.unlink(missing_ok=True)
    else:atomic(state,encoded(plan['previous']))

def recover(root, release_id=None):
    with lock(root) as local:
        if release_id:
            if not re.fullmatch('[a-z0-9.-]+',release_id):raise ReleaseError('invalid backup identity')
            tx=local/'release-backups'/release_id;plan=read(tx/'transaction.json')
            if installed(root,plan['product'])!=plan['next']:raise ReleaseError('Rollback is not for the currently installed release')
        else:
            plan=read(local/'release-transaction.json');tx=local/'release-backups'/plan['backup']
        restore(root,plan,tx)
        if not release_id:(local/'release-transaction.json').unlink()
        # Retain immutable backups, but retire their identity so reapplying is possible.
        archived=tx.with_name(tx.name+'-recovered-'+str(__import__('time').time_ns()));tx.rename(archived)
        return {'status':'restored','release_id':plan['next']['release_id']}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['verify','apply','recover','rollback','candidate-verify','candidate-apply','candidate-relink']);p.add_argument('--root',default='.');p.add_argument('--bundle');p.add_argument('--pin');p.add_argument('--product',choices=sorted(PRODUCTS));p.add_argument('--release-id');p.add_argument('--distribution-lock');p.add_argument('--distribution-sha256');p.add_argument('--json',action='store_true');a=p.parse_args()
    try:
        if a.command=='candidate-relink':
            if a.pin or not all([a.bundle,a.distribution_lock,a.distribution_sha256]):raise ReleaseError('Relink requires the explicit bundle, independent distribution lock and digest; no replacement product pin')
            result=candidate_relink(a.root,a.bundle,a.distribution_lock,a.distribution_sha256)
        elif a.command in {'candidate-verify','candidate-apply'}:
            if any([a.bundle,a.pin,a.distribution_lock,a.distribution_sha256]) or not a.product:raise ReleaseError('Candidate application uses only the verified local transport and frozen product; relink explicitly to move it')
            result=candidate(a.root,a.product,a.command=='candidate-apply')
        elif a.command in {'verify','apply'}:
            if not all([a.bundle,a.pin,a.product]):raise ReleaseError('bundle, reviewed pin and product required')
            pin=read(a.pin)
            if a.command=='apply':result=apply(a.root,a.bundle,pin,a.product)
            else:
                m,payload=verify(a.bundle,pin,a.product);check_distribution_pin(a.root,pin,a.product);preflight(a.root,m,payload);result={'status':'verified','release_id':m['release_id'],'files':len(m['files'])}
        else:result=recover(a.root,a.release_id if a.command=='rollback' else None)
        print(json.dumps(result) if a.json else ' | '.join(str(v) for v in result.values()));return 0
    except (ValueError,OSError,KeyError,TypeError,zipfile.BadZipFile) as e:
        print(json.dumps({'status':'blocked','recovery':str(e)}) if a.json else 'Blocked: '+str(e));return 1
if __name__=='__main__':sys.exit(main())
