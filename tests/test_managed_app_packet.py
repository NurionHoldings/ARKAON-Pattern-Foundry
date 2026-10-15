import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parent
if not (ROOT/'src'/'apf'/'managed_app_packet.py').is_file():
    ROOT=ROOT.parent
sys.path.insert(0,str(ROOT/'src'))
from apf.managed_app_packet import render_plan, validate_packet


class ManagedAppPacketTest(unittest.TestCase):
    def setUp(self):
        self.packet=json.loads((ROOT/'arkaon-managed-app-intake.json').read_text(encoding='utf-8'))

    def test_reference_intake_is_complete_and_drafts_plan(self):
        self.assertEqual(validate_packet(self.packet),[])
        plan=render_plan(self.packet)
        self.assertIn('Tenant Sales and Commission Control',plan)
        self.assertIn('운영 배포',plan)

    def test_enabled_api_needs_official_authority_and_stable_id(self):
        self.packet['source_systems'][1].update(enabled=True,owner_authorized=False,official_docs_ref='',stable_event_id_field='',credential_ref='')
        errors=validate_packet(self.packet)
        self.assertTrue(any('official_docs_ref' in item for item in errors))
        self.assertTrue(any('owner_authorized' in item for item in errors))

    def test_production_deploy_cannot_be_enabled_in_automation_packet(self):
        self.packet['approval']['production_deploy_authorized']=True
        self.assertTrue(any('운영 배포 승인' in item for item in validate_packet(self.packet)))

    def test_data_scope_choice_must_be_explicit(self):
        self.packet['security'].pop('tenant_isolation')
        self.assertTrue(any('업체 분리' in item for item in validate_packet(self.packet)))

    def test_cli_writes_review_plan_from_example(self):
        with tempfile.TemporaryDirectory() as temp:
            output=pathlib.Path(temp)/'review-plan.md'
            result=subprocess.run([sys.executable,str(ROOT/'src/apf/managed_app_packet.py'),str(ROOT/'arkaon-managed-app-intake.json'),'--plan-out',str(output)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertTrue(output.exists())
            self.assertIn('업체·운영자에게 확인할 질문',output.read_text(encoding='utf-8'))


if __name__=='__main__':
    unittest.main()
