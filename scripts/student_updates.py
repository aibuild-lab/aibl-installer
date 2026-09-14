"""Student-controlled grouped updates, isolated from active agent discovery.

No automatic checkpoint, stash, reset, force push, polling or faculty approval.
Every external write is reconciled by identity before another attempt.
"""
from __future__ import annotations
import argparse
import json
import re
import subprocess
from pathlib import Path
import workbench_packages as packages
from release_files import ReleaseError, atomic, digest, encoded, process_guard, under


def git(root,*args):
    result=subprocess.run(['git',*args],cwd=root,text=True,capture_output=True)
    if result.returncode:raise ReleaseError('Git '+args[0]+' paused; preserve local work and inspect divergence or conflicts. '+result.stderr.strip())
    return result.stdout.strip()


class GitHub:
    def api(self,route,body=None):
        command=['gh','api','--hostname','github.com',route]
        if body is not None:command+=['--input','-']
        raw=subprocess.check_output(command,input=encoded(body) if body is not None else None)
        return json.loads(raw)

    def owner(self,repository):
        user=self.api('user');repo=self.api('repos/'+repository)
        if repo.get('private') is not True or repo.get('full_name')!=repository or repo.get('owner',{}).get('login')!=user.get('login'):
            raise ReleaseError('Use the signed-in student own private repository')
        return repo['default_branch']

    def lookup(self,repository,branch,base):
        # Branch/base are locally generated or checked Git ref names.
        from urllib.parse import urlencode
        rows=self.api('repos/'+repository+'/pulls?'+urlencode({'state':'all','head':repository.split('/')[0]+':'+branch,'base':base,'per_page':100}))
        if len(rows)>1:raise ReleaseError('Multiple update PRs match; preserve operation for review')
        return rows[0] if rows else None

    def create(self,repository,branch,base,operation):
        return self.api('repos/'+repository+'/pulls',{'head':branch,'base':base,'title':'My Workbench update '+operation,'body':'One reviewed package combination. Student approval is required before merge. Local synchronization and native verification are separate.'})

    def read(self,repository,number):return self.api(f'repos/{repository}/pulls/{number}')

    def merge(self,repository,number,head):
        raw=subprocess.check_output(['gh','api','--hostname','github.com',f'repos/{repository}/pulls/{number}/merge','-X','PUT','--input','-'],input=encoded({'sha':head,'merge_method':'merge'}))
        result=json.loads(raw)
        if not result.get('merged'):raise ReleaseError('Provider did not confirm merge')
        return result


def repository(root):
    remote=git(root,'remote','get-url','origin')
    match=re.fullmatch(r'(?:https://github.com/|git@github.com:)([A-Za-z0-9-]+/[A-Za-z0-9_.-]+?)(?:\.git)?',remote)
    if not match:raise ReleaseError('Update requires the verified GitHub origin')
    return match[1]


def state_path(root,operation):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}',operation):raise ReleaseError('Portable explicit operation ID required')
    return under(root,'.aibl-local/updates/'+operation+'.json')


def save(path,state):atomic(path,encoded(state),0o600)


def read_state(root,operation):
    state=json.loads(state_path(root,operation).read_text())
    if state.get('schema_version')!='aibl.student-update/v1' or state.get('operation')!=operation or state.get('workbench')!=str(Path(root).resolve()):raise ReleaseError('Update operation identity differs')
    return state


def managed_snapshot(root):
    record=packages.read(under(root,packages.MARKER))
    return {name:packages.snapshot(root,name) for name in sorted({name for name,row in record['files'].items() if row['policy']=='supplied'}|{packages.MARKER})}


def transition_snapshot(root,names):return {name:packages.snapshot(root,name) for name in sorted(names)}


def fence_origin(root,state):
    if repository(root)!=state['repository']:raise ReleaseError('Repository origin changed; no external update write is allowed')


def fence_candidate(state):
    candidate=Path(state['candidate'])
    if git(candidate,'rev-parse','HEAD^')!=state['base_revision'] or git(candidate,'rev-parse','HEAD^{tree}')!=state['prepared_tree']:
        raise ReleaseError('Preparation commit differs from the reviewed tree or base; no push allowed')
    if state.get('head_revision') and git(candidate,'rev-parse','HEAD')!=state['head_revision']:raise ReleaseError('Preparation head changed; no push allowed')


