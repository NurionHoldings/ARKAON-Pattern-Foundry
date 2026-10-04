import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest

from apf.co_creation_codegen import CoCreationCodegenEngine, CoCreationCodegenRejected
from apf.co_creation_codegen_bridge import bridge_codegen_manifest

NOW = datetime(2031, 9, 1, tzinfo=UTC)
APPROVAL = "a" * 64


def _seed_proposal_and_scaffold(tmp_path: Path, *, purpose: str = "hero capture") -> str:
    proposal_id = sha256(b"proposal-seed").hexdigest()[:24]
    proposal = {
        "schema_version": "apf.co-creation-proposal/v1",
        "proposal_id": proposal_id,
        "tenant_id": str(uuid4()),
        "principal_id": str(uuid4()),
        "platform_id": "NARANG_RIDER",
        "review_status": "PROPOSED",
        "template_blueprint": [
            {
                "section_id": "hero",
                "purpose": purpose,
                "pattern_token": "landing-pattern:hero-single-cta",
                "cta_slot": True,
            }
        ],
        "platform_blueprint": [
            {"route_ref": "flow/step-e-contract", "purpose": "e-contract funnel"},
        ],
    }
    proposal_root = tmp_path / "state" / "co-creation" / "proposals"
    proposal_root.mkdir(parents=True)
    (proposal_root / f"{proposal_id}.json").write_text(json.dumps(proposal), encoding="utf-8")

    scaffold = {
        "schema_version": "apf.co-creation-template-scaffold/v1",
        "proposal_id": proposal_id,
        "platform_id": "NARANG_RIDER",
        "sections": [
            {
                "section_id": "hero",
                "purpose": purpose,
                "pattern_token": "landing-pattern:hero-single-cta",
                "codegen_status": "PENDING_REVIEW",
            }
        ],
        "surfaces": [{"route_ref": "flow/step-e-contract", "purpose": "e-contract funnel"}],
        "reference_style_bundle": {"style_tags": ["single-primary-cta", "compact-rhythm"]},
    }
    scaffold_root = tmp_path / "state" / "co-creation" / "scaffolds"
    scaffold_root.mkdir(parents=True)
    (scaffold_root / f"{proposal_id}-scaffold01.json").write_text(json.dumps(scaffold), encoding="utf-8")
    return proposal_id


def _write_codegen_policy(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "arkaon-co-creation-codegen.json").write_text(
        json.dumps({"schema_version": "apf.co-creation-codegen/v1"}),
        encoding="utf-8",
    )


def test_run_codegen_generates_variant_tree(tmp_path):
    _write_codegen_policy(tmp_path)
    proposal_id = _seed_proposal_and_scaffold(tmp_path)
    engine = CoCreationCodegenEngine(foundry_root=tmp_path)
    manifest = engine.run_codegen(
        proposal_id=proposal_id,
        operator_approval_digest=APPROVAL,
        now=NOW,
    )
    assert manifest.codegen_status == "GENERATED"
    assert manifest.files
    output = tmp_path / "state" / "co-creation" / "codegen" / proposal_id
    assert (output / "sections" / "hero.html").is_file()
    assert (output / "routes.json").is_file()
    assert (output / "manifest.json").is_file()
    hero = (output / "sections" / "hero.html").read_text(encoding="utf-8")
    assert "landing-pattern:hero-single-cta" in hero
    assert "single-primary-cta" in hero


def test_run_codegen_rejects_missing_scaffold(tmp_path):
    _write_codegen_policy(tmp_path)
    proposal_id = _seed_proposal_and_scaffold(tmp_path)
    for path in (tmp_path / "state" / "co-creation" / "scaffolds").glob("*.json"):
        path.unlink()
    engine = CoCreationCodegenEngine(foundry_root=tmp_path)
    with pytest.raises(CoCreationCodegenRejected) as error:
        engine.run_codegen(
            proposal_id=proposal_id,
            operator_approval_digest=APPROVAL,
            now=NOW,
        )
    assert error.value.code == "SCAFFOLD_MISSING"


def test_run_codegen_blocks_contamination(tmp_path):
    _write_codegen_policy(tmp_path)
    proposal_id = _seed_proposal_and_scaffold(tmp_path, purpose="api_key=supersecretvalue123")
    engine = CoCreationCodegenEngine(foundry_root=tmp_path)
    with pytest.raises(CoCreationCodegenRejected) as error:
        engine.run_codegen(
            proposal_id=proposal_id,
            operator_approval_digest=APPROVAL,
            now=NOW,
        )
    assert error.value.code == "CONTAMINATION_BLOCKED"


