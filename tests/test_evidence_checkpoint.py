from datetime import datetime,timedelta,timezone
import hashlib
import pytest
from apf.evidence_checkpoint import CHECKPOINT_STATUS,EvidenceCheckpointError,VerifiedEvidenceLedgerTip,checkpoint_evidence_ledger
NOW=datetime(2026,9,17,tzinfo=timezone.utc)
def h(v:bytes)->str:return hashlib.sha256(v).hexdigest()
def tip()->VerifiedEvidenceLedgerTip:return VerifiedEvidenceLedgerTip(1,h(b"tip"),h(b"report"),NOW,True)
def test_verified_tip_creates_nonpromoting_checkpoint():
    item=checkpoint_evidence_ledger(tip(),checkpointed_at=NOW)
    assert item.status==CHECKPOINT_STATUS
    assert item.value()["asset_promoted"] is False
    assert item.value()["mutation_authority"] is False
    assert item.value()["deployment_authority"] is False
def test_invalid_empty_or_unverified_tip_fails_closed():
    with pytest.raises(EvidenceCheckpointError):checkpoint_evidence_ledger(VerifiedEvidenceLedgerTip(0,h(b"tip"),h(b"report"),NOW,True),checkpointed_at=NOW)
    with pytest.raises(EvidenceCheckpointError):checkpoint_evidence_ledger(VerifiedEvidenceLedgerTip(1,h(b"tip"),h(b"report"),NOW,False),checkpointed_at=NOW)
def test_time_reversal_fails_closed():
    with pytest.raises(EvidenceCheckpointError):checkpoint_evidence_ledger(tip(),checkpointed_at=NOW-timedelta(seconds=1))
def test_checkpoint_tamper_is_detected():
    item=checkpoint_evidence_ledger(tip(),checkpointed_at=NOW);object.__setattr__(item,"status","PROMOTED")
    with pytest.raises(EvidenceCheckpointError):item.validate()
