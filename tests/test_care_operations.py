import hashlib
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from apf.api import create_app
from apf.care_operations import CareOperationsRequest, build_operations_program
from apf.console import ConsoleSecurity
from apf.repository import MemoryRepository


def test_confirmation_and_executable_program():
    request = CareOperationsRequest()
    check = build_operations_program(request)
    assert check['artifact'] is None
    ready = build_operations_program(request.model_copy(update={'confirmed_digest': check['digest']}))
    artifact = ready['artifact']
    assert ready['status'] == 'PROGRAM_READY'
    assert hashlib.sha256(artifact['content'].encode()).hexdigest() == artifact['sha256']
    assert '__APF_CONFIG_JSON__' not in artifact['content']
    assert 'function save(' in artifact['content']
    assert 'function balances(' in artifact['content']
    assert "connect-src 'none'" in artifact['content']
    assert 'localStorage' not in artifact['content']
    assert ready['production_change_allowed'] is False
    stale = build_operations_program(request.model_copy(update={
        'capacity': 48, 'confirmed_digest': check['digest'],
    }))
    assert stale['status'] == 'CONFIRMATION_STALE'
    assert stale['artifact'] is None


def test_script_injection_is_escaped():
    request = CareOperationsRequest(brand='</script><script>alert(1)</script>')
    first = build_operations_program(request)
    packet = build_operations_program(request.model_copy(update={'confirmed_digest': first['digest']}))
    content = packet['artifact']['content']
    assert request.brand not in content
    serialized = content.split('<script id="config" type="application/json">')[1].split('</script>')[0]
    assert json.loads(serialized)['brand'] == request.brand


@pytest.mark.parametrize('bad', [{'capacity': True}, {'capacity': -1},
                                 {'modules': ['office', 'office']}, {'modules': []},
                                 {'modules': ['automatic_nhis_submit']}, {'brand': ' '}])
def test_invalid_requests(bad):
    with pytest.raises(ValidationError):
        CareOperationsRequest.model_validate(bad)


def test_api_auth_csrf_role():
    client = TestClient(create_app(repository=MemoryRepository(), console_security=ConsoleSecurity(
        environment='test', secret='s' * 32, allow_dev_sessions=True,
    )), base_url='https://testserver')
    path = '/v1/console/care-operations/program'
    assert client.post(path, json={}).status_code == 401
    assert client.get('/console/care-operations').status_code == 401
    csrf = client.post('/console/dev/session', json={
        'tenant_id': str(uuid4()), 'principal_id': str(uuid4()), 'role': 'operator',
    }).json()['csrf_token']
    assert client.post(path, json={}).status_code == 403
    r = client.post(path, json={}, headers={'X-CSRF-Token': csrf})
    assert r.status_code == 200
    assert r.headers['Cache-Control'] == 'no-store'
    assert client.post(path, json={'confirmed_digest': r.json()['digest']},
                       headers={'X-CSRF-Token': csrf}).json()['status'] == 'PROGRAM_READY'
    csrf = client.post('/console/dev/session', json={
        'tenant_id': str(uuid4()), 'principal_id': str(uuid4()), 'role': 'auditor',
    }).json()['csrf_token']
    assert client.post(path, json={}, headers={'X-CSRF-Token': csrf}).status_code == 403


def test_generated_program_executes_inventory_and_benefit_workflows(tmp_path):
    import re
    import subprocess

    request = CareOperationsRequest()
    initial = build_operations_program(request)
    ready = build_operations_program(request.model_copy(update={
        'confirmed_digest': initial['digest'],
    }))
    html = ready['artifact']['content']
    code = re.findall(r'<script>([\s\S]*?)</script>', html)[0]
    config = json.dumps(initial['configuration'], ensure_ascii=False)
    harness = r'''
const vm=require('node:vm'),assert=require('node:assert/strict');
const nodes=new Map();const node=s=>{if(!nodes.has(s))nodes.set(s,{textContent:'',innerHTML:'',querySelectorAll:()=>[]});return nodes.get(s)};
node('#config').textContent=CONFIG;
let values={};class FormData {constructor(){return Object.entries(values)[Symbol.iterator]()}}
const context={document:{querySelector:node},FormData,Date,Number,String,Object,JSON,Map,setTimeout};
vm.createContext(context);vm.runInContext(CODE,context);
function save(module,body){values=body;context.targetModule=module;vm.runInContext("module=targetModule;save({preventDefault(){},target:{}})",context)}
save('food_inventory',{date:'2026-10-17',code:'RICE',lot:'A',unit:'kg',expiry:'2026-12-31',direction:'입고',quantity:'10.25'});
assert.equal(vm.runInContext('entries.length',context),1);
save('food_inventory',{date:'2026-10-17',code:'RICE',lot:'A',unit:'kg',expiry:'2026-12-31',direction:'출고',quantity:'11'});
assert.equal(vm.runInContext('entries.length',context),1);
save('food_inventory',{date:'2026-10-17',code:'RICE',lot:'A',unit:'kg',expiry:'2026-12-31',direction:'출고',quantity:'2.125'});
assert.equal(vm.runInContext('balances()[0].quantity',context),8.125);
const benefit={date:'2026-10-17',resident:'R001',month:'2026-02',days:'28',dailyFee:'100000',copay:'20',extras:'300000',evidence:'manual evidence'};
save('benefit',benefit);assert.equal(vm.runInContext('entries[2].residentTotal',context),860000);
save('benefit',benefit);assert.equal(vm.runInContext('entries.length',context),3);
save('benefit',{...benefit,resident:'R002',days:'29'});assert.equal(vm.runInContext('entries.length',context),3);
console.log('program workflows passed');
'''
    harness = harness.replace('CONFIG;', json.dumps(config) + ';').replace('CODE,', json.dumps(code) + ',')
    path = tmp_path / 'program-check.cjs'
    path.write_text(harness)
    result = subprocess.run(['node', str(path)], capture_output=True, text=True, check=True)
    assert 'program workflows passed' in result.stdout
