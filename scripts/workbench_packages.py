"""Verified Agent family composition and recoverable updates in an existing workbench.

Reuses release_files atomic writes, safe paths and kernel operation lock from
Internal's MIT-reviewed v3 helper. Historical releases keep their own verifier.
A trusted lock is supplied independently of packages. No publication or grants.
"""
from __future__ import annotations
import argparse, datetime, io, json, os, re, shutil, stat, subprocess, sys, time, zipfile
from contextlib import nullcontext
from pathlib import Path
from release_files import ReleaseError, atomic, digest, encoded, under, lock
LEGACY_PRODUCTS={'agent-workbench','agent-essentials','agent-workforce'}
PRODUCTS=LEGACY_PRODUCTS|{'workbench-core'}
PUBLIC_TEMPLATE='aibuild-lab/my-workbench-template'
V2_PUBLISHERS={p:PUBLIC_TEMPLATE for p in ('agent-workbench','workbench-core','agent-essentials')}
V2_PUBLISHERS['agent-workforce']='aibuild-lab/agent-workforce'
CORE_SKILLS={'aibl-enroll','aibl-personalize','aibl-checkpoint'}
MAX_BYTES=32*1024*1024
MARKER='.aibl/family.json'
SYNC_PENDING='.aibl-local/student-update-sync.json'

def require_no_pending_sync(root):
    if under(root,SYNC_PENDING).exists():raise ReleaseError('Resume the existing student update synchronization before package changes; preserve its journal')

def read(path):return json.loads(Path(path).read_text())
def release_tag(product,version):
    return (product+'-v' if product in ('workbench-core','agent-essentials') else 'v')+version

def validate_pin(product,pin,successor=False):
    fields={'version','manifest_sha256','archive_sha256','publisher'}
    if successor:fields|={'release_tag','release_target'}
    if not isinstance(pin,dict) or set(pin)!=fields:raise ReleaseError('Package pin contract')
    version_key(pin['version'])
    publisher=V2_PUBLISHERS.get(product) if successor else 'aibuild-lab/'+product
    if pin['publisher']!=publisher or any(not re.fullmatch('[0-9a-f]{64}',pin[k]) for k in ('manifest_sha256','archive_sha256')):raise ReleaseError('Package publisher or hash contract')
    if successor and (pin['release_tag']!=release_tag(product,pin['version']) or not re.fullmatch('[0-9a-f]{40}',pin['release_target'])):raise ReleaseError('Exact release identity required')

def validate_family(d):
    if not isinstance(d,dict) or set(d)!={'schema_version','installer_revision','template_revision','packages','compatibility'} or d['schema_version'] not in ('aibl.family-lock/v1','aibl.family-lock/v2'):raise ReleaseError('Family lock contract')
    successor=d['schema_version']=='aibl.family-lock/v2'
    if not re.fullmatch('[0-9a-f]{40}',d.get('template_revision','')):raise ReleaseError('Missing exact template revision')
    if not re.fullmatch('[0-9a-f]{40}',d['installer_revision']):raise ReleaseError('Missing exact installer revision')
    if not isinstance(d['packages'],dict):raise ReleaseError('Family package contract')
    if successor:
        if not {'agent-workbench','workbench-core'}<=set(d['packages'])<=PRODUCTS:raise ReleaseError('Family requires template and core, with only supported optional programs')
    elif set(d['packages'])!=LEGACY_PRODUCTS:raise ReleaseError('Family must bind template, Essentials and Workforce independently')
    for product,pin in d['packages'].items():validate_pin(product,pin,successor)
    if successor and d['packages']['agent-workbench']['release_target']!=d['template_revision']:raise ReleaseError('Template release target differs from template revision')
    if d['compatibility']!={'legacy_template':'aibuild-lab/agent-essentials','legacy_workforce_product':'agent-native-workforce','legacy_workforce_publisher':'aibuild-lab/agent-native-workforce'}:raise ReleaseError('Historical identity mapping required')
    return d

def load_lock(path,expected,engine=None):
    raw=Path(path).read_bytes()
    if len(raw)>65536 or not re.fullmatch('[0-9a-f]{64}',expected or '') or digest(raw)!=expected:raise ReleaseError('Family lock integrity mismatch')
    d=validate_family(json.loads(raw))
    if engine:
        root=Path(engine)
        head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
        dirty=subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip()
        if head!=d['installer_revision'] or dirty:raise ReleaseError('Use the clean installer revision named by this family lock')
    return d

