#!/usr/bin/env python3
"""Connect the programs a student is already enrolled in to their workbench. Standard library only.

The installer builds the hub and never asks which program a student is in. This
command runs inside the workbench later: it reads the program registry, asks
GitHub which program repositories this account can read, shows the list, and on
confirmation records the decision and names the adoption step for each program.
Adoption itself stays with each program's own skill (the registry's adopt_skill),
which verifies the reviewed release pin; this file never touches release pins.

Re-runnable. A program already in the workbench reports its release and is left
alone. A program joined later is the same command again.
"""
from __future__ import annotations
import argparse,datetime,json,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from course_setup import ROOT,SetupError,command,registry,source_provenance,write

def find_workbench(explicit=None):
    # Explicit path, else the current folder, else the installer's default. A workbench is a folder with .aibl/ in it.
    candidates=[Path(explicit)] if explicit else [Path.cwd(),Path.home()/'GitHub'/'my-workbench']
    for c in candidates:
        if c.is_symlink() or (c/'.aibl').is_symlink():raise SetupError('Workbench or state directory is linked; preserve it for review.','local_state')
        if (c/'.aibl').is_dir():return c.resolve()
    where=explicit or 'this folder or ~/GitHub/my-workbench'
    raise SetupError(f'No workbench found at {where}. Open your workbench (the folder the installer created) and run this again, or pass --workbench.','local_state')

def verify_engine(workbench,runner=command):
    """Read only. A pinned workbench must use its independently accepted installer."""
    family=Path(workbench)/'.aibl'/'family.json'
    if family.is_symlink():raise SetupError('Family record is linked; preserve it for review.','local_state')
    if family.exists():
        value=json.loads(family.read_text());commit=value.get('family',{}).get('installer_revision')
        if not isinstance(commit,str) or not re.fullmatch('[a-f0-9]{40}',commit):raise SetupError('Family installer identity is damaged.','local_state')
        if runner(['git','rev-parse','HEAD'],cwd=ROOT)!=commit or runner(['git','status','--porcelain'],cwd=ROOT):raise SetupError('Use the unchanged family installer; explicit family update is separate.','local_state')
        return {'refreshed':False,'mode':'family','installer_commit':commit}
    record=Path(workbench)/'.aibl'/'distribution.json'
    if record.is_symlink():raise SetupError('Distribution record is linked; preserve it for review.','local_state')
    if not record.exists():return {'refreshed':False,'mode':'unpinned'}
    value=json.loads(record.read_text(encoding='utf-8'))
    commit=value.get('installer_commit')
    if not isinstance(commit,str) or not re.fullmatch(r'[a-f0-9]{40}',commit):raise SetupError('Distribution installer identity is damaged.','local_state')
    if runner(['git','rev-parse','HEAD'],cwd=ROOT)!=commit or runner(['git','status','--porcelain'],cwd=ROOT):
        raise SetupError('Use the unchanged installer from this workbench distribution. Enrollment does not upgrade a distribution.','local_state')
    return {'refreshed':False,'mode':'frozen','installer_commit':commit}

def programs(reg):return [p for p in reg['programs'] if p.get('kind')!='foundation']

def access(publisher,runner=command):
    # A 404 only establishes unavailable repository access, not invitation state.
    try:runner(['gh','api','repos/'+publisher]);return 'readable'
    except SetupError as exc:
        if exc.reason=='not_found':return 'unavailable'
        if exc.reason=='authentication_missing':raise SetupError('GitHub is not signed in on this machine. The installer signed you in once; run gh auth login --web and try again.','authentication_missing')
        raise

def installed(workbench,release_product):
    state=Path(workbench)/'.aibl'/('installed-'+release_product+'.json')
    if state.is_symlink():raise SetupError('Installed record is linked; preserve it for diagnosis.','local_state')
    if not state.exists():return None
    try:
        value=json.loads(state.read_text(encoding='utf-8'))
        release=value.get('release_id') if isinstance(value,dict) else None
        if not isinstance(release,str) or not re.fullmatch(re.escape(release_product)+r'-v\d+\.\d+\.\d+(?:-[a-z0-9]+(?:[.-][a-z0-9]+)*)?',release):raise ValueError('invalid release id')
        return release
    except (ValueError,OSError) as exc:raise SetupError('Installed record for '+release_product+' is unreadable or invalid; preserve it for diagnosis.','local_state') from exc

