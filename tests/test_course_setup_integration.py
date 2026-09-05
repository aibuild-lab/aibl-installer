"""Real Git and Python handoff; only GitHub/account boundaries are simulated."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import course_setup as setup


class LocalServices:
    def __init__(self,root,template=None):
        self.root=Path(root);self.template=template;self.server=self.root/'student.git'
        self.calls=[];self.interrupt_clone=False;self.lose_create_reply=False
        self.env={**os.environ,'GIT_CONFIG_GLOBAL':os.devnull,'GIT_CONFIG_NOSYSTEM':'1','GIT_TERMINAL_PROMPT':'0'}

    def git(self,*args,cwd=None):
        p=subprocess.run(['git',*args],cwd=cwd,text=True,encoding='utf-8',capture_output=True,env=self.env)
        if p.returncode:raise setup.SetupError('Synthetic Git operation failed: '+p.stderr)
        return p.stdout.strip()

    def route(self,folder):
        self.git('remote','set-url','origin','https://github.com/synthetic-student/my-workbench.git',cwd=folder)

    def __call__(self,args,cwd=None,interactive=False):
        self.calls.append(args)
        if args==['git','fetch','origin']:
            return self.git('fetch',str(self.server),'+refs/heads/*:refs/remotes/origin/*',cwd=cwd)
        if args[0]=='git':return self.git(*args[1:],cwd=cwd)
        if args[0]==sys.executable:
            p=subprocess.run(args,cwd=cwd,text=True,encoding='utf-8',capture_output=True,env=self.env)
            if p.returncode:raise setup.SetupError('Python handoff failed: '+p.stderr)
            return p.stdout.strip()
        if args[:2]==['gh','--version']:return 'gh version 2.70.0'
        if args[:2]==['claude','--version']:return '2.1.228 (synthetic account boundary)'
        if args[:3]==['gh','auth','status']:return ''
        if args==['gh','api','user']:return json.dumps({'login':'synthetic-student','name':'Synthetic Student','id':123})
        if args[:2]==['gh','api']:
            if args[2].startswith('repos/aibuild-lab/'):return json.dumps({'private':True})
            if not self.server.exists():raise setup.SetupError('HTTP 404','not_found')
            return json.dumps({'private':True,'full_name':'synthetic-student/my-workbench','id':456,'default_branch':'main','template_repository':{'full_name':'aibuild-lab/agent-essentials'}})
        if args[:3]==['gh','repo','create']:
            seed=self.root/'seed';seed.mkdir()
            if self.template:shutil.copytree(self.template,seed,dirs_exist_ok=True,ignore=shutil.ignore_patterns('.git','.aibl-local','__pycache__'))
            else:
                (seed/'scripts').mkdir();(seed/'scripts/aibl.py').write_text("from pathlib import Path\np=Path('context');p.mkdir(exist_ok=True)\nf=p/'project.md'\nif not f.exists():f.write_text('Synthetic starter')\n")
            self.git('init','--initial-branch=main',cwd=seed)
            self.git('config','--local','user.name','Synthetic Template',cwd=seed)
            self.git('config','--local','user.email','fixture@example.invalid',cwd=seed)
            self.git('add','.',cwd=seed);self.git('commit','-m','Independent synthetic student start',cwd=seed)
            self.git('clone','--bare',str(seed),str(self.server))
            if self.lose_create_reply:self.lose_create_reply=False;raise setup.SetupError('Lost creation reply','network')
            return ''
        if args[:3]==['gh','repo','clone']:
            target=Path(args[-1])
            if self.interrupt_clone:
                self.interrupt_clone=False;target.mkdir();self.git('init','--initial-branch=main',cwd=target)
                self.git('remote','add','origin',str(self.server),cwd=target);self.route(target)
                raise setup.SetupError('Interrupted clone','network')
            self.git('clone',str(self.server),str(target));self.route(target);return ''
        if args[:3]==['claude','auth','status']:return json.dumps({'loggedIn':True})
        if args[0]=='claude':return ''
        raise AssertionError('Unexpected simulated service call: '+repr(args))


class GitSetupIntegrationTests(unittest.TestCase):
    def setup_project(self,services,root):
        with contextlib.redirect_stdout(io.StringIO()):
            return setup.setup(setup.choose('agent-native-workforce'),root/'projects','my-workbench',root/'state',services,True)

    def test_real_git_clone_python_handoff_and_repeat(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td).resolve();services=LocalServices(root)
            result=self.setup_project(services,root);project=Path(result['workspace'])
            self.assertEqual((project/'context/project.md').read_text(),'Synthetic starter')
            (project/'context/project.md').write_text('Student choice')
            again=self.setup_project(services,root)
            self.assertEqual((project/'context/project.md').read_text(),'Student choice')
            self.assertEqual(result['workspace'],again['workspace'])
            self.assertEqual(services.git('config','--local','user.email',cwd=project),'123+synthetic-student@users.noreply.github.com')
            self.assertEqual(sum(c[:3]==['gh','repo','create'] for c in services.calls),1)
            self.assertEqual(sum(c[:3]==['gh','repo','clone'] for c in services.calls),1)

    def test_partial_clone_resumes_without_second_repository(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td).resolve();services=LocalServices(root);services.interrupt_clone=True
            with self.assertRaisesRegex(setup.SetupError,'Interrupted clone'):self.setup_project(services,root)
            result=self.setup_project(services,root)
            self.assertTrue((Path(result['workspace'])/'context/project.md').is_file())
            self.assertEqual(sum(c[:3]==['gh','repo','create'] for c in services.calls),1)
            self.assertEqual(sum(c[:3]==['gh','repo','clone'] for c in services.calls),1)

    def test_creation_reply_lost_is_reconciled_before_retry(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td).resolve();services=LocalServices(root);services.lose_create_reply=True
            with self.assertRaisesRegex(setup.SetupError,'Lost creation reply'):self.setup_project(services,root)
            self.assertEqual(self.setup_project(services,root)['status'],'ready')
            self.assertEqual(sum(c[:3]==['gh','repo','create'] for c in services.calls),1)

    def test_incomplete_clone_with_work_is_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td).resolve();services=LocalServices(root);services.interrupt_clone=True
            with self.assertRaises(setup.SetupError):self.setup_project(services,root)
            practice=root/'projects/.my-workbench-clone-in-progress/my-work.md';practice.write_text('Keep me')
            with self.assertRaisesRegex(setup.SetupError,'contains files'):self.setup_project(services,root)
            self.assertEqual(practice.read_text(),'Keep me')

    def test_killed_setup_releases_operation_guard(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);ready=root/'ready'
            scripts=Path(setup.__file__).parent
            code="import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from course_setup import setup_lock\nwith setup_lock(Path(sys.argv[2]),'my-workbench'):\n Path(sys.argv[3]).write_text('ready')\n sys.stdin.read()\n"
            child=subprocess.Popen([sys.executable,'-c',code,str(scripts),str(root/'state'),str(ready)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                deadline=time.monotonic()+5
                while not ready.exists() and child.poll() is None and time.monotonic()<deadline:time.sleep(.02)
                self.assertTrue(ready.exists())
                with self.assertRaisesRegex(setup.SetupError,'holds'):
                    with setup.setup_lock(root/'state','my-workbench'):pass
                child.terminate();child.wait(timeout=5)
                self.assertEqual(self.setup_project(LocalServices(root),root)['status'],'ready')
            finally:
                if child.poll() is None:child.terminate()
                child.communicate(timeout=5)

class SetupEvidenceTests(unittest.TestCase):
    def test_failed_clone_records_boundary_and_not_run_stages(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td).resolve();services=LocalServices(root);services.interrupt_clone=True
            with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(setup.SetupError):
                setup.setup(setup.choose('agent-native-workforce'),root/'projects','my-workbench',root/'state',services,True)
            attempt=json.loads((root/'state/my-workbench.json').read_text())['attempts'][-1]
            self.assertEqual(attempt['failed_stage'],'clone')
            self.assertEqual(attempt['last_proven_stage'],'private_repository')
            self.assertEqual(attempt['failure_domain'],'network')
            self.assertEqual(attempt['stages']['claude_auth'],'NOT_RUN')
            self.assertEqual(attempt['stages']['clone'],'FAIL')
            self.assertEqual(attempt['provenance']['bootstrap'],'unmeasured')
            self.assertEqual(len(attempt['provenance']['setup_sha256']),64)

    def test_success_records_actual_clone_identity_and_explicit_launch_skip(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td).resolve();services=LocalServices(root)
            with contextlib.redirect_stdout(io.StringIO()):
                result=setup.setup(setup.choose('agent-native-workforce'),root/'projects','my-workbench',root/'state',services,True)
            attempt=json.loads((root/'state/my-workbench.json').read_text())['attempts'][-1]
            self.assertEqual(attempt['provenance']['student_observed_tree'],services.git('rev-parse','HEAD^{tree}',cwd=result['workspace']))
            self.assertEqual(attempt['failed_stage'],None)
            self.assertEqual(attempt['stages']['claude_launch'],'NOT_RUN')
            self.assertEqual(attempt['last_proven_stage'],'claude_auth')