def verify(bundle,product,pin):
    successor='release_tag' in pin
    validate_pin(product,pin,successor)
    root=Path(bundle)/product;mb=(root/'manifest.json').read_bytes();ab=(root/'payload.zip').read_bytes()
    if len(mb)>2*1024*1024 or len(ab)>MAX_BYTES or digest(mb)!=pin['manifest_sha256'] or digest(ab)!=pin['archive_sha256']:raise ReleaseError('Package integrity mismatch: '+product)
    m=json.loads(mb)
    if set(m)!=({'schema_version','product','version','source_repository','source_revision','files'} | ({'components'} if m.get('schema_version')=='aibl.family-package/v2' else set())) or m['schema_version'] not in ('aibl.family-package/v1','aibl.family-package/v2') or m['product']!=product or m['version']!=pin['version'] or m['source_repository']!='aibuild-lab/agent-native-workforce-internal' or not re.fullmatch('[0-9a-f]{40}',m['source_revision']):raise ReleaseError('Package manifest contract')
    rows={};fold=set()
    for row in m['files']:
        if set(row)!={'path','sha256','mode','policy'} or row['policy'] not in ['supplied','seed'] or row['mode'] not in [420,493] or not re.fullmatch('[0-9a-f]{64}',row['sha256']):raise ReleaseError('Invalid file policy')
        name=row['path'];under(root,name)
        allowed=(product=='agent-workbench' and row['policy']=='seed' and (name in ['README.md','AGENTS.md','CLAUDE.md','.gitignore','.aibl/template.json'] or name.startswith(('context/','library/','work/')))) or (product=='agent-essentials' and row['policy']=='supplied' and name.startswith(('course/essentials/','blueprints/','.agents/skills/','.claude/skills/','scripts/','starter/','.aibl/capabilities-'))) or (product=='agent-workforce' and name.startswith(('course/workforce/','workforce/')))
        if successor:
            if product=='agent-workbench':allowed=row['policy']=='seed' and (allowed or name in ('LICENSE','blueprints/.gitkeep','blueprints/README.md'))
            elif product=='agent-essentials':allowed=row['policy']=='supplied' and name in ('course/essentials/START-HERE.md','blueprints/youtube-transcripts.md')
            elif product=='workbench-core':
                allowed=row['policy']=='supplied' and (name=='.aibl/licenses/workbench-core-MIT.txt' or any(name.startswith(client+'/skills/'+skill+'/') for client in ('.agents','.claude') for skill in CORE_SKILLS))
                if m['schema_version']!='aibl.family-package/v2':raise ReleaseError('Core requires component-aware manifest')
            elif product=='agent-workforce':
                allowed=allowed or (row['policy']=='supplied' and name in ('.aibl/workforce-student-edition.json','.claude/skills/aibl-workforce/SKILL.md','.agents/skills/aibl-workforce/SKILL.md'))
        if not allowed or name.casefold() in fold:raise ReleaseError('File ownership boundary: '+name)
        if 'done-for-the-day' in name or 'done-for-day' in name:raise ReleaseError('Habit skill must be student authored')
        fold.add(name.casefold());rows[name]=row
    if not rows:raise ReleaseError('Empty package')
    version_key(m['version'])
    validate_components(m,rows)
    if product=='workbench-core':
        expected_ids={'workbench.method.'+name for name in CORE_SKILLS}
        if {c['id'] for c in m.get('components',[])}!=expected_ids:raise ReleaseError('Core requires exactly three versioned skill components')
        for name in CORE_SKILLS:
            entries={client+'/skills/'+name+'/SKILL.md' for client in ('.agents','.claude')}
            component=next(c for c in m['components'] if c['id']=='workbench.method.'+name)
            if component['kind']!='skill' or component['requires'] or not entries<=set(component['files']) or not entries<=set(rows):raise ReleaseError('Core requires paired native skill exposures without course dependencies')
            if len({rows[path]['sha256'] for path in entries})!=1:raise ReleaseError('Core native exposures differ')
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

