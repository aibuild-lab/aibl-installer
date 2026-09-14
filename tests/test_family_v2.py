import copy
import json
import unittest
from pathlib import Path
import test_workbench_packages as fixtures
import workbench_packages as w


def core_components(files,version='0.0.10'):
    return [{'id':'workbench.method.'+name,'kind':'skill','version':version,'content_date':'2026-09-14','files':sorted(path for path in files if '/skills/'+name+'/' in path),'requires':[]} for name in sorted(w.CORE_SKILLS)]


def package_core(case,files,version='0.0.10'):
    files=dict(files)
    for name in w.CORE_SKILLS:
        content=files.get('.agents/skills/'+name+'/SKILL.md',name)
        for client in ('.agents','.claude'):files[client+'/skills/'+name+'/SKILL.md']=content
    fixtures.FamilyTests.package(case,'workbench-core',files,version)
    path=case.bundles/'workbench-core/manifest.json';manifest=w.read(path)
    manifest.update(schema_version='aibl.family-package/v2',components=core_components(files,version))
    path.write_bytes(w.encoded(manifest));case.family['packages']['workbench-core']['manifest_sha256']=w.digest(path.read_bytes())


class FamilyV2(unittest.TestCase):
    setUp=fixtures.FamilyTests.setUp
    package=fixtures.FamilyTests.package
    apply=fixtures.FamilyTests.apply
    def v2(self):
        self.package('agent-workbench', {'AGENTS.md': 'generic', 'blueprints/.gitkeep': ''},seed=True)
        package_core(self, {'.agents/skills/aibl-enroll/SKILL.md': 'enroll'})
        self.package('agent-essentials', {'blueprints/youtube-transcripts.md':'lesson8'})
        self.package('agent-workforce', {'workforce/start.md':'first action'})
        self.family.update(schema_version='aibl.family-lock/v2',installer_revision='a'*40,template_revision='b'*40,
                           compatibility={'legacy_template':'aibuild-lab/agent-essentials','legacy_workforce_product':'agent-native-workforce','legacy_workforce_publisher':'aibuild-lab/agent-native-workforce'})
        for product,pin in self.family['packages'].items():
            pin.update(publisher=w.V2_PUBLISHERS[product],release_tag=w.release_tag(product,pin['version']),release_target='b'*40)

    def test_standalone_then_optional_packages(self):
        self.v2();w.validate_family(self.family)
        self.apply(['agent-workbench','workbench-core'])
        self.assertFalse((self.root/'blueprints/youtube-transcripts.md').exists())
        self.apply(['agent-workforce'])
        self.assertNotIn('agent-essentials',w.read(self.root/w.MARKER)['packages'])
        self.apply(['agent-essentials'])
        self.assertEqual((self.root/'blueprints/youtube-transcripts.md').read_text(),'lesson8')
        self.assertEqual(self.apply(['agent-essentials'])['status'],'already_installed')

    def test_exact_v2_release_and_prerequisites(self):
        self.v2()
        for key,value in [('publisher','aibuild-lab/agent-essentials'),('release_tag','v0.0.10'),('release_target','main')]:
            bad=copy.deepcopy(self.family);bad['packages']['agent-essentials'][key]=value
            with self.assertRaises(w.ReleaseError):w.validate_family(bad)
        bad=copy.deepcopy(self.family);del bad['packages']['workbench-core']
        with self.assertRaises(w.ReleaseError):w.validate_family(bad)
        with self.assertRaisesRegex(w.ReleaseError,'template and core'):self.apply(['agent-workforce'])

    def test_lesson8_existing_student_asset_is_preserved(self):
        self.v2();self.apply(['agent-workbench','workbench-core'])
        path=self.root/'blueprints/youtube-transcripts.md';path.write_text('student blueprint')
        with self.assertRaisesRegex(w.ReleaseError,'preserved'):self.apply(['agent-essentials'])
        self.assertEqual(path.read_text(),'student blueprint')

    def test_v1_rejects_successor_pin_fields(self):
        self.v2();self.family['schema_version']='aibl.family-lock/v1';del self.family['packages']['workbench-core']
        with self.assertRaisesRegex(w.ReleaseError,'pin contract'):w.validate_family(self.family)

    def test_new_essentials_cannot_own_generic_skills(self):
        self.v2();self.package('agent-essentials',{'.agents/skills/aibl-personalize/SKILL.md':'collision'})
        pin=self.family['packages']['agent-essentials'];pin.update(publisher=w.PUBLIC_TEMPLATE,release_tag='agent-essentials-v0.0.10',release_target='b'*40)
        with self.assertRaisesRegex(w.ReleaseError,'ownership'):w.verify(self.bundles,'agent-essentials',pin)


if __name__=='__main__':unittest.main()
