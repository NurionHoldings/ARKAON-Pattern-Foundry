from datetime import UTC, datetime
from pathlib import Path

from apf.owned_platform_live_proof import OwnedPlatformLiveProofHarness, ProofStatus

ROOT = Path(__file__).parents[1]


def test_live_proof_skips_without_repo_paths():
    report = OwnedPlatformLiveProofHarness(foundry_root=ROOT).run(
        now=datetime(2031, 1, 1, tzinfo=UTC), dry_run=True
    )
    assert report.overall is ProofStatus.SKIP
    assert len(report.results) == 2


def test_live_proof_writes_report():
    harness = OwnedPlatformLiveProofHarness(foundry_root=ROOT)
    harness.run(now=datetime(2031, 1, 1, tzinfo=UTC), dry_run=False)
    assert list((ROOT / "state" / "owned-platform-live").glob("*.json"))