def validate_components(manifest,rows):
    components=manifest.get('components',[])
    if not isinstance(components,list):raise ReleaseError('Invalid components')
    if any(not isinstance(c,dict) or set(c)!={'id','kind','version','content_date','files','requires'} or not all(isinstance(c[k],str) for k in ('id','kind','version','content_date')) or not isinstance(c['files'],list) or not all(isinstance(n,str) for n in c['files']) or not isinstance(c['requires'],list) for c in components):raise ReleaseError('Component contract')
    ids=[c['id'] for c in components]
    if ids!=sorted(set(ids)):raise ReleaseError('Component IDs must be sorted and unique')
    by_id={c['id']:c for c in components}
    for c in components:
        if set(c)!={'id','kind','version','content_date','files','requires'} or not re.fullmatch(r'[a-z0-9]+(?:[._-][a-z0-9]+)*',c['id']) or c['kind'] not in ('agent','skill'):raise ReleaseError('Component contract')
        version_key(c['version'])
        if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',c['content_date']):raise ReleaseError('Component date contract')
        try:datetime.date.fromisoformat(c['content_date'])
        except ValueError as e:raise ReleaseError('Component date contract') from e
        if not c['files'] or c['files']!=sorted(set(c['files'])) or not set(c['files'])<=set(rows):raise ReleaseError('Component file closure')
        if any(not isinstance(d,dict) or set(d)!={'id','version'} or not all(isinstance(v,str) for v in d.values()) for d in c['requires']):raise ReleaseError('Component dependency contract')
        deps=[d['id'] for d in c['requires']]
        if deps!=sorted(set(deps)):raise ReleaseError('Component dependencies must be sorted and unique')
        for d in c['requires']:
            if set(d)!={'id','version'} or d['id'] not in by_id or by_id[d['id']]['version']!=d['version']:raise ReleaseError('Component dependency contract')
    def visit(key,trail):
        if key in trail:raise ReleaseError('Component dependency cycle')
        for dep in by_id[key]['requires']:visit(dep['id'],trail|{key})
    for key in by_id:visit(key,set())

def component_signature(c,rows):
    return {**c,'files':[{k:rows[n][k] for k in ('path','sha256','mode','policy')} for n in c['files']]}

def filesystem_mode(mode):
    # Windows chmod exposes the read-only bit, not POSIX executable/owner bits.
    return (0o666 if mode & stat.S_IWRITE else 0o444) if os.name=='nt' else mode

def snapshot(root,name):
    p=under(root,name)
    if p.exists() and not p.is_file():raise ReleaseError('File collision: '+name)
    return {'hash':digest(p.read_bytes()),'mode':stat.S_IMODE(p.stat().st_mode)} if p.exists() else None

def version_key(value):
    match=re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?',value)
    if not match:raise ReleaseError('Invalid semantic version')
    pre=match[4]
    if pre and any(x.isdigit() and len(x)>1 and x.startswith('0') for x in pre.split('.')):raise ReleaseError('Invalid semantic version')
    return tuple(int(match[i]) for i in (1,2,3))+(pre is None,tuple((0,int(x)) if x.isdigit() else (1,x) for x in pre.split('.')) if pre else ())

def status(root):
    root=Path(root).resolve();marker=under(root,MARKER)
    if under(root,SYNC_PENDING).exists():return {'status':'recovery_required','update_availability':'unknown','recovery':'Resume the existing student update synchronization'}
    if under(root,'.aibl-local/family-transaction.json').exists():return {'status':'recovery_required','update_availability':'unknown'}
    if not marker.exists():return {'status':'not_installed','update_availability':'unknown'}
    prior=read(marker)
    if prior.get('schema_version')!='aibl.installed-family/v1':raise ReleaseError('Invalid installed family record')
    customized=[];missing=[]
    for name,row in prior['files'].items():
        current=snapshot(root,name)
        if current is None:missing.append(name)
        elif current!={'hash':row['sha256'],'mode':filesystem_mode(row['mode'])}:customized.append(name)
    return {'status':'installed','supplied_packages':prior['packages'],'customized':sorted(customized),'missing':sorted(missing),'update_availability':'unknown'}

