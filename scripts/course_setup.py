#!/usr/bin/env python3
"""Shared course selector and resumable private workbench setup. Standard library only."""
from __future__ import annotations
import argparse,contextlib,datetime,hashlib,json,os,platform,re,shutil,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class SetupError(ValueError):
    def __init__(self,message,reason='operation'):
        super().__init__(message);self.reason=reason

def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def command(args,cwd=None,interactive=False):
    child_env={**os.environ,'GH_HOST':'github.com'} if args[0]=='gh' else None
    result=subprocess.run(args,cwd=cwd,text=True,encoding='utf-8',errors='replace',capture_output=not interactive,env=child_env)
    if result.returncode:
        detail=(result.stderr or '').lower()
        reason='authentication_missing' if args[0]=='gh' and result.returncode==4 else 'not_found' if 'http 404' in detail else 'authentication' if 'http 401' in detail else 'permission' if 'http 403' in detail else 'network' if any(t in detail for t in ('could not resolve','connection refused','connection reset','timed out','error connecting','tls handshake','http 429','http 502','http 503')) else 'operation'
        recovery='Check the network connection and retry; access has not been determined.' if reason=='network' else 'Complete the visible action and rerun the same launcher.'
        raise SetupError(f'{args[0]} {args[1] if len(args)>1 else ""} failed. {recovery} No work was removed.',reason)
    return '' if interactive else result.stdout.strip()

def registry():return json.loads((ROOT/'course-options.json').read_text(encoding='utf-8'))
def options():return registry()['programs']
def resolve(program,reg):
    # The registry names programs; setup needs repositories. Required access is strict, included access is reported.
    by_id={p['id']:p for p in reg['programs']}
    for ref in (*program['requires'],*program['includes']):
        if ref not in by_id:raise SetupError(f'Program registry names an unknown program: {ref}. Ask the course team to review the installer.')
    return {**program,'template':reg['hub'].get('template'),'starter':reg['hub'].get('starter'),'access':[by_id[r]['publisher'] for r in program['requires']],'included':[{'id':r,'label':by_id[r]['label'],'publisher':by_id[r]['publisher']} for r in program['includes']]}
def choose(course):
    reg=registry();programs=reg['programs']
    if course:
        for c in programs:
            if c['id']==course:return resolve(c,reg)
        raise SetupError('Unknown program. Use a listed program id.')
    menu=[c for c in programs if c.get('menu')]
    print('Which program are you joining?')
    for i,c in enumerate(menu,1):print(f'{i}. {c["label"]}')
    answer=input('Choose '+' or '.join(str(x) for x in range(1,len(menu)+1))+': ').strip()
    if answer not in [str(x) for x in range(1,len(menu)+1)]:raise SetupError('Choose one listed program; rerun to select again.')
    return resolve(menu[int(answer)-1],reg)

def safe_workspace(path):
    path=Path(path).expanduser().absolute()
    resolved=path.resolve()
    if any(x.lower() in {'desktop','documents'} or any(label in x.lower() for label in ['dropbox','onedrive','icloud','google drive','cloudstorage']) for x in (*path.parts,*resolved.parts)):raise SetupError('Choose a local folder such as ~/GitHub, outside synced Desktop/Documents or cloud storage.')
    if path.is_symlink():raise SetupError('Choose a local folder rather than a symlink.')
    return resolved

def version_tuple(text):
    m=re.search(r'(\d+)\.(\d+)(?:\.(\d+))?',text)
    return tuple(int(x or 0) for x in m.groups()) if m else (0,0,0)

def check_tools(runner=command,desktop=False,harness='claude'):
    h=HARNESSES[harness]
    versions={};minimum={'git':(2,28,0),'gh':(2,0,0),'python':(3,11,0),'node':(18,0,0),h['cli']:h['floor']}
    required=[('git','git'),('gh','gh'),('python',sys.executable)]
    # The desktop preview route verifies files only; the student route also needs Node (the secrets guard runs on it) and the app's command-line twin.
    if not desktop:required+=[('node','node'),(h['cli'],h['cli'])]
    for name,exe in required:
        try:
            lines=runner([exe,'--version']).splitlines()
            if not lines:raise SetupError('Version output is empty')
            text=lines[0]
        except (OSError,SetupError):raise SetupError(f'{name} is missing. Rerun the platform launcher to install only missing requirements.')
        if version_tuple(text)<minimum[name]:raise SetupError(f'{name} is older than the course compatibility floor. Update this tool through its installer, then rerun.')
        versions[name]=text
    return versions

