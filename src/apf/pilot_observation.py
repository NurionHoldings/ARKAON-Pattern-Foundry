from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .benchmark_campaign import CampaignPhase, EvidenceBenchmarkCampaign, TrialEvidence
from .development_orchestrator import TaskStatus
from .learning_safety import require_safe_learning_payload
from .role_benchmark import BenchmarkReport, BenchmarkRole, BenchmarkThresholds
from .worker_runtime import ExecutionReceipt

_SAFE_ID = re.compile(r"\A[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}\Z")
_GENESIS_HASH = "0" * 64
_BUNDLE_SCHEMA = "apf.pilot-observation-bundle/v1"
_HEX_64 = re.compile(r"\A[0-9a-f]{64}\Z")


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


@dataclass(frozen=True)
class PilotBundleVerificationResult:
    """Read-only result; verification never creates or mutates a live ledger."""

    schema_version: str
    evidence_class: EvidenceClass
    entry_count: int
    head_hash: str
    bundle_hash: str
    signer_key_id: str
    entry_key_ids: tuple[str, ...]


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

    def sign_bundle_manifest(self, manifest: bytes) -> str:
        """Sign only a domain-separated canonical pilot bundle manifest."""

        return self._key.sign(b"APF:PILOT_BUNDLE:V1\x00" + manifest).hex()


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


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _entry_document(entry: PilotLedgerEntry) -> dict[str, Any]:
    draft = entry.draft
    return {
        "sequence": entry.sequence,
        "evidence_class": entry.evidence_class.value,
        "observer_id": entry.observer_id,
        "observer_key_id": entry.observer_key_id,
        "event_id": str(draft.event_id),
        "trial_id": draft.trial_id,
        "scenario_id": draft.scenario_id,
        "phase": draft.phase.value,
        "role": draft.role.value,
        "kind": draft.kind.value,
        "observed_at": draft.observed_at.isoformat(),
        "receipt": _receipt_payload(draft.receipt),
        "intent_alignment": draft.intent_alignment,
        "evidence_refs": list(draft.evidence_refs),
        "previous_hash": entry.previous_hash,
        "entry_hash": entry.entry_hash,
        "observer_signature": entry.observer_signature,
    }


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

    def export_bundle(self, observer: EthernianObserver) -> bytes:
        """Export a canonical, manifest-signed snapshot without private key material."""

        self.verify_integrity()
        if observer.key_id not in self._trusted_observer_keys:
            raise ValueError("UNTRUSTED_BUNDLE_SIGNER")
        entries = [_entry_document(entry) for entry in self._entries]
        manifest = {
            "schema_version": _BUNDLE_SCHEMA,
            "evidence_class": EvidenceClass.PILOT_OBSERVATION.value,
            "entry_count": len(entries),
            "head_hash": entries[-1]["entry_hash"] if entries else _GENESIS_HASH,
            "entries": entries,
            "signer_key_id": observer.key_id,
        }
        manifest_bytes = _canonical_json(manifest)
        document = {
            **manifest,
            "bundle_hash": hashlib.sha256(manifest_bytes).hexdigest(),
            "bundle_signature": observer.sign_bundle_manifest(manifest_bytes),
        }
        return _canonical_json(document)

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


_BUNDLE_FIELDS = {
    "schema_version",
    "evidence_class",
    "entry_count",
    "head_hash",
    "entries",
    "signer_key_id",
    "bundle_hash",
    "bundle_signature",
}
_ENTRY_FIELDS = {
    "sequence",
    "evidence_class",
    "observer_id",
    "observer_key_id",
    "event_id",
    "trial_id",
    "scenario_id",
    "phase",
    "role",
    "kind",
    "observed_at",
    "receipt",
    "intent_alignment",
    "evidence_refs",
    "previous_hash",
    "entry_hash",
    "observer_signature",
}
_RECEIPT_FIELDS = {
    "task_id",
    "worker_id",
    "intent_fingerprint",
    "status",
    "touched_paths",
    "checks",
    "failure_code",
}


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_JSON_FIELD")
        result[key] = value
    return result