def compose(root,bundles,family,products,fail_after=None,preview=False):
    root=Path(root).resolve()
    if not set(products)<=PRODUCTS:raise ReleaseError('Unknown product')
    with (nullcontext() if preview else lock(root)) as local:
        require_no_pending_sync(root)
        journal=under(root,'.aibl-local/family-transaction.json')
        if journal.exists():raise ReleaseError('Interrupted update: run family recover first')
        history_path=under(root,'.aibl-local/family-history.json')
        history=read(history_path) if history_path.exists() else {'packages':{},'components':{}}
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
        successor=family.get('schema_version')=='aibl.family-lock/v2'
        if successor:
            validate_family(family)
            if not {'agent-workbench','workbench-core'}<=selected:raise ReleaseError('Install template and core before optional packages')
            if not selected<=set(family['packages']):raise ReleaseError('Installed combination is not admitted by this family')
        elif 'workbench-core' in selected:raise ReleaseError('Core requires family-lock v2')
        elif 'agent-workforce' in selected and 'agent-essentials' not in selected:raise ReleaseError('Install Essentials before Workforce')
        after=json.loads(json.dumps(prior));changes={};conflicts=[];comparisons=[];legacy_transition=not prior['packages']
        for product in sorted(selected):
            m,payload=verify(bundles,product,family['packages'][product]);previous_pin=prior['packages'].get(product)
            if previous_pin and previous_pin['version']==m['version'] and previous_pin!=family['packages'][product]:raise ReleaseError('Immutable version changed; use a new package version')
            if previous_pin and version_key(m['version'])<version_key(previous_pin['version']):raise ReleaseError('Use recorded rollback for version downgrade')
            package_key=product+'@'+m['version']
            if package_key in history['packages'] and history['packages'][package_key]!=family['packages'][product]:raise ReleaseError('Immutable historical package version changed')
            history['packages'][package_key]=family['packages'][product]
            rows={r['path']:r for r in m['files']}
            for c in m.get('components',[]):
                component_key=product+'/'+c['id']+'@'+c['version'];signature=component_signature(c,rows)
                if component_key in history['components'] and history['components'][component_key]!=signature:raise ReleaseError('Immutable component version changed in history')
                history['components'][component_key]=signature
            old_components=prior.get('components',{}).get(product,[])
            if (old_components or any(k.startswith(product+'/') for k in history['components'])) and m['schema_version']=='aibl.family-package/v1':raise ReleaseError('Component history cannot downgrade to v1')
            old_by_id={c['id']:c for c in old_components}
            for c in m.get('components',[]):
                old_c=old_by_id.get(c['id'])
                if old_c and version_key(c['version'])<version_key(old_c['version']):raise ReleaseError('Component version downgrade')
                if old_c and c['version']==old_c['version'] and component_signature(c,rows)!=component_signature(old_c,prior['files']):raise ReleaseError('Immutable component version changed')
            component_holds=set()
            for old_c in old_components:
                incoming=next((c for c in m.get('components',[]) if c['id']==old_c['id']),None)
                changed=incoming is None or component_signature(old_c,prior['files'])!=component_signature(incoming,rows)
                if changed and any(snapshot(root,n)!={'hash':prior['files'][n]['sha256'],'mode':filesystem_mode(prior['files'][n]['mode'])} for n in old_c['files']):component_holds.update(old_c['files'])
            required={n for c in m.get('components',[]) for d in c['requires'] for target in m['components'] if target['id']==d['id'] for n in target['files']}
            for name in required:
                if name in prior['files'] and snapshot(root,name) is None:component_holds.add(name)
            conflicts.extend(sorted(component_holds))
            if m['schema_version']=='aibl.family-package/v2':after.setdefault('components',{})[product]=m['components']
            owned={n:r for n,r in prior['files'].items() if r['product']==product}
            for name in sorted(set(owned)|set(rows)):
                old=owned.get(name);new=rows.get(name);current=snapshot(root,name)
                comparisons.append({'path':name,'prior':old,'actual':current,'incoming':new})
                if legacy_transition and old and not new:
                    after['files'].pop(name,None);continue
                other=after['files'].get(name)
                if other and other['product']!=product:raise ReleaseError('Cross-package ownership collision: '+name)
                if new and new['policy']=='seed':
                    if current is None and not old:changes[name]=(payload[name],new['mode'])
                    after['files'][name]={**new,'product':product};continue
                if old and old['policy']=='seed':raise ReleaseError('Student-owned seed cannot become supplied: '+name)
                if old and current!={'hash':old['sha256'],'mode':filesystem_mode(old['mode'])}:
                    # A retained local edit/deletion is not permission to restore supplied bytes.
                    if new and all(old[k]==new[k] for k in ('sha256','mode','policy')):
                        after['files'][name]={**new,'product':product};continue
                    conflicts.append(name);continue
                if not old and current:conflicts.append(name);continue
                if new:
                    if current is None or current['hash']!=new['sha256'] or current['mode']!=filesystem_mode(new['mode']):changes[name]=(payload[name],new['mode'])
                    after['files'][name]={**new,'product':product}
                else:changes[name]=(None,None);after['files'].pop(name,None)
            after['packages'][product]=family['packages'][product]
        if preview:return {'status':'needs_review' if conflicts else 'ready','conflicts':sorted(set(conflicts)),'comparison':comparisons,'changes':[{'path':n,'action':'remove' if raw is None else 'write','prior':prior['files'].get(n),'actual':snapshot(root,n),'incoming':after['files'].get(n)} for n,(raw,mode) in sorted(changes.items())],'supplied_packages':after['packages'],'update_availability':'reviewed_local_candidate'}
        if conflicts:raise ReleaseError('Changed supplied files preserved; review diffs and save a copy before restoring supplied bytes and retrying: '+', '.join(conflicts))
        atomic(history_path,encoded(history),384)
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