def test_approve_codegen_moves_to_preview_ready(tmp_path):
    _write_codegen_policy(tmp_path)
    proposal_id = _seed_proposal_and_scaffold(tmp_path)
    engine = CoCreationCodegenEngine(foundry_root=tmp_path)
    engine.run_codegen(
        proposal_id=proposal_id,
        operator_approval_digest=APPROVAL,
        now=NOW,
    )
    approved = engine.approve_codegen(
        proposal_id=proposal_id,
        operator_codegen_approval_digest="b" * 64,
        now=NOW,
    )
    assert approved.codegen_status == "PREVIEW_READY"


def test_bridge_codegen_emits_operator_packet(tmp_path):
    _write_codegen_policy(tmp_path)
    proposal_id = _seed_proposal_and_scaffold(tmp_path)
    engine = CoCreationCodegenEngine(foundry_root=tmp_path)
    manifest = engine.run_codegen(
        proposal_id=proposal_id,
        operator_approval_digest=APPROVAL,
        now=NOW,
    )
    paths = bridge_codegen_manifest(
        foundry_root=tmp_path,
        manifest=manifest,
        policy=engine.policy,
        run_id="run-codegen",
        now=NOW,
        dry_run=False,
    )
    packet = json.loads(Path(paths[0]).read_text(encoding="utf-8"))
    assert packet["packet_kind"] == "CO_CREATION_CODEGEN_REVIEW"
    assert packet["manifest_digest"] == manifest.manifest_digest


from apf.entry_effect_presets import PRESETS


@pytest.mark.parametrize('effect_id', PRESETS)
def test_codegen_effect_pages_with_configuration(tmp_path, effect_id):
    proposal_id = _seed_proposal_and_scaffold(tmp_path)
    scaffold_path = next((tmp_path / 'state/co-creation/scaffolds').glob('*.json'))
    scaffold = json.loads(scaffold_path.read_text())
    scaffold['sections'][0]['pattern_token'] = 'entry-effect:' + effect_id
    scaffold['sections'][0]['entry_effect'] = {
        'title': '더 아리랑 스토어', 'subtitle': 'THE ARIRANG STORE',
        'accent': '#ffaabb', 'duration': 2,
    }
    scaffold_path.write_text(json.dumps(scaffold))
    manifest = CoCreationCodegenEngine(foundry_root=tmp_path).run_codegen(
        proposal_id=proposal_id, operator_approval_digest=APPROVAL, now=NOW)
    page = (tmp_path / manifest.output_root / 'sections/hero.html').read_text()
    assert f'data-effect="{effect_id}"' in page
    assert '--apf-accent:#ffaabb' in page
    assert '--apf-duration:2s' in page


def test_codegen_rejects_unknown_effect_before_writing_files(tmp_path):
    proposal_id = _seed_proposal_and_scaffold(tmp_path)
    scaffold_path = next((tmp_path / 'state/co-creation/scaffolds').glob('*.json'))
    scaffold = json.loads(scaffold_path.read_text())
    scaffold['sections'][0]['pattern_token'] = 'entry-effect:missing'
    scaffold_path.write_text(json.dumps(scaffold))
    with pytest.raises(CoCreationCodegenRejected, match='Unknown entry effect'):
        CoCreationCodegenEngine(foundry_root=tmp_path).run_codegen(
            proposal_id=proposal_id, operator_approval_digest=APPROVAL, now=NOW)
    assert not (tmp_path / 'state/co-creation/codegen' / proposal_id).exists()


def test_codegen_applies_text_effects_and_font_selection(tmp_path):
    proposal_id = _seed_proposal_and_scaffold(tmp_path)
    path = next((tmp_path/'state/co-creation/scaffolds').glob('*.json'))
    scaffold = json.loads(path.read_text())
    scaffold['sections'][0]['pattern_token'] = 'entry-effect:arkaon-cinematic-gate'
    scaffold['sections'][0]['entry_effect'] = {
        'font':'serif', 'font_family':'Pretendard',
        'text_segments':[{'text':'아리랑', 'glow':'shine', 'exit':'fade-out'}],
    }
    path.write_text(json.dumps(scaffold))
    manifest = CoCreationCodegenEngine(foundry_root=tmp_path).run_codegen(
        proposal_id=proposal_id, operator_approval_digest=APPROVAL, now=NOW)
    page = (tmp_path/manifest.output_root/'sections/hero.html').read_text()
    assert 'Pretendard' in page and 'data-glow="shine"' in page
    assert 'apf-custom-title' in page
