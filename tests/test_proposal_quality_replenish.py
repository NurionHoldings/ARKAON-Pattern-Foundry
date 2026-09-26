import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest

from apf.conversational_co_creation import (
    CoCreationRejected,
    CoCreationScope,
    ConversationalCoCreationEngine,
)
from apf.proposal_quality_replenish import (
    ProposalQualityReplenishEngine,
    assets_insufficient_for_better_proposal,
    resolve_proposal_quality_with_replenish,
    user_dissatisfaction_detected,
)
from apf.proposal_quality_score import (
    ProposalQualityRejected,
    ProposalQualityScorer,
    assert_proposal_quality_gate,
)

NOW = datetime(2031, 9, 1, tzinfo=UTC)


def _write_policies(tmp_path: Path, *, replenish_enabled: bool = True) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "arkaon-conversational-co-creation.json").write_text(
        json.dumps({"schema_version": "apf.conversational-co-creation/v1"}),
        encoding="utf-8",
    )
    (config / "arkaon-proposal-quality.json").write_text(
        json.dumps(
            {
                "schema_version": "apf.proposal-quality/v1",
                "minimum_proposal_quality_score": 0.2,
                "replenish_enabled": replenish_enabled,
                "max_actions_per_replenish": 2,
            }
        ),
        encoding="utf-8",
    )


def _seed_one_pattern(tmp_path: Path) -> None:
    patterns = tmp_path / "knowledge" / "landing-structure-patterns" / "proposed"
    patterns.mkdir(parents=True)
    (patterns / "landing.cross-platform.hero-single-cta.json").write_text(
        json.dumps(
            {
                "schema_version": "apf.landing-structure-pattern-proposal/v1",
                "pattern_id": "landing.cross-platform.hero-single-cta",
                "pattern_token": "landing-pattern:hero-single-cta",
                "summary": "hero",
                "evidence_digests": ["a" * 64],
            }
        ),
        encoding="utf-8",
    )


def test_user_dissatisfaction_detected():
    assert user_dissatisfaction_detected("품질이 별로예요, 다시 제안해주세요")
    assert user_dissatisfaction_detected("not good, try again")
    assert not user_dissatisfaction_detected("hero landing please")


def test_gate_fail_triggers_replenish_and_passes(tmp_path):
    _write_policies(tmp_path)
    _seed_one_pattern(tmp_path)
    quality, replenish = resolve_proposal_quality_with_replenish(
        foundry_root=tmp_path,
        platform_id="NARANG_RIDER",
        message="hero landing template",
        minimum_artifacts=1,
        now=NOW,
    )
    assert replenish is not None
    assert replenish.trigger == "GATE_FAIL"
    assert quality.gate_pass
    assert replenish.after_score > replenish.before_score
    assert (tmp_path / "state" / "proposal-quality" / "replenish").is_dir()


def test_chat_replenishes_then_proposes(tmp_path):
    _write_policies(tmp_path)
    _seed_one_pattern(tmp_path)
    engine = ConversationalCoCreationEngine(foundry_root=tmp_path)
    tenant, principal = str(uuid4()), str(uuid4())
    platform = "NARANG_RIDER"
    digest = sha256(f"{tenant}|{principal}|{platform}|paid".encode()).hexdigest()
    proposal = engine.chat(
        tenant_id=tenant,
        principal_id=principal,
        platform_id=platform,
        message="hero landing template",
        scope=CoCreationScope.TEMPLATE,
        payment_entitlement_digest=digest,
        now=NOW,
    )
    assert proposal.proposal_quality_replenished
    assert proposal.proposal_quality_replenish_trigger == "GATE_FAIL"
    assert proposal.proposal_quality_score_at_intake >= 0.2
    assert "Supplemental analysis" in proposal.assistant_reply


def test_replenish_disabled_still_rejects_low_quality(tmp_path):
    _write_policies(tmp_path, replenish_enabled=False)
    _seed_one_pattern(tmp_path)
    engine = ConversationalCoCreationEngine(foundry_root=tmp_path)
    tenant, principal = str(uuid4()), str(uuid4())
    digest = sha256(f"{tenant}|{principal}|MJN|paid".encode()).hexdigest()
    with pytest.raises(CoCreationRejected) as error:
        engine.chat(
            tenant_id=tenant,
            principal_id=principal,
            platform_id="MJN",
            message="template please",
            scope=CoCreationScope.TEMPLATE,
            payment_entitlement_digest=digest,
            now=NOW,
        )
    assert error.value.code == "INSUFFICIENT_PROPOSAL_QUALITY"


def test_user_dissatisfaction_replenish_when_assets_thin(tmp_path):
    _write_policies(tmp_path)
    _seed_one_pattern(tmp_path)
    # Two patterns pass gate but score ~0.33 — user dissatisfaction should still replenish
    patterns = tmp_path / "knowledge" / "landing-structure-patterns" / "proposed"
    (patterns / "landing.cross-platform.e-contract-flow.json").write_text(
        json.dumps(
            {
                "schema_version": "apf.landing-structure-pattern-proposal/v1",
                "pattern_id": "landing.cross-platform.e-contract-flow",
                "pattern_token": "landing-pattern:e-contract-flow",
                "summary": "e-contract",
                "evidence_digests": ["b" * 64],
            }
        ),
        encoding="utf-8",
    )
    before = ProposalQualityScorer(foundry_root=tmp_path).evaluate(now=NOW)
    assert before.gate_pass
    assert assets_insufficient_for_better_proposal(
        before, minimum_score=0.2, score_ceiling=0.55
    )
    quality, replenish = resolve_proposal_quality_with_replenish(
        foundry_root=tmp_path,
        platform_id="NARANG_RIDER",
        message="품질이 아쉬워요, hero CTA를 더 크게",
        minimum_artifacts=1,
        now=NOW,
    )
    assert replenish is not None
    assert replenish.trigger == "USER_DISSATISFACTION"
    assert quality.gate_pass


def test_replenish_engine_list_recent(tmp_path):
    _write_policies(tmp_path)
    _seed_one_pattern(tmp_path)
    engine = ProposalQualityReplenishEngine(foundry_root=tmp_path)
    engine.replenish(
        platform_id="DEMO",
        message="hero",
        trigger="GATE_FAIL",
        now=NOW,
    )
    recent = engine.list_recent(limit=5)
    assert len(recent) == 1
    assert recent[0].trigger == "GATE_FAIL"


def test_experience_gate_not_bypassed_by_replenish(tmp_path):
    _write_policies(tmp_path, replenish_enabled=True)
    with pytest.raises(ProposalQualityRejected) as error:
        resolve_proposal_quality_with_replenish(
            foundry_root=tmp_path,
            platform_id="DEMO",
            message="hero landing",
            minimum_artifacts=1,
            now=NOW,
        )
    assert error.value.code == "INSUFFICIENT_EXPERIENCE"


def test_assert_gate_still_raises_without_replenish_path(tmp_path):
    _write_policies(tmp_path, replenish_enabled=False)
    _seed_one_pattern(tmp_path)
    with pytest.raises(ProposalQualityRejected):
        assert_proposal_quality_gate(foundry_root=tmp_path, minimum_artifacts=1)
