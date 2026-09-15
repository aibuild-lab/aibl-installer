import copy
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
from test_family_v2 import FamilyV2, package_core
import student_updates as u
import workbench_packages as w


class Backend:
    def __init__(self,case):self.case=case;self.pr=None;self.creates=0;self.merges=0;self.uncertain=False
    def owner(self,repository):return 'main'
    def lookup(self,*args):return self.pr
    def create(self,repository,branch,base,operation):
        self.creates+=1
        head=u.git(self.case.root,'ls-remote','origin','refs/heads/'+branch).split()[0]
        base_sha=u.git(self.case.root,'ls-remote','origin','refs/heads/'+base).split()[0]
        self.pr={'number':1,'html_url':'https://github.com/student/my-workbench/pull/1','state':'open','merged_at':None,'head':{'sha':head,'ref':branch},'base':{'ref':base,'sha':base_sha,'repo':{'full_name':repository}}}
        if self.uncertain:raise OSError('lost response')
        return self.pr
    def read(self,*args):return self.pr
    def merge(self,repository,number,head):
        self.merges+=1
        # Real remote graph, synthetic GitHub boundary. Fast-forward provider
        # behavior lets us verify local synchronization without a hosted write.
        subprocess.run(['git','--git-dir',str(self.case.remote),'update-ref','refs/heads/main',head],check=True,capture_output=True)
        self.pr.update(merged_at='2026-09-14T00:00:00Z',merge_commit_sha=head,state='closed')
        if self.uncertain:raise OSError('lost merge response')
        return {'merged':True}


