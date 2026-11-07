import base64
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from urllib.parse import urlencode

import pytest
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apf.hecto_pg import (
    Ledger,
    Merchant,
    Order,
    PGRejected,
    checkout,
    encrypt,
    packet_hash,
    parse_notification,
    verify_notification,
)
from apf.hecto_pg_http import HectoInquiry
from apf.hecto_pg_routes import build_router

NOW = datetime(2026, 11, 7, 2, 3, 4, tzinfo=UTC)


def merchant(platform='arkaon'):
    return Merchant(platform, 'testshop', '테스트상점', 'test-only-hash-secret', b'x' * 32,
                    'https://test.example/noti', 'https://test.example/return',
                    'https://test.example/cancel')


def order(platform='arkaon', payment='PAY001', business='BIZ001', principal='person1'):
    return Order(platform, principal, business, payment, '1000', '테스트상품')


def notification(m=None, o=None, **changes):
    m, o = m or merchant(), o or order()
    d = {'outStatCd': '0021', 'trdDtm': '20261107110304', 'mchtId': m.mcht_id,
             'mchtTrdNo': o.payment_id, 'trdAmt': o.amount_krw, 'method': 'CA', 'bizType': 'B0', 'trdNo': 'PG001'}
    d.update(changes)
    d['pktHash'] = packet_hash(d['outStatCd'], d['trdDtm'], d['mchtId'], d['mchtTrdNo'],
                               d['trdAmt'], m.hash_key)
    return d


def test_checkout_matches_card_form_contract_and_encrypts_amount():
    m, o = merchant(), order()
    data = checkout(m, o, NOW)
    f = data['fields']
    assert f['method'] == 'card' and data['action'].endswith('/card/main.do')
    assert f['trdDt'] == '20261107' and f['trdTm'] == '110304'
    dec = Cipher(algorithms.AES(m.aes_key), modes.ECB()).decryptor()
    padded = dec.update(base64.b64decode(f['trdAmt'])) + dec.finalize()
    unpad = padding.PKCS7(128).unpadder()
    assert unpad.update(padded) + unpad.finalize() == b'1000'
    assert f['pktHash'] == packet_hash(m.mcht_id, 'card', o.payment_id, '20261107',
                                      '110304', '1000', m.hash_key)
    assert m.hash_key not in json.dumps(data) and 'hash_key' not in repr(m)


@pytest.mark.parametrize('price', ['0', '-1', '01', '1.0', '1e3', '１２', '1000000000000'])
def test_invalid_amounts_rejected(price):
    with pytest.raises(PGRejected):
        replace(order(), amount_krw=price)


@pytest.mark.parametrize('url', ['http://x.test', 'https://u:p@x.test', 'https://x.test/#fragment',
                                'https://x.test/?redirect=x', 'https://x.test:444/noti'])
def test_callback_urls_are_server_controlled_https(url):
    with pytest.raises(PGRejected):
        replace(merchant(), noti_url=url)


def test_production_and_weak_key_rejected():
    with pytest.raises(PGRejected, match='PRODUCTION'):
        replace(merchant(), environment='production')
    with pytest.raises(PGRejected):
        encrypt('1000', b'short')


def test_parser_rejects_duplicate_fields_but_accepts_future_fields():
    with pytest.raises(PGRejected):
        parse_notification(b'mchtId=one&mchtId=two', 'application/x-www-form-urlencoded')
    assert parse_notification(b'futureField=ok', 'application/x-www-form-urlencoded')['futureField'] == 'ok'
    for body, content_type in [(b'x' * 16385, 'application/x-www-form-urlencoded'),
                               (b'{}', 'application/json'), (b'x=%FF', 'application/x-www-form-urlencoded')]:
        with pytest.raises(PGRejected):
            parse_notification(body, content_type)


@pytest.mark.parametrize('patch', [{'outStatCd': '0061'}, {'bizType': 'A8'}, {'bizType': 'C0'},
                                 {'method': 'VA'}, {'method': 'PZ'}, {'trdDtm': '20260230120000'}])
def test_non_approval_notifications_never_grant(patch):
    with pytest.raises(PGRejected):
        verify_notification(merchant(), order(), notification(**patch))


def test_tamper_and_cross_platform_rejected():
    d = notification(); d['trdAmt'] = '999'
    with pytest.raises(PGRejected):
        verify_notification(merchant(), order(), d)
    d = notification(); d['pktHash'] = '0' * 64
    with pytest.raises(PGRejected, match='HASH'):
        verify_notification(merchant(), order(), d)
    with pytest.raises(PGRejected):
        verify_notification(merchant('another'), order(), notification())


def test_ledger_restart_dedup_concurrent_delivery_and_outbox(tmp_path):
    path = tmp_path / 'pg.sqlite'
    ledger = Ledger(path); ledger.register(merchant(), order(), NOW)
    def deliver(_):
        return Ledger(path).receive(merchant(), notification(), lambda *args: True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(deliver, range(8))) == ['OK'] * 8
    assert Ledger(path).get('arkaon', 'person1', 'PAY001')['status'] == 'PAID'
    with ledger.connection() as db:
        assert db.execute('SELECT count(*) FROM hecto_outbox').fetchone()[0] == 1
    with pytest.raises(PGRejected):
        ledger.get('arkaon', 'person2', 'PAY001')
    with pytest.raises(PGRejected):
        ledger.get('other', 'person1', 'PAY001')


