"""Verified Agent family composition and recoverable updates in an existing workbench.

Reuses release_files atomic writes, safe paths and kernel operation lock from
Internal's MIT-reviewed v3 helper. Historical releases keep their own verifier.
A trusted lock is supplied independently of packages. No publication or grants.
"""
from __future__ import annotations
import argparse, io, json, os, re, shutil, stat, subprocess, sys, time, zipfile
from pathlib import Path
from release_files import ReleaseError, atomic, digest, encoded, under, lock
PRODUCTS={'agent-workbench','agent-essentials','agent-workforce'}
MAX_BYTES=32*1024*1024
MARKER='.aibl/family.json'

def read(path):return json.loads(Path(path).read_text())
def load_lock(path,expected,engine=None):
    raw=Path(path).read_bytes()
    if len(raw)>65536 or not re.fullmatch('[0-9a-f]{64}',expected or '') or digest(raw)!=expected:raise ReleaseError('Family lock integrity mismatch')
    d=json.loads(raw)
    if set(d)!={'schema_version','installer_revision','template_revision','packages','compatibility'} or d['schema_version']!='aibl.family-lock/v1':raise ReleaseError('Family lock contract')
    if not re.fullmatch('[0-9a-f]{40}',d.get('template_revision','')):raise ReleaseError('Missing exact template revision')
    if not re.fullmatch('[0-9a-f]{40}',d['installer_revision']):raise ReleaseError('Missing exact installer revision')
    if set(d['packages'])!=PRODUCTS:raise ReleaseError('Family must bind template, Essentials and Workforce independently')
    for product,pin in d['packages'].items():
        if set(pin)!={'version','manifest_sha256','archive_sha256','publisher'} or not re.fullmatch(r'0\.[0-9]+\.[0-9]+(?:-[a-z0-9.-]+)?',pin['version']):raise ReleaseError('Package pin contract')
        if pin['publisher']!='aibuild-lab/'+product or any(not re.fullmatch('[0-9a-f]{64}',pin[k]) for k in ['manifest_sha256','archive_sha256']):raise ReleaseError('Package publisher or hash contract')
    if d['compatibility']!={'legacy_template':'aibuild-lab/agent-essentials','legacy_workforce_product':'agent-native-workforce','legacy_workforce_publisher':'aibuild-lab/agent-native-workforce'}:raise ReleaseError('Historical identity mapping required')
    if engine:
        root=Path(engine)
        head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
        dirty=subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip()
        if head!=d['installer_revision'] or dirty:raise ReleaseError('Use the clean installer revision named by this family lock')
    return d

def verify(bundle,product,pin):
    root=Path(bundle)/product;mb=(root/'manifest.json').read_bytes();ab=(root/'payload.zip').read_bytes()
    if len(mb)>2*1024*1024 or len(ab)>MAX_BYTES or digest(mb)!=pin['manifest_sha256'] or digest(ab)!=pin['archive_sha256']:raise ReleaseError('Package integrity mismatch: '+product)
    m=json.loads(mb)
    if set(m)!={'schema_version','product','version','source_repository','source_revision','files'} or m['schema_version']!='aibl.family-package/v1' or m['product']!=product or m['version']!=pin['version'] or m['source_repository']!='aibuild-lab/agent-native-workforce-internal' or not re.fullmatch('[0-9a-f]{40}',m['source_revision']):raise ReleaseError('Package manifest contract')
    rows={};fold=set()
    for row in m['files']:
        if set(row)!={'path','sha256','mode','policy'} or row['policy'] not in ['supplied','seed'] or row['mode'] not in [420,493] or not re.fullmatch('[0-9a-f]{64}',row['sha256']):raise ReleaseError('Invalid file policy')
        name=row['path'];under(root,name)
        allowed=(product=='agent-workbench' and row['policy']=='seed' and (name in ['README.md','AGENTS.md','CLAUDE.md','.gitignore','.aibl/template.json'] or name.startswith(('context/','library/','work/')))) or (product=='agent-essentials' and row['policy']=='supplied' and name.startswith(('course/essentials/','blueprints/','.agents/skills/','.claude/skills/','scripts/','starter/','.aibl/capabilities-'))) or (product=='agent-workforce' and name.startswith(('course/workforce/','workforce/')))
        if not allowed or name.casefold() in fold:raise ReleaseError('File ownership boundary: '+name)
        if 'done-for-the-day' in name or 'done-for-day' in name:raise ReleaseError('Habit skill must be student authored')
        fold.add(name.casefold());rows[name]=row
    if not rows:raise ReleaseError('Empty package')
    payload={}
    with zipfile.ZipFile(io.BytesIO(ab)) as z:
        infos=z.infolist()
        if len(infos)!=len(rows) or set(i.filename for i in infos)!=set(rows) or sum(i.file_size for i in infos)>MAX_BYTES:raise ReleaseError('Archive member contract')
        for i in infos:
            if i.is_dir() or stat.S_IFMT(i.external_attr>>16) not in [0,stat.S_IFREG]:raise ReleaseError('Nonregular package member')
            raw=z.read(i)
            if digest(raw)!=rows[i.filename]['sha256']:raise ReleaseError('Payload hash mismatch')
            payload[i.filename]=raw
    return m,payload

