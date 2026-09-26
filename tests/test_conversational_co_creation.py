import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apf.api import create_app
from apf.console import ConsoleSecurity
from apf.conversational_co_creation import (
    CoCreationRejected,
    CoCreationScope,
    ConversationalCoCreationEngine,
    verify_payment_entitlement,
)
from apf.conversational_co_creation_bridge import bridge_co_creation_proposal
from apf.repository import MemoryRepository

NOW = datetime(2031, 8, 1, tzinfo=UTC)


def _write_policy(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "arkaon-conversational-co-creation.json").write_text(
        json.dumps({"schema_version": "apf.conversational-co-creation/v1"}),
        encoding="utf-8",
    )
    (config / "arkaon-proposal-quality.json").write_text(
        json.dumps({"schema_version": "apf.proposal-quality/v1", "minimum_proposal_quality_score": 0.2}),
        encoding="utf-8",
    )


def _seed_experience(tmp_path: Path) -> None:
    patterns = tmp_path / "knowledge" / "landing-structure-patterns" / "proposed"
    patterns.mkdir(parents=True)
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


def test_verify_payment_entitlement_digest():
    tenant = str(uuid4())
    principal = str(uuid4())
    platform = "NARANG_RIDER"
    digest = sha256(f"{tenant}|{principal}|{platform}|paid".encode()).hexdigest()
    assert verify_payment_entitlement(
        tenant_id=tenant,
        principal_id=principal,
        platform_id=platform,
        digest=digest,
    )


def test_chat_rejects_without_experience(tmp_path):
    _write_policy(tmp_path)
    engine = ConversationalCoCreationEngine(foundry_root=tmp_path)
    tenant, principal = str(uuid4()), str(uuid4())
    digest = sha256(f"{tenant}|{principal}|MJN|paid".encode()).hexdigest()
    with pytest.raises(CoCreationRejected) as error:
        engine.chat(
            tenant_id=tenant,
            principal_id=principal,
            platform_id="MJN",
            message="전자계약 funnel 템플릿 만들어줘",
            scope=CoCreationScope.BOTH,
            payment_entitlement_digest=digest,
            now=NOW,
        )
    assert error.value.code == "INSUFFICIENT_EXPERIENCE"


def test_chat_produces_template_and_platform_blueprint(tmp_path):
    _write_policy(tmp_path)
    _seed_experience(tmp_path)
    engine = ConversationalCoCreationEngine(foundry_root=tmp_path)
    tenant, principal = str(uuid4()), str(uuid4())
    platform = "NARANG_RIDER"
    digest = sha256(f"{tenant}|{principal}|{platform}|paid".encode()).hexdigest()
    proposal = engine.chat(
        tenant_id=tenant,
        principal_id=principal,
        platform_id=platform,
        message="전자계약 4단계 funnel과 마이페이지가 있는 플랫폼 템플릿 제안해줘",
        scope=CoCreationScope.BOTH,
        payment_entitlement_digest=digest,
        now=NOW,
    )
    assert proposal.template_blueprint
    assert proposal.platform_blueprint
    assert any("flow/step-e-contract" in item.route_ref for item in proposal.platform_blueprint)
    assert proposal.evidence_table
    paths = bridge_co_creation_proposal(
        foundry_root=tmp_path,
        proposal=proposal,
        policy=engine.policy,
        run_id="run-co",
        now=NOW,
        dry_run=False,
    )
    assert paths
    packet = json.loads(Path(paths[0]).read_text(encoding="utf-8"))
    assert packet["packet_kind"] == "CONVERSATIONAL_CO_CREATION_PROPOSAL"


def test_chat_applies_reference_site_url(tmp_path):
    _write_policy(tmp_path)
    _seed_experience(tmp_path)
    engine = ConversationalCoCreationEngine(foundry_root=tmp_path)
    tenant, principal = str(uuid4()), str(uuid4())
    platform = "NARANG_RIDER"
    digest = sha256(f"{tenant}|{principal}|{platform}|paid".encode()).hexdigest()
    html = b"<html>Step 1 Step 2 CTA</html>"
    proposal = engine.chat(
        tenant_id=tenant,
        principal_id=principal,
        platform_id=platform,
        message="reference style landing template",
        scope=CoCreationScope.TEMPLATE,
        payment_entitlement_digest=digest,
        now=NOW,
        reference_site_url="https://example.test/",
        fetch_payload=lambda _url: html,
    )
    assert proposal.reference_site_url == "https://example.test/"
    assert proposal.reference_style_path
    assert "reference feel" in proposal.template_blueprint[0].purpose


def test_console_co_creation_chat_endpoint():
    app = create_app(
        repository=MemoryRepository(),
        console_security=ConsoleSecurity(
            environment="test", secret="s" * 32, allow_dev_sessions=True
        ),
    )
    client = TestClient(app, base_url="https://testserver")
    tenant_id, principal_id = uuid4(), uuid4()
    session = client.post(
        "/console/dev/session",
        json={"tenant_id": str(tenant_id), "principal_id": str(principal_id), "role": "operator"},
    )
    csrf = session.json()["csrf_token"]
    platform = "NARANG_RIDER"
    digest = sha256(f"{tenant_id}|{principal_id}|{platform}|paid".encode()).hexdigest()
    response = client.post(
        "/v1/console/co-creation/chat",
        headers={"X-CSRF-Token": csrf},
        json={
            "platform_id": platform,
            "message": "로그인 사용자용 전자계약 랜딩 템플릿과 플랫폼 flow blueprint",
            "scope": "BOTH",
            "payment_entitlement_digest": digest,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["assistant_reply"]
    assert body["template_blueprint"]
    assert body["platform_blueprint"]