def repo_name(value):
    if not re.fullmatch('[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}',value) or value.lower().endswith(('.git','.')) or re.match(r'(?i)^(con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\.|$)',value):raise SetupError('Choose a portable repository name without slashes, trailing dots, a .git suffix or a Windows reserved device name.')
    return value

def remote_matches(url,full):return url in {f'https://github.com/{full}',f'https://github.com/{full}.git',f'git@github.com:{full}.git'}

# The app the student works in. The command-line twin is what setup verifies and signs in; the desktop app is what the student operates from.
HARNESSES={'claude':{'cli':'claude','floor':(2,1,0),'client':'claude_code','status':['claude','auth','status','--json'],'login':['claude','auth','login'],'label':'Claude Code'},
           'codex':{'cli':'codex','floor':(0,140,0),'client':'codex_cli','status':['codex','login','status'],'login':['codex','login'],'label':'Codex'}}
def choose_harness(harness):
    if harness:
        if harness not in HARNESSES:raise SetupError('Unknown app. Use claude or codex.')
        return harness
    keys=list(HARNESSES)
    print('Which app will you work in?')
    for i,k in enumerate(keys,1):print(f'{i}. {HARNESSES[k]["label"]}')
    answer=input('Choose '+' or '.join(str(x) for x in range(1,len(keys)+1))+': ').strip()
    if answer not in [str(x) for x in range(1,len(keys)+1)]:raise SetupError('Choose one listed app; rerun to select again.')
    return keys[int(answer)-1]
STAGES=('candidate_inputs','tools','github_auth','course_access','private_repository','clone','git_identity','student_context','claude_auth','claude_launch')
STEP_STAGE={'candidate_inputs_verified':'candidate_inputs','tools_verified':'tools','github_verified':'github_auth','course_access_verified':'course_access','private_repository_verified':'private_repository','clone_verified':'clone','local_git_identity_verified':'git_identity','student_context_ready':'student_context','claude_authenticated':'claude_auth','claude_session_returned':'claude_launch'}

def source_provenance():
    value={'setup_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'course_options_sha256':hashlib.sha256((ROOT/'course-options.json').read_bytes()).hexdigest(),'bootstrap':'unmeasured','installer_revision':'unavailable'}
    try:
        p=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,text=True,capture_output=True)
        if p.returncode==0 and re.fullmatch('[0-9a-f]{40,64}',p.stdout.strip()):
            value['installer_revision']=p.stdout.strip()
            status=subprocess.run(['git','status','--porcelain'],cwd=ROOT,text=True,capture_output=True)
            value['installer_dirty']=bool(status.stdout.strip()) if status.returncode==0 else 'unavailable'
    except OSError:pass
    # The platform entry supplies its own file for a hash, never its contents.
    bootstrap=os.environ.get('AIBL_BOOTSTRAP_PATH')
    if bootstrap and Path(bootstrap).is_file():value['bootstrap']={'sha256':hashlib.sha256(Path(bootstrap).read_bytes()).hexdigest()}
    return value

def verify_existing(folder,full,runner=command,require_head=True):
    folder=Path(folder)
    if folder.is_symlink() or not (folder/'.git').exists():raise SetupError('The chosen folder already exists and is not this Git project. Choose a different name; it will not be overwritten.')
    remote=runner(['git','remote','get-url','origin'],cwd=folder)
    if not remote_matches(remote,full):raise SetupError('Existing folder has a different origin. Keep it and choose another name, or ask Claude to review adoption.')
    top=runner(['git','rev-parse','--show-toplevel'],cwd=folder)
    if Path(top).resolve()!=folder.resolve():raise SetupError('Existing Git folder is not the project root. Choose its actual root or another name.')
    if require_head:runner(['git','rev-parse','--verify','HEAD'],cwd=folder)
    return True

@contextlib.contextmanager
def setup_lock(state_root,name):
    if state_root.is_symlink():raise SetupError('Setup state must be a local directory, not a symlink.')
    state_root.mkdir(parents=True,exist_ok=True);legacy=state_root/(name+'.lock')
    if legacy.exists() or legacy.is_symlink():raise SetupError('A historical setup lock exists. Ask for diagnosis before retrying; do not create a duplicate repository.')
    guard=state_root/(name+'.guard')
    if guard.is_symlink():raise SetupError('Setup operation guard must not be a symlink.')
    fd=os.open(guard,os.O_RDWR|os.O_CREAT|getattr(os,'O_NOFOLLOW',0),0o600)
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
        except OSError as exc:raise SetupError('Another setup process holds this project lock. Close the duplicate launcher and retry.') from exc
        try:yield
        finally:
            stream.seek(0)
            if os.name=='nt':msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)