def plan(workbench,reg=None,runner=command):
    reg=reg or registry();rows=[]
    family=Path(workbench)/'.aibl'/'family.json'
    if family.is_symlink():raise SetupError('Family record is linked.','local_state')
    installed_family=json.loads(family.read_text()) if family.exists() else None
    if installed_family:
        reg=json.loads(json.dumps(reg))
        for program in reg['programs']:
            if program['id']=='agent-workforce':
                program.update(publisher='aibuild-lab/agent-workforce',release_product='agent-workforce',adopt_skill=None)

    for p in programs(reg):
        row={'id':p['id'],'label':p['label'].split(' (')[0],'publisher':p['publisher'],'release_product':p['release_product'],'adopt_skill':p.get('adopt_skill'),'access':access(p['publisher'],runner),'installed':installed(workbench,p['release_product']),'included_by':None}
        if installed_family and p['id']=='agent-workforce':
            pin=installed_family.get('packages',{}).get('agent-workforce')
            row['installed']=('agent-workforce-v'+pin['version']) if pin else None
            row['family_adoption']=True
        rows.append(row)
    # Inclusion is catalog information. Repository readability never proves a pending invitation.
    for p in programs(reg):
        for inc in p.get('includes',[]):
            holder=next(r for r in rows if r['id']==p['id']);target=next((r for r in rows if r['id']==inc),None)
            if target and holder['access']=='readable':target['included_by']=holder['label']
    for r in rows:r['next']=next_step(r)
    return rows

def next_step(r):
    if r['installed']:return 'installed release recorded ('+r['installed']+')'
    if r.get('family_adoption') and r['access']=='readable':return 'use scripts/workbench_packages.py apply with the reviewed family lock, digest, bundles and --product agent-workforce; see FAMILY-DELIVERY.md'
    if r['access']=='readable':return ('run '+r['adopt_skill']) if r['adopt_skill'] else 'no verified adoption route yet; ask the course team for supported delivery'
    return 'repository unavailable; check the signed-in account and access with the course team (invitation status unknown)'

def enrollable(rows):return [r for r in rows if r['access']=='readable' and not r['installed']]

def show(rows):
    print('Programs this GitHub account can read:')
    for r in rows:print(f"  {r['label']}: {r['access']}"+(f" (included with {r['included_by']})" if r['included_by'] else '')+f" -> {r['next']}")

def record(workbench,rows,chosen,refresh):
    path=Path(workbench)/'.aibl'/'enroll.json'
    if path.is_symlink():raise SetupError('Enrollment record is linked; preserve it for review.','local_state')
    value={'schema_version':'aibl.enroll/v1','checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'programs':rows,'chosen':[r['id'] for r in chosen],'installer':{**source_provenance(),**refresh}}
    if path.exists():
        previous=json.loads(path.read_text())
        if previous.get('schema_version')!='aibl.enroll/v1' or not isinstance(previous.get('chosen'),list):raise SetupError('Invalid prior enrollment; preserve for review.','local_state')
        value['chosen']=list(dict.fromkeys(previous['chosen']+value['chosen']))
    write(path,value);return path

def enroll(workbench=None,yes=False,check=False,only=None,runner=None,ask=input,reg=None):
    runner=runner or command  # resolved at call time so a test can replace the module's command
    workbench=find_workbench(workbench);refresh=verify_engine(workbench,runner);rows=plan(workbench,reg,runner)
    if only:
        unknown=[o for o in only if o not in {r['id'] for r in rows}]
        if unknown:raise SetupError('Unknown program: '+', '.join(unknown)+'. Use a listed program id.')
    candidates=[r for r in enrollable(rows) if not only or r['id'] in only]
    result={'status':'checked','workbench':str(workbench),'installer':refresh,'programs':rows,'chosen':[]}
    if check:return result
    if not candidates:result['status']='nothing to select';record(workbench,rows,[],refresh);return result
    if not yes:
        # Never silent: an admin or a two-program student can read more than they want dropped in.
        answer=ask('Select next adoption steps for '+', '.join(r['label'] for r in candidates)+'? [Y/n] ').strip().lower()
        if answer not in ('','y','yes'):result['status']='declined';return result
    result['status']='selected';result['chosen']=[r['id'] for r in candidates];result['next']=[{'id':r['id'],'do':r['next']} for r in candidates];result['record']=str(record(workbench,rows,candidates,refresh))
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter);p.add_argument('--workbench',help='The workbench folder. Default: this folder, then ~/GitHub/my-workbench.');p.add_argument('--check',action='store_true',help='Show what this account can read and change nothing.');p.add_argument('--yes',action='store_true',help='Skip the confirmation (for a coordinating session that already asked).');p.add_argument('--program',action='append',help='Select only this program id; repeatable.');p.add_argument('--json',action='store_true');a=p.parse_args()
    try:
        result=enroll(a.workbench,a.yes,a.check,a.program)
        if a.json:print(json.dumps(result,indent=2))
        else:
            show(result['programs'])
            if result['status']=='selected':
                print('Recorded. Next, in this order:')
                for n in result['next']:print(f"  {n['id']}: {n['do']}")
            elif result['status']=='nothing to select':print('Nothing new to select. No new readable program without an installed record.')
            elif result['status']=='declined':print('Nothing changed. Run this again whenever you want.')
        return 0
    except (OSError,ValueError) as e:print('Enroll paused: '+str(e));return 1
if __name__=='__main__':sys.exit(main())
