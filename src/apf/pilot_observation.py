from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .benchmark_campaign import CampaignPhase, EvidenceBenchmarkCampaign, TrialEvidence
from .learning_safety import require_safe_learning_payload
from .role_benchmark import BenchmarkReport, BenchmarkRole, BenchmarkThresholds
from .worker_runtime import ExecutionReceipt

_SAFE_ID = re.compile(r"\A[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}\Z")
_GENESIS_HASH = "0" * 64


class EvidenceClass(StrEnum):
    SYNTHETIC_PIPELINE_ONLY = "SYNTHETIC_PIPELINE_ONLY"
    PILOT_OBSERVATION = "PILOT_OBSERVATION"


class PilotEventKind(StrEnum):
    START = "START"
    REWORK = "REWORK"
    INTERVENTION = "INTERVENTION"
    FINISH = "FINISH"


@dataclass(frozen=True)
class PilotObservationDraft:
    event_id: UUID
    trial_id: str
    scenario_id: str
    phase: CampaignPhase
    role: BenchmarkRole
    kind: PilotEventKind
    observed_at: datetime
    receipt: ExecutionReceipt | None = None
    intent_alignment: float | None = None
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _SAFE_ID.fullmatch(self.trial_id) or not _SAFE_ID.fullmatch(self.scenario_id):
            raise ValueError("OPAQUE_TRIAL_IDENTIFIERS_REQUIRED")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("TIMEZONE_AWARE_TIMESTAMP_REQUIRED")
        require_safe_learning_payload(
            {"trial_id": self.trial_id, "scenario_id": self.scenario_id},
            self.evidence_refs,
        )
        if self.kind is PilotEventKind.FINISH:
            if self.receipt is None or not self.evidence_refs or self.intent_alignment is None:
                raise ValueError("FINISH_EVIDENCE_REQUIRED")
            if not 0.0 <= self.intent_alignment <= 1.0:
                raise ValueError("INTENT_ALIGNMENT_OUT_OF_RANGE")
            assert self.receipt is not None
            require_safe_learning_payload(
                {
                    "worker_id": self.receipt.worker_id,
                    "intent_fingerprint": self.receipt.intent_fingerprint,
                    "touched_paths": "\n".join(self.receipt.touched_paths),
                    "checks": "\n".join(self.receipt.checks),
                    "failure_code": self.receipt.failure_code,
                },
                self.evidence_refs,
            )
        elif self.receipt is not None or self.intent_alignment is not None or self.evidence_refs:
            raise ValueError("MEASUREMENT_FIELDS_FINISH_ONLY")


@dataclass(frozen=True)
class PilotLedgerEntry:
    sequence: int
    evidence_class: EvidenceClass
    observer_id: str
    observer_key_id: str
    draft: PilotObservationDraft
    previous_hash: str
    entry_hash: str
    observer_signature: str


@dataclass(frozen=True)
class PilotObservationChallenge:
    """Unsigned snapshot of the exact ledger position and observation to attest."""

    sequence: int
    evidence_class: EvidenceClass
    observer_id: str
    draft: PilotObservationDraft
    previous_hash: str


@dataclass(frozen=True)
class PilotObservationAttestation:
    """Immutable observer-signed envelope accepted by the untrusted ledger boundary."""

    challenge: PilotObservationChallenge
    observer_key_id: str
    observer_signature: str


class EthernianObserver:
    """Trusted signer kept outside the ledger and its callers."""

    def __init__(self, *, key_id: str, signing_key: bytes) -> None:
        if not _SAFE_ID.fullmatch(key_id) or len(signing_key) != 32:
            raise ValueError("VALID_OBSERVER_KEY_REQUIRED")
        self.key_id = key_id
        self._key = Ed25519PrivateKey.from_private_bytes(bytes(signing_key))

    @property
    def public_key(self) -> bytes:
        return self._key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    def attest(self, challenge: PilotObservationChallenge) -> PilotObservationAttestation:
        payload = _canonical_payload(
            challenge.sequence,
            challenge.evidence_class,
            challenge.observer_id,
            self.key_id,
            challenge.draft,
            challenge.previous_hash,
        )
        return PilotObservationAttestation(
            challenge=challenge,
            observer_key_id=self.key_id,
            observer_signature=self._key.sign(payload).hex(),
        )


def _receipt_payload(receipt: ExecutionReceipt | None) -> dict | None:
    if receipt is None:
        return None
    return {
        "task_id": str(receipt.task_id),
        "worker_id": receipt.worker_id,
        "intent_fingerprint": receipt.intent_fingerprint,
        "status": receipt.status.value,
        "touched_paths": receipt.touched_paths,
        "checks": receipt.checks,
        "failure_code": receipt.failure_code,
    }