def prepare(root,bundles,family,operation,preparation_root=None,backend=None):
    root=Path(root).resolve();backend=backend or GitHub();packages.validate_family(family)
    if family['schema_version']!='aibl.family-lock/v2':raise ReleaseError('Use the successor family distribution for student update PRs')
    path=state_path(root,operation);path.parent.mkdir(parents=True,exist_ok=True)
    with process_guard(path.parent/'operation.lock'):
        full=repository(root);base=backend.owner(full)
        git(root,'check-ref-format','refs/heads/'+base)
        installed=packages.read(under(root,packages.MARKER));products=sorted(installed['packages'])
        if not set(products)<=set(family['packages']):raise ReleaseError('New distribution omits an installed package')
        identity=digest(encoded(family))
        if path.exists():
            state=read_state(root,operation)
            if state['family_sha256']!=identity or state['repository']!=full:raise ReleaseError('Operation already belongs to another exact distribution')
            if state['stage'] not in ('preparing','prepared_files'):return state
        else:
            git(root,'fetch','origin',base)
            base_sha=git(root,'rev-parse','refs/remotes/origin/'+base)
            preview=packages.compose(root,bundles,family,products,preview=True)
            if preview['conflicts']:raise ReleaseError('Customized supplied files require review before preparing an update')
            directory=(Path(preparation_root) if preparation_root else Path.home()/'.aibl/update-preparations').resolve()
            if directory==root or directory.is_relative_to(root):raise ReleaseError('Prepare outside the active workbench and agent discovery')
            directory.mkdir(parents=True,exist_ok=True)
            candidate=directory/(digest(str(root).encode())[:12]+'-'+operation)
            if candidate.exists():raise ReleaseError('Unowned preparation path exists; preserve it')
            state={'schema_version':'aibl.student-update/v1','operation':operation,'workbench':str(root),'repository':full,'base_branch':base,'base_revision':base_sha,'local_revision':git(root,'rev-parse','HEAD'),'local_branch':git(root,'symbolic-ref','--short','HEAD'),'family':family,'family_sha256':identity,'products':products,'candidate':str(candidate),'branch':'aibl-update/'+operation,'stage':'preparing','managed_before':managed_snapshot(root),'pr':None,'approval':None,'native_verification':'pending'}
            state['transition_before']=transition_snapshot(root,set(state['managed_before'])|{row['path'] for row in preview['changes']})
            save(path,state)
        candidate=Path(state['candidate'])
        if not candidate.exists():git(root,'worktree','add','--detach',str(candidate),state['base_revision'])
        if git(candidate,'rev-parse','--show-toplevel')!=str(candidate):raise ReleaseError('Preparation ownership differs')
        candidate_head=git(candidate,'rev-parse','HEAD')
        if state['stage']=='prepared_files':
            if candidate_head==state['base_revision']:
                if git(candidate,'write-tree')!=state['prepared_tree']:raise ReleaseError('Prepared index changed; preserve for review')
                git(candidate,'commit','-m','My Workbench update '+operation)
                candidate_head=git(candidate,'rev-parse','HEAD')
            if git(candidate,'rev-parse','HEAD^')!=state['base_revision'] or git(candidate,'rev-parse','HEAD^{tree}')!=state['prepared_tree']:
                raise ReleaseError('Interrupted preparation commit differs from the reviewed tree')
            state.update(stage='prepared',head_revision=candidate_head);save(path,state);return state
        if candidate_head!=state['base_revision']:raise ReleaseError('Interrupted preparation has another commit; inspect before continuing')
        if under(candidate,'.aibl-local/family-transaction.json').exists():packages.recover(candidate)
        # The remote base must describe the same currently installed packages.
        prior=packages.read(under(candidate,packages.MARKER))
        completed_apply=state.get('intended_changes') is not None and prior['packages']=={p:family['packages'][p] for p in products}
        if prior['packages']!=installed['packages'] and not completed_apply:raise ReleaseError('Local and remote installed records differ; synchronize their history first')
        preview=packages.compose(candidate,bundles,family,products,preview=True)
        if preview['conflicts']:raise ReleaseError('Remote supplied files need review; no PR created')
        state['changes']=preview['changes']
        # Persist the intended diff before applying, so interrupted application
        # can restore its transaction and resume without losing removed paths.
        if not state.get('intended_changes'):state['intended_changes']=preview['changes'];save(path,state)
        packages.compose(candidate,bundles,family,products)
        git(candidate,'add','--',packages.MARKER,*[row['path'] for row in state['intended_changes']])
        staged=set(git(candidate,'diff','--cached','--name-only','-z').split('\0'))-{''}
        intended={packages.MARKER}|{row['path'] for row in state['intended_changes']}
        if staged-intended:raise ReleaseError('Preparation index contains unreviewed files; no commit or PR created')
        if not git(candidate,'diff','--cached','--name-only'):raise ReleaseError('No package change to propose')
        state.update(stage='prepared_files',prepared_tree=git(candidate,'write-tree'),changes=state['intended_changes'])
        state['managed_after']=managed_snapshot(candidate)
        state['transition_after']=transition_snapshot(candidate,state['transition_before'])
        state['history']=packages.read(under(candidate,'.aibl-local/family-history.json'))
        save(path,state)
        git(candidate,'commit','-m','My Workbench update '+operation)
        fence_candidate(state)
        state.update(stage='prepared',head_revision=git(candidate,'rev-parse','HEAD'))
        save(path,state);return state