def setup(course,workspace,name,state_root=None,runner=command,no_launch=False,distribution=None,distribution_sha256=None,preview_bundle=None,distribution_lock=None,rehearsal_id=None,desktop=False,harness='claude'):
    if desktop and not preview_bundle:raise SetupError('Desktop handoff requires an explicit local candidate preview for Workforce, which starts with Essentials.')
    name=repo_name(name);workspace=safe_workspace(workspace)
    state_root=Path(state_root) if state_root else Path.home()/'.aibl'/'setup'
    with setup_lock(state_root,name):
        return _setup(course,workspace,name,state_root,runner,no_launch,distribution,distribution_sha256,preview_bundle,distribution_lock,rehearsal_id,desktop,harness)

def resume_clone(folder,temporary,full,default_branch,runner):
    if temporary.is_symlink():raise SetupError('Interrupted clone path is a symlink. Preserve it and choose a local folder.')
    if temporary.exists() and not any(temporary.iterdir()):
        runner(['gh','repo','clone',full,str(temporary)])
    elif temporary.exists():
        verify_existing(temporary,full,runner,require_head=False)
        try:runner(['git','rev-parse','--verify','HEAD'],cwd=temporary)
        except SetupError:
            if any(p.name!='.git' for p in temporary.iterdir()):raise SetupError('Incomplete clone contains files. They are preserved; ask Claude or the facilitator to review this folder before resuming.')
            if not isinstance(default_branch,str) or not default_branch or default_branch.startswith('-'):raise SetupError('GitHub default branch is unavailable. Retry when the repository finishes initializing.')
            runner(['git','check-ref-format','refs/heads/'+default_branch],cwd=temporary)
            runner(['git','fetch','origin'],cwd=temporary)
            runner(['git','checkout','--detach','refs/remotes/origin/'+default_branch],cwd=temporary)
            runner(['git','switch','-c',default_branch],cwd=temporary)
    else:runner(['gh','repo','clone',full,str(temporary)])
    verify_existing(temporary,full,runner)
    if folder.exists():raise SetupError('Destination appeared during cloning. Both folders are preserved; review before continuing.')
    temporary.rename(folder)

def starter_files(starter):
    """Every file under the installer's starter folder, plus a Codex copy of the Claude skills, as {relative posix path: bytes}."""
    root=ROOT/starter
    if not root.is_dir():raise SetupError('The installer is missing its workbench starter folder. Pull the installer again (git -C ~/GitHub/aibl-installer pull --ff-only) and rerun.')
    files={}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():raise SetupError('The workbench starter contains a symlink; the installer files are not trusted. Pull the installer again.')
        if not path.is_file() or '__pycache__' in path.parts:continue
        rel=path.relative_to(root).as_posix();files[rel]=path.read_bytes()
        # Codex registers skills from .agents/skills/, Claude from .claude/skills/. One source in the installer, both folders in the workbench.
        if rel.startswith('.claude/skills/'):files['.agents/skills/'+rel[len('.claude/skills/'):]]=files[rel]
    if not files:raise SetupError('The workbench starter folder is empty. Pull the installer again.')
    return files