def _canonical_payload(
    sequence: int,
    evidence_class: EvidenceClass,
    observer_id: str,
    observer_key_id: str,
    draft: PilotObservationDraft,
    previous_hash: str,
) -> bytes:
    value = {
        "sequence": sequence,
        "evidence_class": evidence_class.value,
        "observer_id": observer_id,
        "observer_key_id": observer_key_id,
        "event_id": str(draft.event_id),
        "trial_id": draft.trial_id,
        "scenario_id": draft.scenario_id,
        "phase": draft.phase.value,
        "role": draft.role.value,
        "kind": draft.kind.value,
        "observed_at": draft.observed_at.isoformat(),
        "receipt": _receipt_payload(draft.receipt),
        "intent_alignment": draft.intent_alignment,
        "evidence_refs": draft.evidence_refs,
        "previous_hash": previous_hash,
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


class PilotObservationLedger:
    """Append-only, observer-signed ledger for real-world pilot measurements."""

    def __init__(self, *, trusted_observer_keys: dict[str, bytes]) -> None:
        if not trusted_observer_keys:
            raise ValueError("TRUSTED_OBSERVER_KEY_REQUIRED")
        self._trusted_observer_keys = {
            key_id: Ed25519PublicKey.from_public_bytes(bytes(public_key))
            for key_id, public_key in trusted_observer_keys.items()
            if _SAFE_ID.fullmatch(key_id) and len(public_key) == 32
        }
        if len(self._trusted_observer_keys) != len(trusted_observer_keys):
            raise ValueError("VALID_OBSERVER_PUBLIC_KEY_REQUIRED")
        self._entries: list[PilotLedgerEntry] = []
        self._event_ids: set[UUID] = set()
        self._receipt_ids: set[UUID] = set()
        self._sealed = False

    @property
    def entries(self) -> tuple[PilotLedgerEntry, ...]:
        return tuple(self._entries)

    def challenge(self, draft: PilotObservationDraft) -> PilotObservationChallenge:
        if self._sealed:
            raise ValueError("LEDGER_ALREADY_SEALED")
        return PilotObservationChallenge(
            sequence=len(self._entries) + 1,
            evidence_class=EvidenceClass.PILOT_OBSERVATION,
            observer_id="ETHERNIAN",
            draft=draft,
            previous_hash=self._entries[-1].entry_hash if self._entries else _GENESIS_HASH,
        )

    def append(self, attestation: PilotObservationAttestation) -> PilotLedgerEntry:
        if self._sealed:
            raise ValueError("LEDGER_ALREADY_SEALED")
        challenge = attestation.challenge
        draft = challenge.draft
        expected_sequence = len(self._entries) + 1
        expected_previous_hash = self._entries[-1].entry_hash if self._entries else _GENESIS_HASH
        if (
            challenge.sequence != expected_sequence
            or challenge.previous_hash != expected_previous_hash
        ):
            raise ValueError("STALE_OR_OUT_OF_ORDER_CHALLENGE")
        if (
            challenge.evidence_class is not EvidenceClass.PILOT_OBSERVATION
            or challenge.observer_id != "ETHERNIAN"
        ):
            raise ValueError("INVALID_ATTESTATION_SCOPE")
        if draft.event_id in self._event_ids:
            raise ValueError("DUPLICATE_EVENT_ID")
        if self._entries and draft.observed_at < self._entries[-1].draft.observed_at:
            raise ValueError("OBSERVATION_TIME_REGRESSION")
        if draft.receipt is not None and draft.receipt.task_id in self._receipt_ids:
            raise ValueError("REUSED_EXECUTION_RECEIPT")
        payload = _canonical_payload(
            challenge.sequence,
            challenge.evidence_class,
            challenge.observer_id,
            attestation.observer_key_id,
            draft,
            challenge.previous_hash,
        )
        verifier = self._trusted_observer_keys.get(attestation.observer_key_id)
        if verifier is None:
            raise ValueError("UNTRUSTED_OBSERVER")
        try:
            verifier.verify(bytes.fromhex(attestation.observer_signature), payload)
        except (InvalidSignature, ValueError):
            raise ValueError("INVALID_OBSERVER_SIGNATURE") from None
        entry_hash = hashlib.sha256(payload).hexdigest()
        entry = PilotLedgerEntry(
            sequence=challenge.sequence,
            evidence_class=challenge.evidence_class,
            observer_id=challenge.observer_id,
            observer_key_id=attestation.observer_key_id,
            draft=draft,
            previous_hash=challenge.previous_hash,
            entry_hash=entry_hash,
            observer_signature=attestation.observer_signature,
        )
        self._entries.append(entry)
        self._event_ids.add(draft.event_id)
        if draft.receipt is not None:
            self._receipt_ids.add(draft.receipt.task_id)
        return entry

    def verify_integrity(self) -> None:
        previous_hash = _GENESIS_HASH
        previous_time: datetime | None = None
        event_ids: set[UUID] = set()
        receipt_ids: set[UUID] = set()
        for expected_sequence, entry in enumerate(self._entries, start=1):
            if entry.evidence_class is not EvidenceClass.PILOT_OBSERVATION:
                raise ValueError("INVALID_EVIDENCE_CLASS")
            if entry.sequence != expected_sequence or entry.previous_hash != previous_hash:
                raise ValueError("LEDGER_CHAIN_BROKEN")
            verifier = self._trusted_observer_keys.get(entry.observer_key_id)
            if entry.observer_id != "ETHERNIAN" or verifier is None:
                raise ValueError("UNTRUSTED_OBSERVER")
            if entry.draft.event_id in event_ids:
                raise ValueError("DUPLICATE_EVENT_ID")
            if previous_time is not None and entry.draft.observed_at < previous_time:
                raise ValueError("OBSERVATION_TIME_REGRESSION")
            receipt = entry.draft.receipt
            if receipt is not None and receipt.task_id in receipt_ids:
                raise ValueError("REUSED_EXECUTION_RECEIPT")
            payload = _canonical_payload(
                entry.sequence,
                entry.evidence_class,
                entry.observer_id,
                entry.observer_key_id,
                entry.draft,
                entry.previous_hash,
            )
            digest = hashlib.sha256(payload).hexdigest()
            try:
                verifier.verify(bytes.fromhex(entry.observer_signature), payload)
            except (InvalidSignature, ValueError):
                raise ValueError("LEDGER_TAMPERING_DETECTED") from None
            if digest != entry.entry_hash:
                raise ValueError("LEDGER_TAMPERING_DETECTED")
            previous_hash = entry.entry_hash
            previous_time = entry.draft.observed_at
            event_ids.add(entry.draft.event_id)
            if receipt is not None:
                receipt_ids.add(receipt.task_id)

    def to_campaign(self) -> EvidenceBenchmarkCampaign:
        self.verify_integrity()
        grouped: dict[str, list[PilotLedgerEntry]] = {}
        for entry in self._entries:
            grouped.setdefault(entry.draft.trial_id, []).append(entry)
        campaign = EvidenceBenchmarkCampaign()
        for entries in grouped.values():
            starts = [item for item in entries if item.draft.kind is PilotEventKind.START]
            finishes = [item for item in entries if item.draft.kind is PilotEventKind.FINISH]
            if len(starts) != 1 or len(finishes) != 1:
                raise ValueError("COMPLETE_TRIAL_BOUNDARY_REQUIRED")
            start, finish = starts[0], finishes[0]
            if entries[0] is not start or entries[-1] is not finish:
                raise ValueError("INVALID_TRIAL_EVENT_ORDER")
            identity = (start.draft.scenario_id, start.draft.phase, start.draft.role)
            if any(
                (item.draft.scenario_id, item.draft.phase, item.draft.role) != identity
                for item in entries
            ):
                raise ValueError("TRIAL_IDENTITY_CHANGED")
            assert finish.draft.receipt is not None
            assert finish.draft.intent_alignment is not None
            campaign.record(
                TrialEvidence(
                    scenario_id=start.draft.scenario_id,
                    phase=start.draft.phase,
                    role=start.draft.role,
                    receipt=finish.draft.receipt,
                    started_at=start.draft.observed_at,
                    finished_at=finish.draft.observed_at,
                    rework_count=sum(item.draft.kind is PilotEventKind.REWORK for item in entries),
                    ethernian_interventions=sum(
                        item.draft.kind is PilotEventKind.INTERVENTION for item in entries
                    ),
                    intent_alignment=finish.draft.intent_alignment,
                    evidence_refs=finish.draft.evidence_refs,
                )
            )
        return campaign

    def evaluate(self, *, thresholds: BenchmarkThresholds | None = None) -> BenchmarkReport:
        if self._sealed:
            raise ValueError("LEDGER_ALREADY_SEALED")
        campaign = self.to_campaign()
        report = campaign.evaluate(thresholds=thresholds)
        self._sealed = True
        return report