def validate_pr(state,pr):
    if pr.get('head',{}).get('sha')!=state['head_revision'] or pr.get('head',{}).get('ref')!=state['branch'] or pr.get('base',{}).get('sha')!=state['base_revision'] or pr.get('base',{}).get('ref')!=state['base_branch'] or pr.get('base',{}).get('repo',{}).get('full_name')!=state['repository']:
        raise ReleaseError('PR identity changed; fresh student review required')


def propose(root,operation,backend=None):
    root=Path(root).resolve();backend=backend or GitHub();path=state_path(root,operation)
    with process_guard(path.parent/'operation.lock'):
        state=read_state(root,operation);fence_origin(root,state);backend.owner(state['repository'])
        if state['stage'] not in ('prepared','proposing','pr_open'):return state
        fence_candidate(state)
        state['stage']='proposing';save(path,state)
        target='refs/heads/'+state['branch']
        remote=git(root,'ls-remote','origin',target)
        if remote and remote.split()[0]!=state['head_revision']:raise ReleaseError('Update branch already has different work')
        if not remote:
            if repository(Path(state['candidate']))!=state['repository']:raise ReleaseError('Preparation origin changed; no push allowed')
            try:git(Path(state['candidate']),'push','origin',state['head_revision']+':'+target)
            except ReleaseError:
                remote=git(root,'ls-remote','origin',target)
                if not remote or remote.split()[0]!=state['head_revision']:raise
        pr=backend.lookup(state['repository'],state['branch'],state['base_branch'])
        if pr is None:
            try:pr=backend.create(state['repository'],state['branch'],state['base_branch'],operation)
            except Exception:
                pr=backend.lookup(state['repository'],state['branch'],state['base_branch'])
                if pr is None:raise ReleaseError('PR creation uncertain; resume this operation to reconcile')
        validate_pr(state,pr)
        if pr.get('state')=='closed' and not pr.get('merged_at'):raise ReleaseError('Student closed the PR; no replacement is created')
        state.update(pr=pr['number'],pr_url=pr['html_url'],stage='pr_open');save(path,state);return state


def approve_and_merge(root,operation,approved_head,backend=None):
    root=Path(root).resolve();backend=backend or GitHub();path=state_path(root,operation)
    with process_guard(path.parent/'operation.lock'):
        state=read_state(root,operation);fence_origin(root,state);backend.owner(state['repository'])
        if approved_head!=state.get('head_revision') or not state.get('pr'):raise ReleaseError('Explicit student approval of the exact PR head is required')
        pr=backend.read(state['repository'],state['pr']);validate_pr(state,pr)
        state.update(approval={'head_revision':approved_head,'actor':'student'},stage='merging');save(path,state)
        if not pr.get('merged_at'):
            if pr.get('state')!='open':raise ReleaseError('PR is not open')
            base_remote=git(root,'ls-remote','origin','refs/heads/'+state['base_branch'])
            if not base_remote or base_remote.split()[0]!=state['base_revision']:raise ReleaseError('Remote base changed; prepare and review the new combination before merge')
            try:backend.merge(state['repository'],state['pr'],approved_head)
            except Exception:pass
            pr=backend.read(state['repository'],state['pr']);validate_pr(state,pr)
        if not pr.get('merged_at') or not re.fullmatch('[0-9a-f]{40}',pr.get('merge_commit_sha') or ''):raise ReleaseError('Merge not confirmed; resume this same operation')
        state.update(stage='remote_merged',merge_revision=pr['merge_commit_sha']);save(path,state);return state


