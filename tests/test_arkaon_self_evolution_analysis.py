import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest

from apf.arkaon_self_evolution_analysis import ArkaonSelfEvolutionAnalysisEngine
from apf.arkaon_self_evolution_compare import (
    ArkaonSelfEvolutionCompareEngine,
    ImprovementContributor,
)
from apf.arkaon_user_feature_proposal import (
    ArkaonUserFeatureProposalEngine,
    UserFeatureProposalRejected,
)

NOW = datetime(2031, 9, 1, 12, 0, tzinfo=UTC)
LATER = datetime(2031, 9, 2, 12, 0, tzinfo=UTC)


def _write_configs(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "arkaon-self-evolution-compare.json").write_text(
        json.dumps({"schema_version": "apf.self-evolution-compare/v1"}),
        encoding="utf-8",
    )
    (config / "arkaon-user-feature-proposal.json").write_text(
        json.dumps({"schema_version": "apf.user-feature-proposal/v1"}),
        encoding="utf-8",
    )
    (config / "arkaon-billing-entitlement.json").write_text(
        json.dumps({"schema_version": "apf.billing-entitlement/v1", "mode": "DIGEST"}),
        encoding="utf-8",
    )
    intents = tmp_path / "knowledge" / "feature-intents"
    intents.mkdir(parents=True)
    (intents / "conversational-co-creation.json").write_text(
        json.dumps(
            {
                "schema_version": "apf.feature-intent-seed/v1",
                "feature_id": "conversational-co-creation",
                "intent_summary": "Paid tenant chat co-creation.",
            }
        ),
        encoding="utf-8",
    )
    apf = tmp_path / "src" / "apf"
    apf.mkdir(parents=True)
    (apf / "conversational_co_creation.py").write_text("# chat\n", encoding="utf-8")


def test_analyze_improvement_process_and_added_features(tmp_path):
    _write_configs(tmp_path)
    compare = ArkaonSelfEvolutionCompareEngine(foundry_root=tmp_path)
    before = compare.capture_snapshot(
        contributor=ImprovementContributor.BEOM,
        improvement_ref="w0",
        improvement_summary="initial co-creation only",
        now=NOW,
    )
    (tmp_path / "src" / "apf" / "co_creation_preview.py").write_text("# preview\n", encoding="utf-8")
    after = compare.capture_snapshot(
        contributor=ImprovementContributor.ETERNIAN,
        improvement_ref="w2",
        improvement_summary="preview sandbox added after eternian audit",
        now=LATER,
    )
    analysis_engine = ArkaonSelfEvolutionAnalysisEngine(foundry_root=tmp_path)
    analysis = analysis_engine.analyze(
        baseline_snapshot_id=before.snapshot_id,
        candidate_snapshot_id=after.snapshot_id,
        now=LATER,
    )
    assert analysis.process_steps
    assert "BEOM" in analysis.process_narrative
    assert "ETERNIAN" in analysis.process_narrative
    assert any(item.feature_id == "co_creation_preview" for item in analysis.added_features)


def test_propose_features_to_user(tmp_path):
    _write_configs(tmp_path)
    compare = ArkaonSelfEvolutionCompareEngine(foundry_root=tmp_path)
    compare.capture_snapshot(
        contributor=ImprovementContributor.BEOM,
        improvement_ref="w0",
        improvement_summary="baseline",
        now=NOW,
    )
    compare.capture_snapshot(
        contributor=ImprovementContributor.BEOM,
        improvement_ref="w1",
        improvement_summary="added chat",
        now=LATER,
    )
    tenant = str(uuid4())
    principal = str(uuid4())
    platform = "NARANG_RIDER"
    digest = sha256(f"{tenant}|{principal}|{platform}|paid".encode()).hexdigest()
    proposal_engine = ArkaonUserFeatureProposalEngine(foundry_root=tmp_path)
    proposal = proposal_engine.propose_to_user(
        tenant_id=tenant,
        principal_id=principal,
        platform_id=platform,
        payment_entitlement_digest=digest,
        now=LATER,
    )
    assert proposal.assistant_pitch
    assert proposal.feature_offers or proposal.process_narrative
    assert (tmp_path / "state" / "self-evolution" / "user-proposals" / f"{proposal.proposal_id}.json").is_file()


def test_propose_rejects_without_entitlement(tmp_path):
    _write_configs(tmp_path)
    compare = ArkaonSelfEvolutionCompareEngine(foundry_root=tmp_path)
    compare.capture_snapshot(
        contributor=ImprovementContributor.BEOM,
        improvement_ref="a",
        improvement_summary="a",
        now=NOW,
    )
    compare.capture_snapshot(
        contributor=ImprovementContributor.BEOM,
        improvement_ref="b",
        improvement_summary="b",
        now=LATER,
    )
    engine = ArkaonUserFeatureProposalEngine(foundry_root=tmp_path)
    with pytest.raises(UserFeatureProposalRejected) as error:
        engine.propose_to_user(
            tenant_id=str(uuid4()),
            principal_id=str(uuid4()),
            platform_id="NARANG_RIDER",
            payment_entitlement_digest="f" * 64,
            now=LATER,
        )
    assert error.value.code == "ENTITLEMENT_INACTIVE"