def repair(root,bundles,product,paths,expected,fail_after=None):
    """Explicitly restore selected installed supplied bytes, retaining local copies.

    expected is the caller-reviewed path -> snapshot map; changes since that
    review refuse the operation. This does not advance the installed package.
    """
    root=Path(root).resolve()
    if not paths or len(paths)!=len(set(paths)) or set(expected)!=set(paths):raise ReleaseError('Explicit unique paths and reviewed snapshots required')
    with lock(root):
        require_no_pending_sync(root)
        journal=under(root,'.aibl-local/family-transaction.json')
        if journal.exists():raise ReleaseError('Recover interrupted transaction first')
        prior=read(under(root,MARKER))
        if prior.get('schema_version')!='aibl.installed-family/v1' or not isinstance(prior.get('packages'),dict) or not isinstance(prior.get('files'),dict):raise ReleaseError('Invalid installed family record')
        if product not in prior['packages']:raise ReleaseError('Product not installed')
        manifest,payload=verify(bundles,product,prior['packages'][product])
        rows={row['path']:row for row in manifest['files']}
        for name in paths:
            old=prior['files'].get(name);row=rows.get(name)
            if not old or old.get('product')!=product or old.get('policy')!='supplied' or not row or any(old[k]!=row[k] for k in ('sha256','mode','policy')):raise ReleaseError('Only installed supplied files can be repaired')
            if snapshot(root,name)!=expected[name]:raise ReleaseError('Work changed since repair review: '+name)
        tx=under(root,'.aibl-local/family-backups/'+str(time.time_ns()));tx.mkdir(parents=True)
        plan={'backup':tx.name,'before':{},'after':{},'complete':False}
        for name in paths:
            before=snapshot(root,name);plan['before'][name]=before
            plan['after'][name]={'hash':rows[name]['sha256'],'mode':filesystem_mode(rows[name]['mode'])}
            if before:atomic(under(tx,name),under(root,name).read_bytes(),before['mode'])
        # Recheck after backup and before journaling any destructive writes.
        if any(snapshot(root,n)!=expected[n] for n in paths):raise ReleaseError('Work changed while preparing repair')
        atomic(journal,encoded(plan),384)
        for i,name in enumerate(paths):
            if snapshot(root,name)!=expected[name]:raise ReleaseError('Work changed during repair; recover transaction')
            atomic(under(root,name),payload[name],rows[name]['mode'])
            if fail_after and i+1>=fail_after:raise ReleaseError('Synthetic interruption; run recover')
        plan['complete']=True;atomic(tx/'transaction.json',encoded(plan),384);journal.unlink()
        return {'status':'repaired','paths':sorted(paths),'rollback':tx.name}

def recover(root,backup=None):
    root=Path(root).resolve()
    with lock(root) as local:
        require_no_pending_sync(root)
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
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['apply','preview','status','repair','recover','rollback']);p.add_argument('--root',required=True);p.add_argument('--lock');p.add_argument('--sha256');p.add_argument('--bundles');p.add_argument('--product',action='append',choices=sorted(PRODUCTS));p.add_argument('--backup');p.add_argument('--reviewed-repair',help='JSON path to explicitly reviewed path/snapshot map');a=p.parse_args()
    try:
        if a.command in ('apply','preview'):
            if not a.lock or not a.bundles or not a.product:raise ReleaseError('Reviewed lock, digest, bundles and products required')
            family=load_lock(a.lock,a.sha256,Path(__file__).resolve().parents[1]);
            if a.command=='apply':verify_student_access(a.root,a.product)
            result=compose(a.root,a.bundles,family,a.product,preview=a.command=='preview')
        elif a.command=='repair':
            if not a.bundles or not a.product or len(a.product)!=1 or not a.reviewed_repair:raise ReleaseError('One installed product, bundles and reviewed repair snapshots required')
            verify_student_access(a.root,a.product)
            expected=read(a.reviewed_repair)
            result=repair(a.root,a.bundles,a.product[0],list(expected),expected)
        elif a.command=='status':result=status(a.root)
        else:result=recover(a.root,a.backup if a.command=='rollback' else None)
        print(json.dumps(result));return 0
    except (ValueError,OSError,KeyError,zipfile.BadZipFile,subprocess.SubprocessError) as e:print(json.dumps({'status':'blocked','recovery':str(e)}));return 1
if __name__=='__main__':sys.exit(main())
