"""Incubating, non-promoting checkpoint for a verified evidence-ledger tip."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

CHECKPOINT_STATUS = "ETHERNIAN_REVIEW_REQUIRED"

class EvidenceCheckpointError(ValueError):
    pass

def _digest(value:object)->str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

def _valid(value:object)->bool:
    return isinstance(value,str) and len(value)==64 and all(c in "0123456789abcdef" for c in value)

@dataclass(frozen=True)
class VerifiedEvidenceLedgerTip:
    record_count:int
    tip_digest:str
    report_digest:str
    last_recorded_at:datetime
    chain_valid:bool
    def validate(self)->None:
        if (self.record_count<=0 or not _valid(self.tip_digest) or not _valid(self.report_digest)
            or self.last_recorded_at.tzinfo is None or self.chain_valid is not True):
            raise EvidenceCheckpointError("VERIFIED_NONEMPTY_LEDGER_TIP_REQUIRED")

@dataclass(frozen=True)
class EvidenceLedgerCheckpoint:
    record_count:int
    tip_digest:str
    report_digest:str
    checkpointed_at:datetime
    status:str
    checkpoint_digest:str
    def value(self)->dict[str,object]:
        return {"record_count":self.record_count,"tip_digest":self.tip_digest,"report_digest":self.report_digest,
            "checkpointed_at":self.checkpointed_at.isoformat(),"status":self.status,"asset_promoted":False,
            "mutation_authority":False,"deployment_authority":False}
    def validate(self)->None:
        if (self.record_count<=0 or not _valid(self.tip_digest) or not _valid(self.report_digest)
            or self.checkpointed_at.tzinfo is None or self.status!=CHECKPOINT_STATUS
            or self.checkpoint_digest!=_digest(self.value())):
            raise EvidenceCheckpointError("INTACT_NONPROMOTING_CHECKPOINT_REQUIRED")

def checkpoint_evidence_ledger(tip:VerifiedEvidenceLedgerTip,*,checkpointed_at:datetime)->EvidenceLedgerCheckpoint:
    if not isinstance(tip,VerifiedEvidenceLedgerTip):raise EvidenceCheckpointError("TYPED_LEDGER_TIP_REQUIRED")
    tip.validate()
    if checkpointed_at.tzinfo is None or checkpointed_at<tip.last_recorded_at:
        raise EvidenceCheckpointError("CHRONOLOGICAL_CHECKPOINT_REQUIRED")
    value={"record_count":tip.record_count,"tip_digest":tip.tip_digest,"report_digest":tip.report_digest,
        "checkpointed_at":checkpointed_at.isoformat(),"status":CHECKPOINT_STATUS,"asset_promoted":False,
        "mutation_authority":False,"deployment_authority":False}
    item=EvidenceLedgerCheckpoint(tip.record_count,tip.tip_digest,tip.report_digest,checkpointed_at,CHECKPOINT_STATUS,_digest(value))
    item.validate();return item