def test_inquiry_failure_leaves_no_payment_or_outbox(tmp_path):
    ledger = Ledger(tmp_path / 'pg.sqlite'); ledger.register(merchant(), order(), NOW)
    for inquiry in (None, lambda *args: False):
        with pytest.raises(PGRejected, match='INQUIRY'):
            ledger.receive(merchant(), notification(), inquiry)
    assert ledger.get('arkaon', 'person1', 'PAY001')['status'] == 'PENDING'
    with ledger.connection() as db:
        assert db.execute('SELECT count(*) FROM hecto_outbox').fetchone()[0] == 0


def test_order_id_conflict_and_provider_transaction_reuse_roll_back(tmp_path):
    ledger = Ledger(tmp_path / 'pg.sqlite'); ledger.register(merchant(), order(), NOW)
    with pytest.raises(PGRejected):
        ledger.register(merchant(), replace(order(), amount_krw='2000'), NOW)
    ledger.receive(merchant(), notification(), lambda *args: True)
    other = order(payment='PAY002', business='BIZ002')
    ledger.register(merchant(), other, NOW)
    with pytest.raises(PGRejected):
        ledger.receive(merchant(), notification(o=other), lambda *args: True)
    assert ledger.get('arkaon', 'person1', 'PAY002')['status'] == 'PENDING'


def test_inquiry_checks_actual_result_not_api_success():
    def transport(payload):
        return {'params': {**payload['params'], 'outStatCd':'0021', 'outRsltCd':result_code},
                'data': {**payload['data'], 'cnclAmt':'0'}}
    row = {'amount': '1000', 'request_date': '20261107', 'payment_id': 'PAY001'}
    inquiry = HectoInquiry(transport, clock=lambda: NOW)
    result_code = '0001'
    assert inquiry(merchant(), row, notification()) is False
    result_code = '0000'
    assert inquiry(merchant(), row, notification()) is True


def test_routes_auth_price_injection_noti_ack_and_status_isolation(tmp_path):
    ledger = Ledger(tmp_path / 'pg.sqlite')
    app = FastAPI()
    app.include_router(build_router({'arkaon': merchant()}, ledger,
        authorize_checkout=lambda req, platform: req.headers.get('x-csrf-token') == 'fixture',
        resolve_order=lambda req, platform, business: ('person1', '1000', '테스트상품'),
        authorize_read=lambda req, platform, payment: req.headers.get('x-principal', 'nobody'),
        inquiry=lambda *args: True))
    client = TestClient(app)
    url = '/v1/payments/hecto/arkaon'
    assert client.post(url+'/checkout', json={'business_order_id':'BIZ001'}).status_code == 403
    headers = {'x-csrf-token':'fixture'}  # TEST_DOUBLE, not a production authentication policy
    assert client.post(url+'/checkout', headers=headers,
                       json={'business_order_id':'BIZ001','amount':'1'}).status_code == 422
    r = client.post(url+'/checkout', headers=headers, json={'business_order_id':'BIZ001'})
    assert r.status_code == 200
    payment = r.json()['payment_id']; o = order(payment=payment)
    assert client.get(url+'/orders/'+payment).status_code == 404
    result = client.post(url+'/noti', content=urlencode(notification(o=o)),
                         headers={'content-type':'application/x-www-form-urlencoded'})
    assert result.content == b'OK'
    assert client.get(url+'/orders/'+payment, headers={'x-principal':'person1'}).json()['status'] == 'PAID'
    assert client.post(url+'/noti', content='bad', headers={'content-type':'application/json'}).content == b'FAIL'
    assert client.post(url+'/return', json={'outStatCd':'0021'}).status_code == 404


def test_config_never_enables_examples_or_production(tmp_path):
    from apf.hecto_pg_config import load_merchants
    path = tmp_path / 'config.json'
    fixture = {'schema_version':'apf.hecto-platform-map/v1', 'enabled':False,
               'environment':'sandbox', 'platforms':{}}
    path.write_text(json.dumps(fixture))
    with pytest.raises(PGRejected, match='DISABLED'):
        load_merchants(path, environ={})
    fixture['enabled'] = True
    fixture['platforms'] = {'arkaon': {'enabled':True, 'merchant_id_env':'MID',
        'hash_key_env':'HASH', 'aes_key_env':'AES', 'merchant_name':'테스트상점',
        'noti_url':'https://test.example/noti', 'next_url':'https://test.example/return',
        'cancel_url':'https://test.example/cancel'}}
    path.write_text(json.dumps(fixture))
    merchants = load_merchants(path, environ={'MID':'testshop', 'HASH':'fixture', 'AES':'x'*32})
    assert merchants['arkaon'].platform_id == 'arkaon'
    with pytest.raises(PGRejected, match='MISSING'):
        load_merchants(path, environ={})


def test_inquiry_response_tampering_is_rejected():
    row = {'amount':'1000', 'request_date':'20261107', 'payment_id':'PAY001'}
    for change in ({'trdAmt':'1'}, {'cnclAmt':'1'}, {'pktHash':'0'*64}, {'method':'VA'}):
        def transport(payload, change=change):
            return {'params':{**payload['params'], 'outStatCd':'0021', 'outRsltCd':'0000'},
                    'data':{**payload['data'], 'cnclAmt':'0', **change}}
        assert HectoInquiry(transport, clock=lambda:NOW)(merchant(), row, notification()) is False


def test_malformed_hash_rejected_without_unicode_comparison_error():
    d = notification(); d['pktHash'] = '가' * 64
    with pytest.raises(PGRejected, match='HASH'):
        verify_notification(merchant(), order(), d)
