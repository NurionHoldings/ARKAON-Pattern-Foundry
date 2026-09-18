import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest

from apf.co_creation_codegen import CoCreationCodegenEngine
from apf.co_creation_preview import CoCreationPreviewEngine, CoCreationPreviewRejected

NOW = datetime(2031, 9, 1, tzinfo=UTC)
APPROVAL = "a" * 64
PREVIEW_BASE = "https://preview.example.test"


def _write_policies(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    for name, body in (
        ("arkaon-co-creation-codegen.json", {"schema_version": "apf.co-creation-codegen/v1"}),
        ("arkaon-co-creation-preview.json", {"schema_version": "apf.co-creation-preview/v1", "preview_ttl_minutes": 60}),
        ("arkaon-billing-entitlement.json", {"schema_version": "apf.billing-entitlement/v1", "mode": "DIGEST"}),
        ("arkaon-conversational-co-creation.json", {"schema_version": "apf.conversational-co-creation/v1"}),
        ("arkaon-proposal-quality.json", {"schema_version": "apf.proposal-quality/v1", "minimum_proposal_quality_score": 0.2}),
        ("arkaon-co-creation-feedback-loop.json", {"schema_version": "apf.co-creation-feedback-loop/v1"}),
    ):
        (config / name).write_text(json.dumps(body), encoding="utf-8")


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


def _seed_preview_ready_chain(tmp_path: Path) -> dict[str, str]:
    tenant_id = str(uuid4())
    principal_id = str(uuid4())
    platform = "NARANG_RIDER"
    session_id = str(uuid4())
    proposal_id = sha256(b"preview-chain").hexdigest()[:24]
    digest = sha256(f"{tenant_id}|{principal_id}|{platform}|paid".encode()).hexdigest()
    proposal = {
        "schema_version": "apf.co-creation-proposal/v1",
        "proposal_id": proposal_id,
        "session_id": session_id,
        "tenant_id": tenant_id,
        "principal_id": principal_id,
        "platform_id": platform,
        "review_status": "PROPOSED",
        "template_blueprint": [
            {
                "section_id": "hero",
                "purpose": "hero capture",
                "pattern_token": "landing-pattern:hero-single-cta",
                "cta_slot": True,
            }
        ],
        "platform_blueprint": [{"route_ref": "flow/step-e-contract", "purpose": "e-contract funnel"}],
    }
    proposal_root = tmp_path / "state" / "co-creation" / "proposals"
    proposal_root.mkdir(parents=True)
    (proposal_root / f"{proposal_id}.json").write_text(json.dumps(proposal), encoding="utf-8")

    scaffold = {
        "schema_version": "apf.co-creation-template-scaffold/v1",
        "proposal_id": proposal_id,
        "platform_id": platform,
        "sections": [
            {
                "section_id": "hero",
                "purpose": "hero capture",
                "pattern_token": "landing-pattern:hero-single-cta",
                "codegen_status": "PENDING_REVIEW",
            }
        ],
        "surfaces": [{"route_ref": "flow/step-e-contract", "purpose": "e-contract funnel"}],
        "reference_style_bundle": {"style_tags": ["single-primary-cta"]},
    }
    scaffold_root = tmp_path / "state" / "co-creation" / "scaffolds"
    scaffold_root.mkdir(parents=True)
    (scaffold_root / f"{proposal_id}-scaffold01.json").write_text(json.dumps(scaffold), encoding="utf-8")

    codegen = CoCreationCodegenEngine(foundry_root=tmp_path)
    codegen.run_codegen(proposal_id=proposal_id, operator_approval_digest=APPROVAL, now=NOW)
    codegen.approve_codegen(
        proposal_id=proposal_id,
        operator_codegen_approval_digest="b" * 64,
        now=NOW,
    )
    return {
        "proposal_id": proposal_id,
        "tenant_id": tenant_id,
        "principal_id": principal_id,
        "platform_id": platform,
        "digest": digest,
        "session_id": session_id,
    }


def test_start_preview_provisions_active_sandbox(tmp_path):
    _write_policies(tmp_path)
    chain = _seed_preview_ready_chain(tmp_path)
    engine = CoCreationPreviewEngine(foundry_root=tmp_path)
    runtime = engine.start_preview(
        proposal_id=chain["proposal_id"],
        tenant_id=chain["tenant_id"],
        principal_id=chain["principal_id"],
        platform_id=chain["platform_id"],
        preview_base_url=PREVIEW_BASE,
        payment_entitlement_digest=chain["digest"],
        now=NOW,
    )
    assert runtime.status.value == "ACTIVE"
    assert runtime.preview_url.startswith(PREVIEW_BASE)
    assets = tmp_path / runtime.assets_root
    assert (assets / "index.html").is_file()
    assert (assets / "sections" / "hero.html").is_file()


def test_get_sandbox_rejects_cross_tenant_access(tmp_path):
    _write_policies(tmp_path)
    chain = _seed_preview_ready_chain(tmp_path)
    engine = CoCreationPreviewEngine(foundry_root=tmp_path)
    runtime = engine.start_preview(
        proposal_id=chain["proposal_id"],
        tenant_id=chain["tenant_id"],
        principal_id=chain["principal_id"],
        platform_id=chain["platform_id"],
        preview_base_url=PREVIEW_BASE,
        payment_entitlement_digest=chain["digest"],
        now=NOW,
    )
    with pytest.raises(CoCreationPreviewRejected) as error:
        engine.get_sandbox(
            sandbox_id=runtime.sandbox_id,
            tenant_id=str(uuid4()),
            principal_id=chain["principal_id"],
            platform_id=chain["platform_id"],
            payment_entitlement_digest=chain["digest"],
            now=NOW,
        )
    assert error.value.code == "TENANT_FORBIDDEN"


def test_get_sandbox_rejects_inactive_entitlement(tmp_path):
    _write_policies(tmp_path)
    chain = _seed_preview_ready_chain(tmp_path)
    engine = CoCreationPreviewEngine(foundry_root=tmp_path)
    runtime = engine.start_preview(
        proposal_id=chain["proposal_id"],
        tenant_id=chain["tenant_id"],
        principal_id=chain["principal_id"],
        platform_id=chain["platform_id"],
        preview_base_url=PREVIEW_BASE,
        payment_entitlement_digest=chain["digest"],
        now=NOW,
    )
    with pytest.raises(CoCreationPreviewRejected) as error:
        engine.get_sandbox(
            sandbox_id=runtime.sandbox_id,
            tenant_id=chain["tenant_id"],
            principal_id=chain["principal_id"],
            platform_id=chain["platform_id"],
            payment_entitlement_digest="c" * 64,
            now=NOW,
        )
    assert error.value.code == "ENTITLEMENT_INACTIVE"


def test_sandbox_expires_after_ttl(tmp_path):
    _write_policies(tmp_path)
    chain = _seed_preview_ready_chain(tmp_path)
    engine = CoCreationPreviewEngine(foundry_root=tmp_path)
    runtime = engine.start_preview(
        proposal_id=chain["proposal_id"],
        tenant_id=chain["tenant_id"],
        principal_id=chain["principal_id"],
        platform_id=chain["platform_id"],
        preview_base_url=PREVIEW_BASE,
        payment_entitlement_digest=chain["digest"],
        now=NOW,
    )
    later = NOW + timedelta(hours=2)
    with pytest.raises(CoCreationPreviewRejected) as error:
        engine.get_sandbox(
            sandbox_id=runtime.sandbox_id,
            tenant_id=chain["tenant_id"],
            principal_id=chain["principal_id"],
            platform_id=chain["platform_id"],
            payment_entitlement_digest=chain["digest"],
            now=later,
        )
    assert error.value.code == "SANDBOX_EXPIRED"


def test_feedback_loop_creates_revision_proposal(tmp_path):
    _write_policies(tmp_path)
    _seed_experience(tmp_path)
    chain = _seed_preview_ready_chain(tmp_path)
    engine = CoCreationPreviewEngine(foundry_root=tmp_path)
    runtime = engine.start_preview(
        proposal_id=chain["proposal_id"],
        tenant_id=chain["tenant_id"],
        principal_id=chain["principal_id"],
        platform_id=chain["platform_id"],
        preview_base_url=PREVIEW_BASE,
        payment_entitlement_digest=chain["digest"],
        now=NOW,
    )
    updated, revision_id, _loop = engine.submit_feedback(
        sandbox_id=runtime.sandbox_id,
        tenant_id=chain["tenant_id"],
        principal_id=chain["principal_id"],
        platform_id=chain["platform_id"],
        message="hero CTA를 더 크게, 마이페이지 dashboard 추가",
        payment_entitlement_digest=chain["digest"],
        now=NOW,
    )
    assert updated.status.value == "FEEDBACK_LOOP"
    assert revision_id
    assert (tmp_path / "state" / "co-creation" / "proposals" / f"{revision_id}.json").is_file()
