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
import argparse,datetime,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from course_setup import ROOT,SetupError,command,registry,source_provenance,write

def find_workbench(explicit=None):
    # Explicit path, else the current folder, else the installer's default. A workbench is a folder with .aibl/ in it.
    candidates=[Path(explicit)] if explicit else [Path.cwd(),Path.home()/'GitHub'/'my-workbench']
    for c in candidates:
        if (c/'.aibl').is_dir():return c.resolve()
    where=explicit or 'this folder or ~/GitHub/my-workbench'
    raise SetupError(f'No workbench found at {where}. Open your workbench (the folder the installer created) and run this again, or pass --workbench.','local_state')

def refresh_installer(runner=command):
    # The registry is only as current as this checkout. Best effort: an offline or non-git copy still enrolls from what it has.
    if not (ROOT/'.git').exists():return {'refreshed':False,'reason':'not a git checkout'}
    try:runner(['git','-C',str(ROOT),'pull','--ff-only','--quiet']);return {'refreshed':True}
    except SetupError as exc:return {'refreshed':False,'reason':exc.reason}

def programs(reg):return [p for p in reg['programs'] if p.get('kind')!='foundation']

def access(publisher,runner=command):
    # A specific 404 is "not invited". Network and sign-in failures are raised, never read as absence.
    try:runner(['gh','api','repos/'+publisher]);return 'joined'
    except SetupError as exc:
        if exc.reason=='not_found':return 'not invited'
        if exc.reason=='authentication_missing':raise SetupError('GitHub is not signed in on this machine. The installer signed you in once; run gh auth login --web and try again.','authentication_missing')
        raise

def installed(workbench,release_product):
    state=Path(workbench)/'.aibl'/('installed-'+release_product+'.json')
    if not state.is_file():return None
    try:return json.loads(state.read_text(encoding='utf-8')).get('release_id') or 'unknown release'
    except (ValueError,OSError):return 'unreadable record'

def plan(workbench,reg=None,runner=command):
    reg=reg or registry();rows=[]
    for p in programs(reg):
        row={'id':p['id'],'label':p['label'].split(' (')[0],'publisher':p['publisher'],'release_product':p['release_product'],'adopt_skill':p.get('adopt_skill'),'access':access(p['publisher'],runner),'installed':installed(workbench,p['release_product']),'included_by':None}
        rows.append(row)
    # A bundled program (Workforce includes the Lab) may be granted a little after the purchase. Report it as included, never as missing.
    for p in programs(reg):
        for inc in p.get('includes',[]):
            holder=next(r for r in rows if r['id']==p['id']);target=next((r for r in rows if r['id']==inc),None)
            if target and holder['access']=='joined' and target['access']=='not invited':target['access']='included, invitation pending';target['included_by']=holder['label']
    for r in rows:r['next']=next_step(r)
    return rows

def next_step(r):
    if r['installed']:return 'already in this workbench ('+r['installed']+')'
    if r['access']=='joined':return ('run '+r['adopt_skill']) if r['adopt_skill'] else 'no adoption route yet; clone beside the workbench for now'
    if r['access']=='included, invitation pending':return 'wait for the invitation, then run this again'
    return 'not invited; nothing to do'

def enrollable(rows):return [r for r in rows if r['access']=='joined' and not r['installed']]

def show(rows):
    print('Programs this GitHub account can read:')
    for r in rows:print(f"  {r['label']}: {r['access']}"+(f" (included with {r['included_by']})" if r['included_by'] else '')+f" -> {r['next']}")

def record(workbench,rows,chosen,refresh):
    path=Path(workbench)/'.aibl'/'enroll.json'
    value={'schema_version':'aibl.enroll/v1','checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'programs':rows,'chosen':[r['id'] for r in chosen],'installer':{**source_provenance(),**refresh}}
    write(path,value);return path

def enroll(workbench=None,yes=False,check=False,only=None,runner=None,ask=input,reg=None):
    runner=runner or command  # resolved at call time so a test can replace the module's command
    workbench=find_workbench(workbench);refresh=refresh_installer(runner);rows=plan(workbench,reg,runner)
    if only:
        unknown=[o for o in only if o not in {r['id'] for r in rows}]
        if unknown:raise SetupError('Unknown program: '+', '.join(unknown)+'. Use a listed program id.')
    candidates=[r for r in enrollable(rows) if not only or r['id'] in only]
    result={'status':'checked','workbench':str(workbench),'installer':refresh,'programs':rows,'chosen':[]}
    if check:return result
    if not candidates:result['status']='nothing to enroll';record(workbench,rows,[],refresh);return result
    if not yes:
        # Never silent: an admin or a two-program student can read more than they want dropped in.
        answer=ask('Enroll in '+', '.join(r['label'] for r in candidates)+'? [Y/n] ').strip().lower()
        if answer not in ('','y','yes'):result['status']='declined';record(workbench,rows,[],refresh);return result
    result['status']='enrolled';result['chosen']=[r['id'] for r in candidates];result['next']=[{'id':r['id'],'do':r['next']} for r in candidates];result['record']=str(record(workbench,rows,candidates,refresh))
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter);p.add_argument('--workbench',help='The workbench folder. Default: this folder, then ~/GitHub/my-workbench.');p.add_argument('--check',action='store_true',help='Show what this account can read and change nothing.');p.add_argument('--yes',action='store_true',help='Skip the confirmation (for a coordinating session that already asked).');p.add_argument('--program',action='append',help='Enroll only this program id; repeatable.');p.add_argument('--json',action='store_true');a=p.parse_args()
    try:
        result=enroll(a.workbench,a.yes,a.check,a.program)
        if a.json:print(json.dumps(result,indent=2))
        else:
            show(result['programs'])
            if result['status']=='enrolled':
                print('Recorded. Next, in this order:')
                for n in result['next']:print(f"  {n['id']}: {n['do']}")
            elif result['status']=='nothing to enroll':print('Nothing new to enroll. Everything you can read is already here or not yet invited.')
            elif result['status']=='declined':print('Nothing changed. Run this again whenever you want.')
        return 0
    except (OSError,ValueError) as e:print('Enroll paused: '+str(e));return 1
if __name__=='__main__':sys.exit(main())