def filesystem_mode(mode):
    # Windows chmod exposes the read-only bit, not POSIX executable/owner bits.
    return (0o666 if mode & stat.S_IWRITE else 0o444) if os.name=='nt' else mode

def snapshot(root,name):
    p=under(root,name)
    if p.exists() and not p.is_file():raise ReleaseError('File collision: '+name)
    return {'hash':digest(p.read_bytes()),'mode':stat.S_IMODE(p.stat().st_mode)} if p.exists() else None

def compose(root,bundles,family,products,fail_after=None):
    root=Path(root).resolve()
    if not set(products)<=PRODUCTS:raise ReleaseError('Unknown product')
    with lock(root) as local:
        journal=under(root,'.aibl-local/family-transaction.json')
        if journal.exists():raise ReleaseError('Interrupted update: run family recover first')
        marker=under(root,MARKER);prior=read(marker) if marker.exists() else {'schema_version':'aibl.installed-family/v1','packages':{},'files':{}}
        if prior.get('schema_version')!='aibl.installed-family/v1' or not isinstance(prior.get('files'),dict) or not isinstance(prior.get('packages'),dict):raise ReleaseError('Invalid installed family record')
        # A legacy manifest supplies previous managed hashes, never ownership of personal roots.
        if not prior['packages']:
            legacy=under(root,'.aibl/installed-agent-essentials.json')
            if legacy.exists():
                old=read(legacy)
                if old.get('schema_version')!='aibl.course-release/v3' or old.get('product')!='agent-essentials' or not isinstance(old.get('files'),list):raise ReleaseError('Invalid legacy Essentials manifest')
                for row in old['files']:
                    name=row['path'];under(root,name)
                    if name.startswith(('course/essentials/','.claude/skills/','.agents/skills/','scripts/','starter/','.aibl/capabilities-')):
                        prior['files'][name]={**row,'product':'agent-essentials','policy':'supplied'}
        # Updating a family re-verifies every installed package, never silently binds old bytes to new versions.
        selected=set(products)|set(prior['packages'])
        if 'agent-workforce' in selected and 'agent-essentials' not in selected:raise ReleaseError('Install Essentials before Workforce')
        after=json.loads(json.dumps(prior));changes={};conflicts=[];legacy_transition=not prior['packages']
        for product in sorted(selected):
            m,payload=verify(bundles,product,family['packages'][product]);previous_pin=prior['packages'].get(product)
            if previous_pin and previous_pin['version']==m['version'] and previous_pin!=family['packages'][product]:raise ReleaseError('Immutable version changed; use a new package version')
            if previous_pin and tuple(map(int,m['version'].split('-')[0].split('.')))<tuple(map(int,previous_pin['version'].split('-')[0].split('.'))):raise ReleaseError('Use recorded rollback for version downgrade')
            rows={r['path']:r for r in m['files']}
            owned={n:r for n,r in prior['files'].items() if r['product']==product}
            for name in sorted(set(owned)|set(rows)):
                old=owned.get(name);new=rows.get(name);current=snapshot(root,name)
                if legacy_transition and old and not new:
                    after['files'].pop(name,None);continue
                other=prior['files'].get(name)
                if other and other['product']!=product:raise ReleaseError('Cross-package ownership collision: '+name)
                if new and new['policy']=='seed':
                    if current is None and not old:changes[name]=(payload[name],new['mode'])
                    after['files'][name]={**new,'product':product};continue
                if old and old['policy']=='seed':raise ReleaseError('Student-owned seed cannot become supplied: '+name)
                if old and (current is None or current['hash']!=old['sha256']):conflicts.append(name);continue
                if not old and current and (not new or current['hash']!=new['sha256']):conflicts.append(name);continue
                if new:
                    if current is None or current['hash']!=new['sha256'] or current['mode']!=filesystem_mode(new['mode']):changes[name]=(payload[name],new['mode'])
                    after['files'][name]={**new,'product':product}
                else:changes[name]=(None,None);after['files'].pop(name,None)
            after['packages'][product]=family['packages'][product]
        if conflicts:raise ReleaseError('Changed supplied files preserved; review diffs and save a copy before restoring supplied bytes and retrying: '+', '.join(conflicts))
        after['family']=family
        newraw=encoded(after)
        if marker.exists() and marker.read_bytes()==newraw and not changes:return {'status':'already_installed'}
        changes[MARKER]=(newraw,420)
        tx=under(root,'.aibl-local/family-backups/'+str(time.time_ns()));tx.mkdir(parents=True)
        plan={'backup':tx.name,'before':{},'after':{},'complete':False}
        for name,(raw,mode) in changes.items():
            before=snapshot(root,name);plan['before'][name]=before;plan['after'][name]={'hash':digest(raw),'mode':filesystem_mode(mode)} if raw is not None else None
            if before:atomic(under(tx,name),under(root,name).read_bytes(),before['mode'])
        atomic(journal,encoded(plan),384)
        for i,(name,(raw,mode)) in enumerate(changes.items()):
            p=under(root,name)
            if raw is None:p.unlink(missing_ok=True)
            else:atomic(p,raw,mode)
            if fail_after and i+1>=fail_after:raise ReleaseError('Synthetic interruption; run recover')
        plan['complete']=True;atomic(tx/'transaction.json',encoded(plan),384);journal.unlink()
        return {'status':'installed','products':sorted(selected),'rollback':tx.name}