def synchronize(root,operation):
    root=Path(root).resolve();path=state_path(root,operation)
    with process_guard(path.parent/'operation.lock'):
        state=read_state(root,operation)
        if state['stage'] in ('local_synchronized','verified'):return state
        if state['stage']!='remote_merged':raise ReleaseError('Confirm the exact remote merge before synchronization')
        if repository(root)!=state['repository'] or git(root,'symbolic-ref','--short','HEAD')!=state['local_branch']:raise ReleaseError('Local repository or branch changed; preserve it and review')
        actual=transition_snapshot(root,state['transition_before'])
        if actual not in (state['transition_before'],state['transition_after']):raise ReleaseError('Local supplied files or incoming destinations changed; preserve them and review before synchronization')
        git(root,'fetch','origin',state['base_branch'])
        remote=git(root,'rev-parse','refs/remotes/origin/'+state['base_branch'])
        git(root,'merge-base','--is-ancestor',state['merge_revision'],remote)
        # A later remote update needs its own reviewed operation, not implicit pull.
        if remote!=state['merge_revision']:raise ReleaseError('Remote advanced beyond approved merge; review the new revision before synchronizing')
        parents=git(root,'show','-s','--format=%P',remote).split()
        if remote!=state['head_revision'] and parents!=[state['base_revision'],state['head_revision']]:raise ReleaseError('Provider merge graph differs from approved base and head')
        if git(root,'rev-parse',remote+'^{tree}')!=git(root,'rev-parse',state['head_revision']+'^{tree}'):raise ReleaseError('Provider merge content differs from the reviewed update')
        git(root,'merge','--ff-only','--no-overwrite-ignore',state['merge_revision'])
        if managed_snapshot(root)!=state['managed_after']:raise ReleaseError('Local package bytes differ after merge; preserve for recovery')
        history_path=under(root,'.aibl-local/family-history.json')
        history=packages.read(history_path) if history_path.exists() else {'packages':{},'components':{}}
        for kind in ('packages','components'):
            for key,value in state['history'][kind].items():
                if key in history[kind] and history[kind][key]!=value:raise ReleaseError('Local immutable history conflicts; preserve for review')
                history[kind][key]=value
        atomic(history_path,encoded(history),0o600)
        state.update(stage='local_synchronized',local_synchronized_revision=git(root,'rev-parse','HEAD'),native_verification='pending fresh selected-app session and first action')
        save(path,state);return state


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','propose','approve-and-merge','synchronize','status'])
    parser.add_argument('--workbench',required=True);parser.add_argument('--operation',required=True)
    parser.add_argument('--family-lock');parser.add_argument('--family-sha256');parser.add_argument('--family-bundles');parser.add_argument('--approved-head')
    args=parser.parse_args()
    try:
        if args.action=='prepare':
            if not all((args.family_lock,args.family_sha256,args.family_bundles)):raise ReleaseError('Independent approved distribution and bundles required')
            family=packages.load_lock(args.family_lock,args.family_sha256,Path(__file__).resolve().parents[1])
            result=prepare(args.workbench,args.family_bundles,family,args.operation)
        elif args.action=='propose':result=propose(args.workbench,args.operation)
        elif args.action=='approve-and-merge':result=approve_and_merge(args.workbench,args.operation,args.approved_head)
        elif args.action=='synchronize':result=synchronize(args.workbench,args.operation)
        else:result=read_state(args.workbench,args.operation)
        print(json.dumps({k:v for k,v in result.items() if k not in ('managed_before','managed_after','history','family')},indent=2));return 0
    except (OSError,ValueError,subprocess.CalledProcessError) as error:
        print('Update paused: '+str(error));return 1


if __name__=='__main__':raise SystemExit(main())