class Updates(unittest.TestCase):
    package=FamilyV2.package
    apply=FamilyV2.apply
    v2=FamilyV2.v2
    def setUp(self):
        FamilyV2.setUp(self);self.v2();self.apply(['agent-workbench','workbench-core'])
        (self.root/'.gitignore').write_text('.aibl-local/\n')
        u.git(self.root,'init','-b','main');u.git(self.root,'config','user.name','Synthetic Student');u.git(self.root,'config','user.email','student@example.invalid')
        u.git(self.root,'add','.');u.git(self.root,'commit','-m','initial')
        self.remote=Path(self.tmp.name)/'remote.git'
        subprocess.run(['git','init','--bare',str(self.remote)],check=True,capture_output=True)
        u.git(self.root,'remote','add','origin',str(self.remote));u.git(self.root,'push','-u','origin','main')
        self.backend=Backend(self)
        self.addCleanup(patch.stopall)
        patch.object(u,'repository',return_value='student/my-workbench').start()
        # A new reviewed release of the installed core, retaining exact v2 pin.
        package_core(self,{'.agents/skills/aibl-enroll/SKILL.md':'updated'},version='0.0.11')
        path=self.bundles/'workbench-core/manifest.json'
        pin=self.family['packages']['workbench-core'];pin.update(manifest_sha256=w.digest(path.read_bytes()),publisher=w.PUBLIC_TEMPLATE,release_tag='workbench-core-v0.0.11',release_target='b'*40)
    def prepare(self):return u.prepare(self.root,self.bundles,self.family,'one',Path(self.tmp.name)/'preparations',self.backend)
    def merge(self):
        state=self.prepare();u.propose(self.root,'one',self.backend)
        return u.approve_and_merge(self.root,'one',state['head_revision'],self.backend)

    def test_one_grouped_pr_then_sync_preserves_work(self):
        (self.root/'unfinished.md').write_text('unfinished')
        (self.root/'.aibl-local/learning.json').write_text('local learning')
        before=u.git(self.root,'rev-parse','HEAD');state=self.prepare()
        self.assertEqual(before,u.git(self.root,'rev-parse','HEAD'))
        self.assertEqual((self.root/'.agents/skills/aibl-enroll/SKILL.md').read_text(),'enroll')
        self.assertFalse(Path(state['candidate']).is_relative_to(self.root))
        self.merge();u.propose(self.root,'one',self.backend)
        self.assertEqual(self.backend.creates,1)
        result=u.synchronize(self.root,'one')
        self.assertEqual(result['stage'],'local_synchronized');self.assertIn('pending',result['native_verification'])
        self.assertEqual((self.root/'unfinished.md').read_text(),'unfinished')
        self.assertEqual((self.root/'.aibl-local/learning.json').read_text(),'local learning')
        self.assertEqual((self.root/'.agents/skills/aibl-enroll/SKILL.md').read_text(),'updated')
        self.assertEqual(u.synchronize(self.root,'one'),result)

    def test_uncertain_external_results_do_not_duplicate(self):
        self.backend.uncertain=True;self.merge();self.merge()
        self.assertEqual(self.backend.creates,1);self.assertEqual(self.backend.merges,1)
        u.synchronize(self.root,'one')

    def test_unpushed_commit_stops_without_discard(self):
        (self.root/'my-work.md').write_text('unpushed');u.git(self.root,'add','my-work.md');u.git(self.root,'commit','-m','my work')
        head=u.git(self.root,'rev-parse','HEAD');self.merge()
        with self.assertRaises(w.ReleaseError):u.synchronize(self.root,'one')
        self.assertEqual(u.git(self.root,'rev-parse','HEAD'),head);self.assertEqual((self.root/'my-work.md').read_text(),'unpushed')

    def test_customized_supplied_file_stops_before_pr(self):
        (self.root/'.agents/skills/aibl-enroll/SKILL.md').write_text('custom')
        with self.assertRaisesRegex(w.ReleaseError,'Customized'):self.prepare()
        self.assertEqual(self.backend.creates,0)

    def test_wrong_approval_and_changed_pr_refused(self):
        state=self.prepare();u.propose(self.root,'one',self.backend)
        with self.assertRaises(w.ReleaseError):u.approve_and_merge(self.root,'one','f'*40,self.backend)
        self.backend.pr['head']['sha']='f'*40
        with self.assertRaises(w.ReleaseError):u.approve_and_merge(self.root,'one',state['head_revision'],self.backend)
        self.assertEqual(self.backend.merges,0)

    def test_after_remote_merge_local_change_preserved(self):
        self.merge();path=self.root/'.agents/skills/aibl-enroll/SKILL.md';path.write_text('later')
        with self.assertRaisesRegex(w.ReleaseError,'changed'):u.synchronize(self.root,'one')
        self.assertEqual(path.read_text(),'later')

    def test_interrupted_after_commit_resumes_same_candidate(self):
        save=u.save
        def interrupt(path,state):
            if state['stage']=='prepared':raise OSError('synthetic crash after commit')
            save(path,state)
        with patch.object(u,'save',side_effect=interrupt):
            with self.assertRaises(OSError):self.prepare()
        state=self.prepare();self.assertEqual(state['stage'],'prepared')
        self.assertEqual(u.git(state['candidate'],'rev-list','--count',state['base_revision']+'..HEAD'),'1')

    def test_changed_origin_refuses_before_push(self):
        self.prepare()
        with patch.object(u,'repository',return_value='another/repository'):
            with self.assertRaisesRegex(w.ReleaseError,'origin changed'):u.propose(self.root,'one',self.backend)
        self.assertEqual(self.backend.creates,0)

    def test_candidate_unreviewed_index_refused(self):
        original=u.git
        def inject(root,*args):
            result=original(root,*args)
            if args[:2]==('worktree','add'):
                candidate=Path(args[3]);(candidate/'unreviewed.txt').write_text('not a package')
                original(candidate,'add','unreviewed.txt')
            return result
        with patch.object(u,'git',side_effect=inject):
            with self.assertRaisesRegex(w.ReleaseError,'unreviewed'):self.prepare()
        self.assertEqual(self.backend.creates,0)

    def test_remote_base_advance_refused_before_merge(self):
        state=self.prepare();u.propose(self.root,'one',self.backend)
        (self.root/'AGENTS.md').write_text('later instructions');u.git(self.root,'add','AGENTS.md');u.git(self.root,'commit','-m','later');u.git(self.root,'push','origin','main')
        with self.assertRaisesRegex(w.ReleaseError,'base changed'):u.approve_and_merge(self.root,'one',state['head_revision'],self.backend)
        self.assertEqual(self.backend.merges,0)

    def test_new_ignored_destination_after_preview_preserved(self):
        name='.agents/skills/aibl-enroll/new.md'
        package_core(self,{'.agents/skills/aibl-enroll/SKILL.md':'updated',name:'supplied'},version='0.0.11')
        path=self.bundles/'workbench-core/manifest.json'
        self.family['packages']['workbench-core'].update(manifest_sha256=w.digest(path.read_bytes()),publisher=w.PUBLIC_TEMPLATE,release_tag='workbench-core-v0.0.11',release_target='b'*40)
        self.merge();(self.root/name).write_text('student original')
        with (self.root/'.git/info/exclude').open('a') as stream:stream.write('\n'+name+'\n')
        with self.assertRaisesRegex(w.ReleaseError,'destinations changed'):u.synchronize(self.root,'one')
        self.assertEqual((self.root/name).read_text(),'student original')

    def test_real_merge_commit_is_checked(self):
        state=self.prepare();u.propose(self.root,'one',self.backend)
        def merge(repository,number,head):
            tree=u.git(state['candidate'],'rev-parse',head+'^{tree}')
            merged=u.git(state['candidate'],'commit-tree',tree,'-p',state['base_revision'],'-p',head,'-m','Synthetic provider merge')
            u.git(state['candidate'],'push','origin',merged+':refs/heads/main')
            self.backend.pr.update(merged_at='2026-09-14T00:00:00Z',merge_commit_sha=merged,state='closed')
        self.backend.merge=merge
        u.approve_and_merge(self.root,'one',state['head_revision'],self.backend)
        self.assertEqual(u.synchronize(self.root,'one')['stage'],'local_synchronized')


if __name__=='__main__':unittest.main()
