import sys,tempfile,subprocess,json,shutil
from pathlib import Path
import argparse
p=argparse.ArgumentParser(description='Automated local cross-repository rehearsal. No GitHub mutations, student credit or platform qualification.')
p.add_argument('--internal-source',required=True);p.add_argument('--legacy-source',required=True);p.add_argument('--output',required=True);a=p.parse_args()
internal=Path(a.internal_source).resolve();installer=Path(__file__).resolve().parents[1]
for source in [internal,installer]:
 if subprocess.check_output(['git','status','--porcelain'],cwd=source,text=True).strip():raise SystemExit('Use clean committed source for an exact rehearsal receipt')
sys.path.insert(0,str(internal/'scripts'));import family_packages as f
sys.path.insert(0,str(installer/'scripts'));import workbench_packages as w
out=Path(a.output).resolve()
if out.is_relative_to(internal) or out.is_relative_to(installer):raise SystemExit('Choose external output')
out.mkdir(parents=True,exist_ok=False)
pins=f.build(out/'bundles',subprocess.check_output(['git','rev-parse','HEAD'],cwd=internal,text=True).strip());family={'packages':pins}
report={'scope':'automated local composition, no student credit or live access','internal_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=internal,text=True).strip(),'installer_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=installer,text=True).strip(),'output':str(out),'routes':[]}
for route in ['fresh','legacy']:
 root=out/route;root.mkdir();subprocess.run(['git','init','-q',str(root)],check=True);subprocess.run(['git','config','user.name','Synthetic Test'],cwd=root,check=True);subprocess.run(['git','config','user.email','test@example.invalid'],cwd=root,check=True)
 if route=='legacy':
  old=Path(a.legacy_source).resolve()
  for name in subprocess.check_output(['git','ls-files'],cwd=old,text=True).splitlines():
   src=old/name;dst=root/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
 (root/'personal.txt').write_text('synthetic personal content');subprocess.run(['git','add','.'],cwd=root,check=True);subprocess.run(['git','commit','-qm','synthetic independent student history'],cwd=root,check=True);remote=out/(route+'-remote.git');subprocess.run(['git','init','--bare','-q',str(remote)],check=True);subprocess.run(['git','remote','add','origin',str(remote)],cwd=root,check=True);subprocess.run(['git','push','-q','-u','origin','HEAD'],cwd=root,check=True);(root/'personal.txt').write_text('synthetic unpushed checkpoint');subprocess.run(['git','add','personal.txt'],cwd=root,check=True);subprocess.run(['git','commit','-qm','synthetic unpushed checkpoint'],cwd=root,check=True);head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip();(root/'uncommitted.txt').write_text('keep');(root/'.aibl-local/learning').mkdir(parents=True,exist_ok=True);(root/'.aibl-local/learning/synthetic.txt').write_text('keep local')
 first=w.compose(root,out/'bundles',family,['agent-workbench','agent-essentials']);repeat=w.compose(root,out/'bundles',family,['agent-workbench','agent-essentials'])
 if repeat['status']!='already_installed':raise AssertionError(repeat)
 checks={}
 for name,args in [('setup',['scripts/aibl.py','setup','--json']),('learning',['scripts/aibl_learning.py','status','--root','.']),('capabilities',['scripts/aibl_capabilities.py','inspect','--root','.','--property','status','--json'])]:
  r=subprocess.run([sys.executable,*args],cwd=root,text=True,capture_output=True);checks[name]={'exit':r.returncode,'output':r.stdout[:1000],'error':r.stderr[:500]}
  if r.returncode:raise RuntimeError(checks[name])
 adopted=w.compose(root,out/'bundles',family,['agent-workforce']);w.recover(root,adopted['rollback'])
 assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==head
 assert (root/'uncommitted.txt').read_text()=='keep' and (root/'.aibl-local/learning/synthetic.txt').read_text()=='keep local'
 assert subprocess.check_output(['git','rev-list','--count','@{upstream}..HEAD'],cwd=root,text=True).strip()=='1'
 (root/'personal.txt').write_text('deliberate practice edit');subprocess.run(['git','restore','--source=HEAD','--','personal.txt'],cwd=root,check=True);assert (root/'personal.txt').read_text()=='synthetic unpushed checkpoint'
 report['routes'].append({'route':route,'history_preserved':True,'uncommitted_and_local_preserved':True,'adoption_rollback':'passed','checks':checks})
(out/'receipt.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