def _require_fields(value: Any, fields: set[str], error: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(error)
    return value


def _parse_receipt(value: Any) -> ExecutionReceipt | None:
    if value is None:
        return None
    item = _require_fields(value, _RECEIPT_FIELDS, "INVALID_RECEIPT_SCHEMA")
    if (
        not isinstance(item["task_id"], str)
        or not isinstance(item["worker_id"], str)
        or not isinstance(item["intent_fingerprint"], str)
        or not isinstance(item["status"], str)
        or not isinstance(item["touched_paths"], list)
        or not all(isinstance(path, str) for path in item["touched_paths"])
        or not isinstance(item["checks"], list)
        or not all(isinstance(check, str) for check in item["checks"])
        or (item["failure_code"] is not None and not isinstance(item["failure_code"], str))
    ):
        raise ValueError("INVALID_RECEIPT_SCHEMA")
    return ExecutionReceipt(
        task_id=UUID(item["task_id"]),
        worker_id=item["worker_id"],
        intent_fingerprint=item["intent_fingerprint"],
        status=TaskStatus(item["status"]),
        touched_paths=tuple(item["touched_paths"]),
        checks=tuple(item["checks"]),
        failure_code=item["failure_code"],
    )


def verify_pilot_observation_bundle(
    bundle: bytes, *, trusted_observer_keys: dict[str, bytes]
) -> PilotBundleVerificationResult:
    """Independently verify an exported bundle and return facts, never a live ledger."""

    try:
        document = json.loads(bundle, object_pairs_hook=_strict_object)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("INVALID_CANONICAL_JSON") from exc
    root = _require_fields(document, _BUNDLE_FIELDS, "INVALID_BUNDLE_SCHEMA")
    if _canonical_json(root) != bundle:
        raise ValueError("NON_CANONICAL_JSON")
    if (
        root["schema_version"] != _BUNDLE_SCHEMA
        or root["evidence_class"] != EvidenceClass.PILOT_OBSERVATION.value
        or type(root["entry_count"]) is not int
        or root["entry_count"] < 0
        or not isinstance(root["head_hash"], str)
        or _HEX_64.fullmatch(root["head_hash"]) is None
        or not isinstance(root["entries"], list)
        or not isinstance(root["signer_key_id"], str)
        or not isinstance(root["bundle_hash"], str)
        or _HEX_64.fullmatch(root["bundle_hash"]) is None
        or not isinstance(root["bundle_signature"], str)
    ):
        raise ValueError("INVALID_BUNDLE_SCHEMA")
    manifest = {key: root[key] for key in root if key not in {"bundle_hash", "bundle_signature"}}
    manifest_bytes = _canonical_json(manifest)
    if hashlib.sha256(manifest_bytes).hexdigest() != root["bundle_hash"]:
        raise ValueError("BUNDLE_TAMPERING_DETECTED")
    signer_key = trusted_observer_keys.get(root["signer_key_id"])
    if signer_key is None or len(signer_key) != 32:
        raise ValueError("UNTRUSTED_BUNDLE_SIGNER")
    try:
        Ed25519PublicKey.from_public_bytes(bytes(signer_key)).verify(
            bytes.fromhex(root["bundle_signature"]),
            b"APF:PILOT_BUNDLE:V1\x00" + manifest_bytes,
        )
    except (InvalidSignature, ValueError):
        raise ValueError("INVALID_BUNDLE_SIGNATURE") from None
    if root["entry_count"] != len(root["entries"]):
        raise ValueError("BUNDLE_TRUNCATED")

    previous_hash = _GENESIS_HASH
    previous_time: datetime | None = None
    event_ids: set[UUID] = set()
    receipt_ids: set[UUID] = set()
    entry_key_ids: list[str] = []
    for expected_sequence, raw_entry in enumerate(root["entries"], start=1):
        item = _require_fields(raw_entry, _ENTRY_FIELDS, "INVALID_ENTRY_SCHEMA")
        if (
            type(item["sequence"]) is not int
            or item["sequence"] != expected_sequence
            or item["evidence_class"] != EvidenceClass.PILOT_OBSERVATION.value
            or item["observer_id"] != "ETHERNIAN"
            or not isinstance(item["observer_key_id"], str)
            or not isinstance(item["event_id"], str)
            or not isinstance(item["trial_id"], str)
            or not isinstance(item["scenario_id"], str)
            or not isinstance(item["phase"], str)
            or not isinstance(item["role"], str)
            or not isinstance(item["kind"], str)
            or not isinstance(item["observed_at"], str)
            or (item["intent_alignment"] is not None and type(item["intent_alignment"]) is not float)
            or not isinstance(item["evidence_refs"], list)
            or not all(isinstance(ref, str) for ref in item["evidence_refs"])
            or item["previous_hash"] != previous_hash
            or not isinstance(item["entry_hash"], str)
            or _HEX_64.fullmatch(item["entry_hash"]) is None
            or not isinstance(item["observer_signature"], str)
        ):
            raise ValueError("INVALID_ENTRY_SCHEMA")
        observed_at = datetime.fromisoformat(item["observed_at"])
        if observed_at.isoformat() != item["observed_at"]:
            raise ValueError("NON_CANONICAL_TIMESTAMP")
        event_id = UUID(item["event_id"])
        if str(event_id) != item["event_id"] or event_id in event_ids:
            raise ValueError("DUPLICATE_OR_NONCANONICAL_EVENT_ID")
        receipt = _parse_receipt(item["receipt"])
        if receipt is not None and receipt.task_id in receipt_ids:
            raise ValueError("REUSED_EXECUTION_RECEIPT")
        draft = PilotObservationDraft(
            event_id=event_id,
            trial_id=item["trial_id"],
            scenario_id=item["scenario_id"],
            phase=CampaignPhase(item["phase"]),
            role=BenchmarkRole(item["role"]),
            kind=PilotEventKind(item["kind"]),
            observed_at=observed_at,
            receipt=receipt,
            intent_alignment=item["intent_alignment"],
            evidence_refs=tuple(item["evidence_refs"]),
        )
        payload = _canonical_payload(
            item["sequence"],
            EvidenceClass.PILOT_OBSERVATION,
            item["observer_id"],
            item["observer_key_id"],
            draft,
            item["previous_hash"],
        )
        entry_key = trusted_observer_keys.get(item["observer_key_id"])
        if entry_key is None or len(entry_key) != 32:
            raise ValueError("UNTRUSTED_OBSERVER")
        try:
            Ed25519PublicKey.from_public_bytes(bytes(entry_key)).verify(
                bytes.fromhex(item["observer_signature"]), payload
            )
        except (InvalidSignature, ValueError):
            raise ValueError("INVALID_OBSERVER_SIGNATURE") from None
        digest = hashlib.sha256(payload).hexdigest()
        if digest != item["entry_hash"]:
            raise ValueError("LEDGER_TAMPERING_DETECTED")
        if previous_time is not None and observed_at < previous_time:
            raise ValueError("OBSERVATION_TIME_REGRESSION")
        previous_hash = digest
        previous_time = observed_at
        event_ids.add(event_id)
        if receipt is not None:
            receipt_ids.add(receipt.task_id)
        entry_key_ids.append(item["observer_key_id"])
    if root["head_hash"] != previous_hash:
        raise ValueError("BUNDLE_TRUNCATED_OR_HEAD_MISMATCH")
    return PilotBundleVerificationResult(
        schema_version=root["schema_version"],
        evidence_class=EvidenceClass.PILOT_OBSERVATION,
        entry_count=root["entry_count"],
        head_hash=root["head_hash"],
        bundle_hash=root["bundle_hash"],
        signer_key_id=root["signer_key_id"],
        entry_key_ids=tuple(entry_key_ids),
    )
