import contextlib,io,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import course_setup as setup

class Fake:
 def __init__(self):self.calls=[];self.exists=False;self.github=True;self.inactive_status_invalid=False;self.claude=True;self.access=True;self.private=True;self.template='aibuild-lab/agent-essentials'
 def __call__(self,args,cwd=None,interactive=False):
  self.calls.append(args)
  if args[-1]=='--version':return {'git':'git version 2.49.0','gh':'gh version 2.70.0','claude':'2.1.228'}.get(args[0],'Python 3.13.0')
  if args[:3]==['gh','auth','status']:
   if not self.github or self.inactive_status_invalid:raise setup.SetupError('Saved account status failed','authentication')
   return ''
  if args[:3]==['gh','auth','login']:self.github=True;return ''
  if args==['gh','api','user']:
   if not self.github:raise setup.SetupError('No selected GitHub sign-in','authentication_missing')
   return json.dumps({'login':'synthetic-student','name':'Student','id':123})
  if args[:3]==['gh','repo','list']:return json.dumps([{'nameWithOwner':'synthetic-student/my-workbench','isPrivate':self.private}] if self.exists else [])
  if args[:3]==['gh','repo','create']:self.exists=True;return ''
  if args[:3]==['gh','repo','clone']:
   p=Path(args[-1]);p.mkdir();(p/'.git').mkdir();return ''
  if args[:2]==['gh','api']:
   if args[2].startswith('repos/aibuild-lab/'):
    if not self.access:raise setup.SetupError('No access','not_found')
    return json.dumps({'private':True})
   if not self.exists:raise setup.SetupError('HTTP 404','not_found')
   return json.dumps({'private':self.private,'full_name':'synthetic-student/my-workbench','id':100,'template_repository':{'full_name':self.template}})
  if args[:3]==['git','remote','get-url']:return 'https://github.com/synthetic-student/my-workbench.git'
  if args==['git','rev-parse','--show-toplevel']:return str(Path(cwd).resolve())
  if args[:3]==['git','config','--local']:
   if '--get' in args:raise setup.SetupError('not set')
   return ''
  if args[:3]==['claude','auth','status']:return json.dumps({'loggedIn':self.claude})
  if args[:3]==['claude','auth','login']:self.claude=True;return ''
  return '{}'