def seed_starter(folder,temporary,full,files,user,runner):
    """Stage the starter in the installer's own folder, commit it as the single root of the student's history, push, then move it into place. Never rewrite a student's project."""
    folder=Path(folder);temporary=Path(temporary)
    if folder.exists():raise SetupError('Project destination is occupied. It is preserved; choose another name or review it first.')
    if temporary.is_symlink():raise SetupError('Interrupted setup path is a symlink. Preserve it and choose a local folder.')
    temporary.mkdir(parents=True,exist_ok=True)
    if (temporary/'.git').is_symlink() or ((temporary/'.git').exists() and not (temporary/'.git').is_dir()):raise SetupError('Staging Git metadata is linked or unexpected. It is preserved.')
    if not (temporary/'.git').exists():
        if any(temporary.iterdir()):raise SetupError('Interrupted setup contains unrecognized work. It is preserved; ask for a review before resuming.')
        runner(['git','init','--initial-branch=main'],cwd=temporary)
        runner(['git','remote','add','origin','https://github.com/'+full+'.git'],cwd=temporary)
    if not remote_matches(runner(['git','remote','get-url','origin'],cwd=temporary),full):raise SetupError('Staging origin differs from the private destination. It is preserved.')
    if Path(runner(['git','rev-parse','--show-toplevel'],cwd=temporary)).resolve()!=temporary.resolve():raise SetupError('Staging is not the project root. It is preserved.')
    for path in temporary.rglob('*'):
        rel=path.relative_to(temporary).as_posix()
        if rel=='.git' or rel.startswith('.git/'):continue
        if path.is_symlink() or not (path.is_dir() or path.is_file()):raise SetupError('Staging contains a linked or nonregular file; no files were changed.')
        if path.is_file() and (rel not in files or path.read_bytes()!=files[rel]):raise SetupError('Staging contains changed or unrecognized work; it is preserved.')
    for rel,data in files.items():
        path=temporary/rel;path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists():
            with path.open('xb') as stream:stream.write(data)
    runner(['git','config','--local','user.name',user.get('name') or user['login']],cwd=temporary)
    runner(['git','config','--local','user.email',str(user['id'])+'+'+user['login']+'@users.noreply.github.com'],cwd=temporary)
    try:head=runner(['git','rev-parse','--verify','HEAD'],cwd=temporary)
    except SetupError:head=''
    if not head:
        runner(['git','add','--force','--',*sorted(files)],cwd=temporary)
        runner(['git','commit','-m','Your workbench, day one'],cwd=temporary)
        head=runner(['git','rev-parse','HEAD'],cwd=temporary)
    if runner(['git','status','--porcelain'],cwd=temporary):raise SetupError('Staging has unfinished changes. Preserve it for review.')
    if runner(['git','rev-list','--count','HEAD'],cwd=temporary)!='1':raise SetupError('The workbench must begin as a single-root history. Staging is preserved for review.')
    remote=runner(['git','ls-remote','--heads','origin'],cwd=temporary)
    if remote:
        if remote.split()!=[head,'refs/heads/main']:raise SetupError('Private remote changed during setup. Both copies are preserved.')
    else:
        runner(['git','push','--set-upstream','origin','HEAD:refs/heads/main'],cwd=temporary)
        if runner(['git','ls-remote','--heads','origin'],cwd=temporary).split()!=[head,'refs/heads/main']:raise SetupError('Initial private push was not verified. Rerun the same setup.')
    if folder.exists():raise SetupError('Project destination appeared during setup. Preserve both folders.')
    temporary.rename(folder)

