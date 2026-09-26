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
from apf.proposal_quality_score import (
    ProposalQualityRejected,
    ProposalQualityScorer,
    assert_proposal_quality_gate,
)

NOW = datetime(2031, 9, 1, tzinfo=UTC)


def _write_policy(tmp_path: Path) -> None:
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
                "replenish_enabled": False,
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


def _seed_two_patterns(tmp_path: Path) -> None:
    _seed_one_pattern(tmp_path)
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


def test_proposal_quality_score_weights(tmp_path):
    _seed_two_patterns(tmp_path)
    scorer = ProposalQualityScorer(foundry_root=tmp_path)
    report = scorer.evaluate(now=NOW)
    assert report.score >= 0.2
    assert report.gate_pass
    assert report.breakdown.landing_patterns == 2
    assert "더 나은 제안" in report.north_star


def test_gate_rejects_low_quality_with_single_pattern(tmp_path):
    _write_policy(tmp_path)
    _seed_one_pattern(tmp_path)
    with pytest.raises(ProposalQualityRejected) as error:
        assert_proposal_quality_gate(foundry_root=tmp_path, minimum_artifacts=1)
    assert error.value.code == "INSUFFICIENT_PROPOSAL_QUALITY"


def test_chat_records_proposal_quality_score(tmp_path):
    _write_policy(tmp_path)
    _seed_two_patterns(tmp_path)
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
    assert proposal.proposal_quality_score_at_intake is not None
    assert proposal.proposal_quality_score_at_intake >= 0.2


def test_chat_rejects_insufficient_proposal_quality(tmp_path):
    _write_policy(tmp_path)
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


def test_scorer_persists_latest(tmp_path):
    _seed_two_patterns(tmp_path)
    scorer = ProposalQualityScorer(foundry_root=tmp_path)
    scorer.evaluate_and_persist(now=NOW)
    assert (tmp_path / "state" / "proposal-quality" / "latest.json").is_file()
    loaded = scorer.load_latest()
    assert loaded is not None
    assert loaded.gate_pass