class SetupTests(unittest.TestCase):
 def run_setup(self,fake,root,course='agent-native-workforce'):
  with contextlib.redirect_stdout(io.StringIO()):return setup.setup(setup.choose(course),Path(root)/'local','my-workbench',Path(root)/'state',fake,True)
 def test_course_selection_minimal_dependencies(self):
  for name in ['agent-essentials','agent-native-workforce']:self.assertEqual(setup.choose(name)['requirements'],['git','gh','python','claude'])
  self.assertIn('infisical',setup.choose('legacy-workshop')['requirements'])
 def test_fresh_and_resume_do_not_duplicate_repository(self):
  with tempfile.TemporaryDirectory() as d:
   f=Fake();self.assertEqual(self.run_setup(f,d)['status'],'ready');self.run_setup(f,d)
   self.assertEqual(sum(c[:3]==['gh','repo','create'] for c in f.calls),1);self.assertEqual(sum(c[:3]==['gh','repo','clone'] for c in f.calls),1)
   self.assertTrue(all('--global' not in c for c in f.calls))
 def test_missing_logins_recover_visibly_and_recheck_selected_api(self):
  with tempfile.TemporaryDirectory() as d:
   f=Fake();f.github=False;f.claude=False;result=self.run_setup(f,d);self.assertEqual(result['manual_interventions'],2)
   self.assertEqual(sum(c[:3]==['gh','auth','login'] for c in f.calls),1)
   self.assertEqual(sum(c==['gh','api','user'] for c in f.calls),2)
   self.assertFalse(any(c[:3]==['gh','auth','status'] for c in f.calls))
 def test_anw_demo_011_selected_api_works_despite_invalid_inactive_account(self):
  with tempfile.TemporaryDirectory() as d:
   f=Fake();f.inactive_status_invalid=True
   result=self.run_setup(f,d)
   self.assertEqual(result['status'],'ready');self.assertEqual(result['repository'],'synthetic-student/my-workbench')
   self.assertEqual(result['manual_interventions'],0)
   self.assertFalse(any(c[:2]==['gh','auth'] for c in f.calls))
   self.assertEqual(sum(c[:3]==['gh','repo','create'] for c in f.calls),1)
 def test_selected_api_failures_preserve_domain_and_never_login_or_create(self):
  for reason in ('authentication','network','permission','operation'):
   with self.subTest(reason=reason),tempfile.TemporaryDirectory() as d:
    f=Fake()
    def fail(args,**kwargs):
     if args==['gh','api','user']:
      f.calls.append(args);raise setup.SetupError('Selected API unavailable',reason)
     return f(args,**kwargs)
    with self.assertRaises(setup.SetupError) as error:self.run_setup(fail,d)
    self.assertEqual(error.exception.reason,reason)
    self.assertFalse(f.exists);self.assertFalse(any(c[:2]==['gh','auth'] or c[:3]==['gh','repo','create'] for c in f.calls))
    state=json.loads((Path(d)/'state/my-workbench.json').read_text());attempt=state['attempts'][-1]
    self.assertNotIn('repository',state)
    self.assertEqual(attempt['failed_stage'],'github_auth');self.assertEqual(attempt['failure_domain'],reason)
    self.assertEqual(attempt['last_proven_stage'],'tools');self.assertEqual(attempt['stages']['private_repository'],'NOT_RUN')
 def test_selected_api_error_classification_distinguishes_missing_auth_from_network(self):
  for code,detail,reason in [(4,'To get started with GitHub CLI, please run: gh auth login','authentication_missing'),(1,'Bad credentials (HTTP 401)','authentication'),(1,'error connecting to api.github.com','network'),(1,'Forbidden (HTTP 403)','permission')]:
   with self.subTest(reason=reason),patch.object(setup.subprocess,'run',return_value=subprocess.CompletedProcess(['gh','api','user'],code,'',detail)):
    with self.assertRaises(setup.SetupError) as error:setup.command(['gh','api','user'])
    self.assertEqual(error.exception.reason,reason)
 def test_selected_api_account_change_preserves_saved_repository_binding(self):
  with tempfile.TemporaryDirectory() as d:
   f=Fake();self.run_setup(f,d);before=len(f.calls)
   def changed(args,**kwargs):
    if args==['gh','api','user']:
     f.calls.append(args);return json.dumps({'login':'different-student','name':'Different Student','id':124})
    return f(args,**kwargs)
   with self.assertRaisesRegex(setup.SetupError,'another GitHub account'):self.run_setup(changed,d)
   state=json.loads((Path(d)/'state/my-workbench.json').read_text())
   self.assertEqual(state['repository'],'synthetic-student/my-workbench')
   self.assertFalse(any(c[:2]==['gh','auth'] or c[:3]==['gh','repo','create'] for c in f.calls[before:]))
 def test_missing_invitation_blocks_before_repo_creation(self):
  with tempfile.TemporaryDirectory() as d:
   f=Fake();f.access=False
   with self.assertRaisesRegex(setup.SetupError,'invitation'):self.run_setup(f,d)
   self.assertFalse(f.exists)
 def test_repository_collision_preserved(self):
  with tempfile.TemporaryDirectory() as d:
   f=Fake();f.exists=True;f.template='other/template'
   with self.assertRaisesRegex(setup.SetupError,'collision'):self.run_setup(f,d)
   self.assertFalse(any(c[:3]==['gh','repo','clone'] for c in f.calls))
 def test_public_name_collision_preserved(self):
  with tempfile.TemporaryDirectory() as d:
   f=Fake();f.exists=True;f.private=False
   with self.assertRaisesRegex(setup.SetupError,'public'):self.run_setup(f,d)
 def test_existing_folder_not_overwritten(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'local/my-workbench';p.mkdir(parents=True);(p/'mine').write_text('work')
   with self.assertRaisesRegex(setup.SetupError,'folder'):self.run_setup(Fake(),d)
   self.assertEqual((p/'mine').read_text(),'work')
 def test_missing_tool_actionable(self):
  def fail(args,**kw):raise FileNotFoundError()
  with self.assertRaisesRegex(setup.SetupError,'launcher'):setup.check_tools(fail)
 def test_invalid_names_and_synced_paths(self):
  for name in ['../oops','one/two','x.git','x.GIT','CON','nul.txt','COM1','workbench.']:
   with self.assertRaises(setup.SetupError):setup.repo_name(name)
  for path in ['/tmp/Dropbox/project','/tmp/OneDrive/project','/tmp/Documents/project']:
   with self.assertRaises(setup.SetupError):setup.safe_workspace(path)
 def test_wrong_origin_cannot_resume(self):
  with tempfile.TemporaryDirectory() as d:
   (Path(d)/'.git').mkdir()
   with self.assertRaisesRegex(setup.SetupError,'different origin'):setup.verify_existing(d,'student/my-workbench',lambda *a,**k:'https://github.com/other/repo.git')
 def test_empty_version_is_actionable(self):
  with self.assertRaisesRegex(setup.SetupError,'launcher'):setup.check_tools(lambda *a,**k:'')
 def test_setup_lock_blocks_duplicate_attempt(self):
  with tempfile.TemporaryDirectory() as d:
   state=Path(d)/'state';state.mkdir();(state/'my-workbench.lock').write_text('existing writer')
   f=Fake()
   with self.assertRaisesRegex(setup.SetupError,'lock'):self.run_setup(f,d)
   self.assertFalse(f.calls)
 def test_network_failure_is_not_reported_as_missing_invitation(self):
  with tempfile.TemporaryDirectory() as d:
   f=Fake()
   def fail(args,**kwargs):
    if args[:2]==['gh','api'] and args[2].startswith('repos/aibuild-lab/'):
     raise setup.SetupError('Network unavailable','network')
    return f(args,**kwargs)
   with self.assertRaisesRegex(setup.SetupError,'Network unavailable'):self.run_setup(fail,d)
   self.assertFalse(f.exists)
if __name__=='__main__':unittest.main()