def recover(root,backup=None):
    root=Path(root).resolve()
    with lock(root) as local:
        journal=under(root,'.aibl-local/family-transaction.json')
        if backup and journal.exists():raise ReleaseError('Recover interrupted transaction before rollback')
        if backup and not re.fullmatch('[0-9]+',backup):raise ReleaseError('Invalid backup identity')
        plan=read(under(root,'.aibl-local/family-backups/'+backup+'/transaction.json') if backup else journal)
        if not re.fullmatch('[0-9]+',plan['backup']):raise ReleaseError('Invalid journal backup identity')
        tx=under(root,'.aibl-local/family-backups/'+plan['backup'])
        for name,before in plan['before'].items():
            current=snapshot(root,name)
            if current not in [before,plan['after'][name]]:raise ReleaseError('Work changed since update; preserve and resolve: '+name)
            if before and snapshot(tx,name)!=before:raise ReleaseError('Backup integrity mismatch: '+name)
        for name,before in plan['before'].items():
            if before:atomic(under(root,name),under(tx,name).read_bytes(),before['mode'])
            else:under(root,name).unlink(missing_ok=True)
        if not backup:journal.unlink()
        tx.rename(tx.with_name(tx.name+'-restored'))
        return {'status':'restored'}

def verify_student_access(root,products):
    from course_setup import command
    user=json.loads(command(['gh','api','user']))
    remote=command(['git','remote','get-url','origin'],cwd=root)
    match=re.fullmatch(r'(?:https://github.com/|git@github.com:)([^/]+/[^/]+?)(?:\.git)?',remote)
    if not match:raise ReleaseError('Use a verified GitHub workbench origin')
    full=match.group(1);meta=json.loads(command(['gh','api','repos/'+full]))
    if not meta.get('private') or meta.get('owner',{}).get('login','').lower()!=user.get('login','').lower():raise ReleaseError('Signed-in account must own this private student workbench')
    for product in products:
        command(['gh','api','repos/aibuild-lab/'+product])
    return user['login']

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['apply','recover','rollback']);p.add_argument('--root',required=True);p.add_argument('--lock');p.add_argument('--sha256');p.add_argument('--bundles');p.add_argument('--product',action='append',choices=sorted(PRODUCTS));p.add_argument('--backup');a=p.parse_args()
    try:
        if a.command=='apply':
            if not a.lock or not a.bundles or not a.product:raise ReleaseError('Reviewed lock, digest, bundles and products required')
            family=load_lock(a.lock,a.sha256,Path(__file__).resolve().parents[1]);verify_student_access(a.root,a.product);result=compose(a.root,a.bundles,family,a.product)
        else:result=recover(a.root,a.backup if a.command=='rollback' else None)
        print(json.dumps(result));return 0
    except (ValueError,OSError,KeyError,zipfile.BadZipFile,subprocess.SubprocessError) as e:print(json.dumps({'status':'blocked','recovery':str(e)}));return 1
if __name__=='__main__':sys.exit(main())
