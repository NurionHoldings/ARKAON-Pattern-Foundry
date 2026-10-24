"""Console API coverage for co-creation studio E2E contracts (not full browser flows)."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apf.api import create_app
from apf.co_creation_reference_gate import extract_reference_urls, reference_scope_digest
from apf.console import ConsoleSecurity
from apf.reference_material_consent import NOTICE_TEXT, NOTICE_VERSION
from apf.reference_material_consent import digest as reference_digest
from apf.reference_url_style import ReferenceStyleProfile
from apf.repository import MemoryRepository

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = "NARANG_RIDER"
CHAT_MESSAGE = (
    "이름: 온유 스튜디오\n고객: 동네 주민\n목적: 메뉴 소개\n"
    "차별점: 신선한 재료\n연락: demo@example.com\n"
    "로그인 사용자용 전자계약 랜딩 템플릿과 플랫폼 flow blueprint"
)
REFERENCE_URL = "https://example.com/reference-layout"


def _write_policy(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir(exist_ok=True)
    (config / "arkaon-conversational-co-creation.json").write_text(
        json.dumps({"schema_version": "apf.conversational-co-creation/v1"}),
        encoding="utf-8",
    )
    (config / "arkaon-proposal-quality.json").write_text(
        json.dumps({"schema_version": "apf.proposal-quality/v1", "minimum_proposal_quality_score": 0.2}),
        encoding="utf-8",
    )
    (config / "arkaon-co-creation-codegen.json").write_text(
        json.dumps({"schema_version": "apf.co-creation-codegen/v1", "require_scaffold_manifest": False}),
        encoding="utf-8",
    )


def _seed_experience(tmp_path: Path) -> None:
    patterns = tmp_path / "knowledge" / "landing-structure-patterns" / "proposed"
    patterns.mkdir(parents=True, exist_ok=True)
    for name, token in (
        ("landing.cross-platform.hero-single-cta.json", "landing-pattern:hero-single-cta"),
        ("landing.cross-platform.e-contract-flow.json", "landing-pattern:e-contract-flow"),
    ):
        (patterns / name).write_text(
            json.dumps(
                {
                    "schema_version": "apf.landing-structure-pattern-proposal/v1",
                    "pattern_id": name.replace(".json", ""),
                    "pattern_token": token,
                    "summary": token,
                    "evidence_digests": ["a" * 64],
                }
            ),
            encoding="utf-8",
        )


def _payment_digest(tenant_id, principal_id) -> str:
    return sha256(f"{tenant_id}|{principal_id}|{PLATFORM}|paid".encode()).hexdigest()


def _receipt_document(*, request_id: str, scope_digest: str, principal_id: str) -> dict[str, object]:
    request_digest = "sha256:" + "a" * 64
    consent_digest = "sha256:" + "b" * 64
    decision: dict[str, object] = {
        "decision": "SANDBOX_IMPLEMENTATION_ALLOWED",
        "reason": "USER_REQUEST_AND_NOTICE_CONFIRMED",
        "allowed_mode": "CLEAN_ROOM_IMPLEMENTATION",
        "request_digest": request_digest,
        "consent_digest": consent_digest,
        "direct_expression_reuse_allowed": False,
        "implementation_allowed": True,
        "merge_allowed": False,
        "deployment_allowed": False,
        "modification_proposals": [],
    }
    receipt: dict[str, object] = {
        "schema_version": "apf.reference-material-consent-receipt/1.0",
        "request_id": request_id,
        "scope_digest": scope_digest,
        "request_digest": request_digest,
        "consent_digest": consent_digest,
        "principal_id": principal_id,
        "notice_version": NOTICE_VERSION,
        "notice_digest": reference_digest(NOTICE_TEXT),
        "decision": decision,
    }
    receipt["receipt_digest"] = reference_digest(
        {key: value for key, value in receipt.items() if key != "receipt_digest"}
    )
    return receipt


def _plant_receipt(
    tmp_path: Path,
    *,
    request_id: str,
    principal_id: str,
    urls: tuple[str, ...],
    intended_use: str,
) -> None:
    scope = reference_scope_digest(urls=urls, intended_use=intended_use)
    receipt_dir = tmp_path / "state" / "reference-material-consents"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    (receipt_dir / f"{request_id}.json").write_text(
        json.dumps(_receipt_document(request_id=request_id, scope_digest=scope, principal_id=principal_id)),
        encoding="utf-8",
    )


def _session_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tenant_id, principal_id, *, role: str = "operator"):
    monkeypatch.setenv("APF_FOUNDRY_ROOT", str(tmp_path))
    _write_policy(tmp_path)
    _seed_experience(tmp_path)
    app = create_app(
        repository=MemoryRepository(),
        console_security=ConsoleSecurity(environment="test", secret="s" * 32, allow_dev_sessions=True),
    )
    client = TestClient(app, base_url="https://testserver")
    response = client.post(
        "/console/dev/session",
        json={"tenant_id": str(tenant_id), "principal_id": str(principal_id), "role": role},
    )
    assert response.status_code == 200
    return client, response.json()["csrf_token"]


def _complete_brief(**overrides: object) -> dict[str, str]:
    body = {
        "industry": "service",
        "title": "온유 스튜디오",
        "audience": "동네 주민",
        "story": "신선한 재료로 만드는 메뉴",
        "offerings": "점심 | 계절 메뉴\n저녁 | 코스",
        "difference": "매일 직접 준비",
        "process": "예약\n방문\n피드백",
        "contact": "demo@example.com",
        "theme": "editorial",
    }
    body.update(overrides)
    return body


def _chat(client: TestClient, csrf: str, tenant_id, principal_id, **extra: object):
    payload = {
        "platform_id": PLATFORM,
        "message": CHAT_MESSAGE,
        "scope": "BOTH",
        "payment_entitlement_digest": _payment_digest(tenant_id, principal_id),
        **extra,
    }
    return client.post("/v1/console/co-creation/chat", headers={"X-CSRF-Token": csrf}, json=payload)


def _fake_reference_style(*, url: str, now, fetch_payload=None) -> ReferenceStyleProfile:
    del now, fetch_payload
    return ReferenceStyleProfile(
        source_url=url.strip(),
        observation_digest="a" * 64,
        policy_route_refs=("surface/hero-primary-cta",),
        style_tags=("hero-forward",),
        structural_signals={"heading_count_bin": "4-5"},
    )


def test_reference_chat_requires_consent_then_studio_carries_request_id(tmp_path, monkeypatch):
    monkeypatch.setattr("apf.reference_url_style.observe_reference_style", _fake_reference_style)
    tenant_id, principal_id = uuid4(), uuid4()
    client, csrf = _session_client(tmp_path, monkeypatch, tenant_id, principal_id)
    request_id = "consent-return-flow"
    ref_message = f"참고 {REFERENCE_URL}\n{CHAT_MESSAGE}"
    urls = extract_reference_urls(
        message=ref_message, reference_site_url=REFERENCE_URL, feature_reference_urls=None
    )
    intended = ref_message[:500]
    blocked = _chat(
        client,
        csrf,
        tenant_id,
        principal_id,
        message=ref_message,
        reference_site_url=REFERENCE_URL,
    )
    assert blocked.status_code == 428
    assert blocked.json()["detail"]["code"] == "REFERENCE_CONSENT_REQUIRED"

    _plant_receipt(
        tmp_path,
        request_id=request_id,
        principal_id=str(principal_id),
        urls=urls,
        intended_use=intended,
    )
    ok = _chat(
        client,
        csrf,
        tenant_id,
        principal_id,
        message=ref_message,
        reference_site_url=REFERENCE_URL,
        reference_consent_request_id=request_id,
    )
    assert ok.status_code == 200
    session_id = ok.json()["session_id"]
    proposal_id = ok.json()["proposal_id"]

    put = client.put(
        f"/v1/console/co-creation/studio/{session_id}",
        headers={"X-CSRF-Token": csrf},
        json={
            "proposal_id": proposal_id,
            "brief": _complete_brief(title="동의 연결 후 저장"),
            "reference_consent_request_id": request_id,
        },
    )
    assert put.status_code == 200
    assert put.json()["draft"]["reference_consent_request_id"] == request_id

    get = client.get(f"/v1/console/co-creation/studio/{session_id}")
    assert get.status_code == 200
    assert get.json()["draft"]["brief"]["title"] == "동의 연결 후 저장"
    assert get.json()["draft"]["reference_consent_request_id"] == request_id

    preserve = client.put(
        f"/v1/console/co-creation/studio/{session_id}",
        headers={"X-CSRF-Token": csrf},
        json={"proposal_id": proposal_id, "brief": _complete_brief(title="동의 ID 유지")},
    )
    assert preserve.status_code == 200
    assert preserve.json()["draft"]["reference_consent_request_id"] == request_id


def test_studio_put_requires_csrf_and_get_roundtrip(tmp_path, monkeypatch):
    tenant_id, principal_id = uuid4(), uuid4()
    client, csrf = _session_client(tmp_path, monkeypatch, tenant_id, principal_id)
    chat = _chat(client, csrf, tenant_id, principal_id)
    assert chat.status_code == 200
    session_id = chat.json()["session_id"]
    proposal_id = chat.json()["proposal_id"]

    denied = client.put(
        f"/v1/console/co-creation/studio/{session_id}",
        json={"proposal_id": proposal_id, "brief": _complete_brief()},
    )
    assert denied.status_code == 403

    saved = client.put(
        f"/v1/console/co-creation/studio/{session_id}",
        headers={"X-CSRF-Token": csrf},
        json={"proposal_id": proposal_id, "brief": _complete_brief(title="서버 저장"), "local_project_id": "proj-1"},
    )
    assert saved.status_code == 200
    assert saved.json()["draft"]["local_project_id"] == "proj-1"

    loaded = client.get(f"/v1/console/co-creation/studio/{session_id}")
    assert loaded.status_code == 200
    assert loaded.json()["draft"]["brief"]["title"] == "서버 저장"
    assert loaded.json()["draft"]["local_project_id"] == "proj-1"


def test_studio_api_hides_draft_from_other_principals_and_tenants(tmp_path, monkeypatch):
    tenant_a, owner_a = uuid4(), uuid4()
    client_a, csrf_a = _session_client(tmp_path, monkeypatch, tenant_a, owner_a)
    chat = _chat(client_a, csrf_a, tenant_a, owner_a)
    session_id = chat.json()["session_id"]
    proposal_id = chat.json()["proposal_id"]
    assert (
        client_a.put(
            f"/v1/console/co-creation/studio/{session_id}",
            headers={"X-CSRF-Token": csrf_a},
            json={"proposal_id": proposal_id, "brief": _complete_brief()},
        ).status_code
        == 200
    )

    tenant_b, principal_b = uuid4(), uuid4()
    client_b, _ = _session_client(tmp_path, monkeypatch, tenant_b, principal_b)
    assert client_b.get(f"/v1/console/co-creation/studio/{session_id}").status_code == 404

    same_tenant_other = uuid4()
    client_c, csrf_c = _session_client(tmp_path, monkeypatch, tenant_a, same_tenant_other)
    assert client_c.get(f"/v1/console/co-creation/studio/{session_id}").status_code == 404
    assert (
        client_c.put(
            f"/v1/console/co-creation/studio/{session_id}",
            headers={"X-CSRF-Token": csrf_c},
            json={"proposal_id": proposal_id, "brief": _complete_brief(title="탈취 시도")},
        ).status_code
        == 404
    )


def test_site_builder_mobile_layout_contract():
    html = (ROOT / "services/site-builder.html").read_text(encoding="utf-8")
    css = (ROOT / "services/studio.css").read_text(encoding="utf-8")
    services_js = (ROOT / "services/services.js").read_text(encoding="utf-8")
    assert 'name="viewport"' in html
    assert 'id="mobile"' in html
    assert "@media(max-width:680px)" in css
    assert ".frame.phone" in css
    assert "canConsoleApiSync" in services_js
    assert "window.location.origin" in services_js
    assert "API_CROSS_ORIGIN" in services_js