def _setup(course,workspace,name,state_root,runner,no_launch,distribution=None,distribution_sha256=None,preview_bundle=None,distribution_lock=None,rehearsal_id=None,desktop=False,harness='claude'):
    started=time.monotonic();workspace=safe_workspace(workspace);name=repo_name(name)
    state_root=Path(state_root) if state_root else Path.home()/'.aibl'/'setup'
    statefile=state_root/(name+'.json')
    if statefile.is_symlink():raise SetupError('Setup progress must not be a symlink.')
    try:state=json.loads(statefile.read_text(encoding='utf-8')) if statefile.exists() else {'schema_version':'aibl.setup-progress/v1','repository_name':name,'attempts':[]}
    except json.JSONDecodeError:raise SetupError('Setup progress is damaged. Preserve it and ask for recovery; existing repositories have not been changed.')
    if not isinstance(state,dict) or state.get('schema_version')!='aibl.setup-progress/v1' or state.get('repository_name')!=name or not isinstance(state.get('attempts'),list):raise SetupError('Setup progress has an unexpected identity or format. Preserve it for diagnosis.')
    if harness not in HARNESSES:raise SetupError('Unknown app. Use claude or codex.')
    if desktop and harness!='claude':raise SetupError('The desktop preview handoff is a Claude route.')
    client='claude_desktop' if desktop else HARNESSES[harness]['client']
    desktop_observations=dict.fromkeys(('desktop_authentication','desktop_session','native_runtime'),'NOT_OBSERVED') if desktop else {}
    attempt={'course':course['id'],'client':client,'harness':harness,'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'manual_interventions':0,'manual_interventions_scope':'observed browser logins only; course/name/OS consent measured separately','os_prompts':'unmeasured','steps':[],'result':'in_progress','stages':dict.fromkeys(STAGES,'NOT_RUN'),'last_proven_stage':None,'failed_stage':None,'failure_domain':None,'provenance':source_provenance(),**desktop_observations};state['attempts'].append(attempt);write(statefile,state)
    active_stage=None
    def enter(label):
        nonlocal active_stage
        active_stage=label;attempt['stages'][label]='IN_PROGRESS';write(statefile,state)
    def step(label):
        attempt['steps'].append(label)
        if label in STEP_STAGE:
            proven=STEP_STAGE[label];attempt['stages'][proven]='PASS';attempt['last_proven_stage']=proven
        write(statefile,state)
    try:
        saved_client=state.get('client','claude_code')
        if saved_client not in ('claude_code','claude_desktop','codex_cli'):raise SetupError('Saved setup client is invalid. Preserve this project for diagnosis.')
        if saved_client!=client and (state.get('client') or state.get('repository') or state.get('distribution_sha256')):
            raise SetupError('This saved setup uses another client. Use a fresh project name to change clients; its original route is preserved.')
        if rehearsal_id and (not preview_bundle or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}',rehearsal_id)):
            raise SetupError('Automated rehearsal needs a local candidate bundle and a portable rehearsal ID.')
        if preview_bundle and (not distribution or not distribution_lock):raise SetupError('Local candidate setup requires the independent frozen distribution lock and digest.')
        if state.get('local_candidate') and not preview_bundle:raise SetupError('This project uses a local candidate. Resume with its explicit bundle; no release download fallback is allowed.')
        if preview_bundle and not state.get('local_candidate') and (state.get('repository') or state.get('distribution_sha256')):
            raise SetupError('This saved setup uses the published course route. Use a fresh project name for a local candidate; its original setup and resume route are preserved.')
        if state.get('rehearsal_id')!=rehearsal_id and (state.get('rehearsal_id') or (rehearsal_id and state.get('repository'))):raise SetupError('Saved project rehearsal identity differs; preserve this project and choose the matching rehearsal.')
        state['client']=client;write(statefile,state)
        if preview_bundle:
            enter('candidate_inputs')
            from pinned_distribution import preview_bundle as verify_preview,local_input,digest
            lock_path=local_input(distribution_lock)
            if lock_path.stat().st_size>65536:raise SetupError('Candidate distribution lock is oversized.')
            lock_bytes=lock_path.read_bytes()
            if digest(lock_bytes)!=distribution_sha256 or json.loads(lock_bytes)!=distribution:raise SetupError('Candidate distribution lock differs from its independently supplied digest or selected source.')
            verify_preview(preview_bundle,distribution)
            state['local_candidate']=True;state['rehearsal_id']=rehearsal_id
            attempt['provenance']['delivery_mode']='local_candidate'
            if rehearsal_id:attempt.update({'actor':'automated_test','rehearsal_id':rehearsal_id,'course_credit':False})
            step('candidate_inputs_verified')
        if state.get('distribution_sha256') and not distribution:raise SetupError('This project uses a frozen distribution. Resume with its reviewed pinned launcher; earlier work is preserved.')
        if distribution:
            from pinned_distribution import validate_lock
            validate_lock(distribution)
            if course['id']!=distribution['course_id'] or not re.fullmatch('[a-f0-9]{64}',distribution_sha256 or ''):raise SetupError('Pinned distribution does not match this course.')
            if state.get('distribution_sha256') and state['distribution_sha256']!=distribution_sha256:raise SetupError('This project began with a different frozen distribution. Use its supported update path; earlier work is preserved.')
            if not state.get('distribution_sha256') and state.get('repository'):raise SetupError('This saved setup began without a frozen distribution. Choose a new project name; earlier work is preserved.')
            state['distribution_sha256']=distribution_sha256
            attempt['provenance']['distribution_sha256']=distribution_sha256
            attempt['provenance']['source_release_pins']=distribution['source_release_pins']
            write(statefile,state)
        enter('tools')
        versions=check_tools(runner,desktop,harness);attempt['versions']=versions;step('tools_verified')
        enter('github_auth')
        # Qualify the selected account, not every saved account. An inactive
        # account can make `gh auth status` fail while the selected API works.
        try:user=json.loads(runner(['gh','api','user']))
        except SetupError as exc:
            if exc.reason!='authentication_missing':raise
            if rehearsal_id:raise SetupError('Automated rehearsal requires the existing GitHub sign-in; no account enrollment or login is automated.','authentication_missing')
            print('Sign in to GitHub in the browser. Do not paste account codes into Claude chat.');attempt['manual_interventions']+=1;runner(['gh','auth','login','--hostname','github.com','--git-protocol','https','--web'],interactive=True)
            user=json.loads(runner(['gh','api','user']))
        full=user['login']+'/'+name
        if state.get('repository') and state['repository']!=full:raise SetupError('This saved setup belongs to another GitHub account. Sign into that account or choose a new repository name.')
        if state.get('workspace') and state['workspace']!=str(workspace):raise SetupError('This setup already has a local folder. Resume there or choose a new name; duplicate clones are not created.')
        state['repository']=full;state['workspace']=str(workspace);step('github_verified')
        if not preview_bundle:enter('course_access')
        for upstream in ([] if preview_bundle else course['access']):
            try:meta=json.loads(runner(['gh','api','repos/'+upstream]))
            except SetupError as exc:
                if exc.reason!='not_found':raise
                raise SetupError(f'Your GitHub account cannot read {upstream}. Accept the course invitation in GitHub, or ask the course team to check access for your signed-in account. Rerun this same launcher afterward.','missing_access')
            if not meta.get('private'):raise SetupError('Course destination privacy changed. Ask the course team to review before continuing.')
        attempt['included_access']={}
        for included in ([] if preview_bundle else course.get('included',[])):
            # Bundled programs (a Workforce purchase includes the Lab) may be granted a little later than the purchase. Report, never block.
            try:runner(['gh','api','repos/'+included['publisher']]);attempt['included_access'][included['id']]='found'
            except SetupError as exc:
                if exc.reason!='not_found':raise
                attempt['included_access'][included['id']]='not yet';print(included['label'].split(' (')[0]+': not yet. Your invitation may still be on its way; it lands in your workbench later through the update path.')
        write(statefile,state)
        if not preview_bundle:step('course_access_verified')
        enter('private_repository')
        folder=workspace/name
        if folder.exists():verify_existing(folder,full,runner)
        # A specific 404 is absence; network/auth failures never trigger creation.
        try:existing=json.loads(runner(['gh','api','repos/'+full]))
        except SetupError as exc:
            if exc.reason!='not_found':raise
            existing=None
        if distribution:
            from pinned_distribution import ensure_private_repository
            ensure_private_repository(full,existing,state,distribution_sha256,runner,lambda:write(statefile,state))
        elif existing:
            if not existing['private']:raise SetupError('That name belongs to a public repository. Choose a new private workbench name; privacy is not changed automatically.')
            meta=existing;template=(meta.get('template_repository') or {}).get('full_name')
            if course.get('template'):
                if template!=course['template'] and state.get('created_repository_id')!=meta.get('id'):raise SetupError('Repository name collision. This existing repository is not the selected template; choose a different name.')
            # Starter route: resume our own creation, or adopt an empty repository the student made by hand. Anything with history is someone's work.
            elif state.get('created_repository_id')!=meta.get('id') and meta.get('size',0)!=0:raise SetupError('Repository name collision. That repository already has work in it; choose a different name.')
        else:
            state['creation_intent']={'repository':full,'template':course.get('template')};step('repository_creation_planned')
            runner(['gh','repo','create',full,'--private',*(['--template',course['template']] if course.get('template') else [])])
        meta=json.loads(runner(['gh','api','repos/'+full]))
        if not meta.get('private') or meta.get('full_name','').lower()!=full.lower():raise SetupError('Private repository verification failed.')
        state['created_repository_id']=meta.get('id');step('private_repository_verified')
        enter('clone')
        if not folder.exists():
            workspace.mkdir(parents=True,exist_ok=True)
            temp=workspace/('.'+name+'-clone-in-progress')
            if distribution:
                from pinned_distribution import download_bundle,seed_project,preview_bundle as verify_preview
                if preview_bundle:
                    manifest,payload=verify_preview(preview_bundle,distribution)['agent-essentials']
                    seed_project(folder,temp,full,manifest,payload,distribution,distribution_sha256,user,runner,local_candidate=True)
                else:
                    with tempfile.TemporaryDirectory(prefix='aibl-pinned-release-') as bundle:
                        manifest,payload=download_bundle(distribution,bundle,runner)
                        seed_project(folder,temp,full,manifest,payload,distribution,distribution_sha256,user,runner)
            elif course.get('template'):resume_clone(folder,temp,full,meta.get('default_branch'),runner)
            else:seed_starter(folder,temp,full,starter_files(course['starter']),user,runner)
        verify_existing(folder,full,runner)
        if distribution:
            from pinned_distribution import verify_installed_helper
            verify_installed_helper(folder,distribution,distribution_sha256)
            if preview_bundle:
                from pinned_distribution import record_candidate_transport
                record_candidate_transport(folder,preview_bundle,distribution_lock,distribution,distribution_sha256,rehearsal_id)
        attempt['provenance']['student_observed_commit']=runner(['git','rev-parse','HEAD'],cwd=folder)
        attempt['provenance']['student_observed_tree']=runner(['git','rev-parse','HEAD^{tree}'],cwd=folder)
        step('clone_verified')
        enter('git_identity')
        for key,value in [('user.name',user.get('name') or user['login']),('user.email',str(user['id'])+'+'+user['login']+'@users.noreply.github.com')]:
            try:current=runner(['git','config','--local','--get',key],cwd=folder)
            except SetupError:current=''
            if not current:runner(['git','config','--local',key,value],cwd=folder)
        step('local_git_identity_verified')
        enter('student_context')
        if (folder/'scripts/aibl.py').is_file():runner([sys.executable,'scripts/aibl.py','setup','--json'],cwd=folder)
        else:
            for sub in ('context','library','blueprints'):
                if (folder/sub).is_symlink():raise SetupError('Workbench folders must not be symlinks. Preserve the project for diagnosis.')
                (folder/sub).mkdir(exist_ok=True)
        step('student_context_ready')
        onboarding=folder/'.aibl-local/onboarding.json'
        if onboarding.parent.is_symlink() or onboarding.is_symlink():raise SetupError('Private onboarding state must not be a symlink.')
        if not onboarding.exists():write(onboarding,{'started_at':state['attempts'][0]['started_at'],'course':course['id'],'harness':harness,'first_artifact':None,'measurement_scope':('Python setup only; Desktop authentication, session and exercise not observed' if desktop else 'Python setup and Claude exercise; OS bootstrap prompts and duration not captured')})
        start_skill=course.get('start_skill') or 'aibl-what-do-i-have'
        start_request='/aibl-teach' if distribution else '/'+start_skill
        if distribution:prompt='Use /aibl-teach in this workbench. Read the installed mission map and saved learning state; resume the pending checkpoint, or begin ANW-M0-01 if no learning record exists. Preserve prior attempts and ask for my actual choices and explanations.'
        elif start_skill=='aibl-what-do-i-have':prompt='Use /aibl-what-do-i-have. Tell me what is in this workbench and what it can do, in plain words, then the one thing I should check before I close this session.'
        else:prompt='Use /'+start_skill+'. Continue my Essentials prerequisite and help me make the first useful artifact. This setup selected '+course['label']+'.'
        if harness=='codex':prompt=prompt.replace('Use /aibl-teach in this workbench.','Read .claude/skills/aibl-teach/SKILL.md in this workbench and follow it.').replace('Use /'+start_skill+'.','Use the '+start_skill+' skill.')
        if rehearsal_id:prompt=('This is isolated automated_test rehearsal '+rehearsal_id+'. Use /aibl-teach and the real installed missions. Every learning helper call must include --rehearsal '+rehearsal_id+' --actor automated_test. Record explicit automated test responses, never human answers, approval, assessment or credit. Resume the pending test checkpoint, or begin ANW-M0-01. Use the verified local candidate transport for adoption after the rehearsal prerequisites; never download a release or use a channel fallback.')
        if desktop:
            attempt['result']='files_ready_for_desktop';attempt['elapsed_seconds']=round(time.monotonic()-started,2);write(statefile,state)
            result={'status':'files_ready_for_desktop','client':client,'course':course['id'],'repository':full,'workspace':str(folder),'versions':versions,'manual_interventions':attempt['manual_interventions'],'elapsed_seconds':attempt['elapsed_seconds'],'first_useful_artifact':'pending Desktop exercise; no timing promise','next':start_request,'handoff_prompt':prompt+(' This rehearsal has course_credit=false.' if rehearsal_id else ''),'delivery_mode':'local_candidate','student_observed_commit':attempt['provenance']['student_observed_commit'],'student_observed_tree':attempt['provenance']['student_observed_tree'],'last_proven_stage':attempt['last_proven_stage'],'stages':dict(attempt['stages']),**desktop_observations}
            if rehearsal_id:result.update({'rehearsal_id':rehearsal_id,'actor':'automated_test','course_credit':False})
            print(json.dumps(result,indent=2));return result
        enter('claude_auth')
        # Do not persist auth payloads. Browser consent stays visible and is rechecked each run.
        h=HARNESSES[harness]
        def signed_in():
            out=runner(h['status'])
            if harness=='claude':return bool(json.loads(out).get('loggedIn'))
            return 'logged in' in out.lower() or 'signed in' in out.lower()
        try:
            if not signed_in():raise SetupError(h['label']+' login required')
        except (SetupError,json.JSONDecodeError):
            if rehearsal_id:raise SetupError('Automated rehearsal requires existing supported '+h['label']+' access; no login is automated.')
            print('Sign into your '+h['label']+' account in the browser.');attempt['manual_interventions']+=1;runner(h['login'],interactive=True)
            if not signed_in():raise SetupError(h['label']+' sign-in is not complete. Finish browser consent and rerun.')
        step('claude_authenticated');attempt['result']='ready';attempt['elapsed_seconds']=round(time.monotonic()-started,2);write(statefile,state)
        result={'status':'ready','course':course['id'],'repository':full,'workspace':str(folder),'versions':versions,'manual_interventions':attempt['manual_interventions'],'elapsed_seconds':attempt['elapsed_seconds'],'first_useful_artifact':'pending Claude exercise; no timing promise','next':start_request,'included_access':attempt.get('included_access',{}),'harness':harness}
        if preview_bundle:result['delivery_mode']='local_candidate'
        if rehearsal_id:result.update({'rehearsal_id':rehearsal_id,'actor':'automated_test','course_credit':False})
        print(json.dumps(result,indent=2))
        if not no_launch:
            enter('claude_launch');runner([HARNESSES[harness]['cli'],prompt],cwd=folder,interactive=True);step('claude_session_returned')
        return result
    except (OSError,ValueError) as e:
        attempt['result']='blocked';attempt['failed_stage']=active_stage;attempt['failure_domain']=getattr(e,'reason','local_state');attempt['recovery']=str(e);attempt['elapsed_seconds']=round(time.monotonic()-started,2)
        if active_stage:attempt['stages'][active_stage]='FAIL'
        write(statefile,state);raise

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--course');p.add_argument('--workspace',default=str(Path.home()/'GitHub'));p.add_argument('--repo-name');p.add_argument('--plan',action='store_true');p.add_argument('--no-launch',action='store_true');p.add_argument('--distribution-lock');p.add_argument('--distribution-sha256');p.add_argument('--preview-bundle');p.add_argument('--rehearsal-id');p.add_argument('--desktop',action='store_true',help='Prepare a local preview for a separate Claude Desktop session; authentication and runtime remain unobserved.');p.add_argument('--harness',choices=list(HARNESSES),help='The app the student works in: claude or codex. Asked when absent.');a=p.parse_args()
    try:
        if a.desktop and not a.preview_bundle:raise SetupError('Desktop handoff requires an explicit local candidate preview for Workforce, which starts with Essentials.')
        distribution=None;distribution_sha256=None
        if a.distribution_lock or a.distribution_sha256:
            if not a.distribution_lock or not a.distribution_sha256:raise SetupError('Pinned setup needs both the reviewed lock and its separate digest.')
            from pinned_distribution import load_lock
            distribution,distribution_sha256=load_lock(a.distribution_lock,a.distribution_sha256,ROOT,command,os.environ.get('AIBL_BOOTSTRAP_PATH'))
        if a.preview_bundle:
            if not distribution:raise SetupError('Local candidate setup requires the reviewed distribution lock and independent digest.')
            from pinned_distribution import preview_bundle
            preview_bundle(a.preview_bundle,distribution)
        if a.rehearsal_id and not a.preview_bundle:raise SetupError('Rehearsal setup requires an explicit local candidate bundle.')
        course=choose(a.course or (distribution['course_id'] if distribution else None))
        if a.plan:print(json.dumps({'course':course,'workspace':str(safe_workspace(a.workspace)),'effects':'none','platform':platform.system()},indent=2));return 0
        harness='claude' if a.desktop else choose_harness(a.harness)
        name=a.repo_name or input('Private project name [my-workbench]: ').strip() or 'my-workbench'
        setup(course,a.workspace,name,no_launch=a.no_launch,distribution=distribution,distribution_sha256=distribution_sha256,preview_bundle=a.preview_bundle,distribution_lock=a.distribution_lock,rehearsal_id=a.rehearsal_id,desktop=a.desktop,harness=harness);return 0
    except (OSError,ValueError) as e:print('Setup paused: '+str(e));return 1
if __name__=='__main__':sys.exit(main())
