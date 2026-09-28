"""Purpose selection, sandbox checkout, and gated implementation workflow."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class PurposePurchaseError(RuntimeError):
    pass


class FlowState(StrEnum):
    PURPOSE_CONFIRMED = "PURPOSE_CONFIRMED"
    CHECKOUT_OPEN = "CHECKOUT_OPEN"
    PAYMENT_RETRY_REQUIRED = "PAYMENT_RETRY_REQUIRED"
    IMPLEMENTATION_READY = "IMPLEMENTATION_READY"
    SANDBOX_IMPLEMENTING = "SANDBOX_IMPLEMENTING"
    ARKAON_VERIFYING = "ARKAON_VERIFYING"
    ARKAON_VERIFIED = "ARKAON_VERIFIED"
    ETERNIAN_AUDITING = "ETERNIAN_AUDITING"
    ETERNIAN_REMEDIATING = "ETERNIAN_REMEDIATING"
    ETERNIAN_VERIFIED = "ETERNIAN_VERIFIED"
    CHANGE_REPORTED = "CHANGE_REPORTED"
    DEPLOYMENT_APPROVAL_PENDING = "DEPLOYMENT_APPROVAL_PENDING"
    HOLD_PAYMENT_REVERSED = "HOLD_PAYMENT_REVERSED"


class PaymentStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REVERSED = "REVERSED"


class PurposeSelection(BaseModel):
    product_code: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
    product_name: str = Field(min_length=1, max_length=200)
    purpose: str = Field(min_length=10, max_length=2000)
    amount_minor: int = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    allowed_paths: list[str] = Field(min_length=1, max_length=100)
    scope_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    owner_approval_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @field_validator("allowed_paths")
    @classmethod
    def validate_paths(cls, paths: list[str]) -> list[str]:
        for value in paths:
            path = PurePosixPath(value)
            if not value or "\\" in value or path.is_absolute() or ".." in path.parts:
                raise ValueError("safe repository-relative paths required")
        return paths


class RawPaymentEvent(BaseModel):
    event_id: str = Field(min_length=1, max_length=200)
    checkout_id: UUID
    checkout_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    provider_payment_id: str = Field(min_length=1, max_length=200)
    amount_minor: int = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    status: PaymentStatus
    occurred_at: datetime
    environment: str = Field(pattern=r"^SANDBOX$")


class VerifiedPayment(BaseModel):
    event: RawPaymentEvent
    verifier: str = Field(pattern=r"^PAYMENT_ADAPTER$")
    verification_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class PaymentVerifier(Protocol):
    def verify(self, event: RawPaymentEvent) -> VerifiedPayment: ...


_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_IMPLEMENTATION_TRANSITIONS = {
    FlowState.SANDBOX_IMPLEMENTING: (FlowState.ARKAON_VERIFYING, "ARKAON"),
    FlowState.ARKAON_VERIFYING: (FlowState.ARKAON_VERIFIED, "ARKAON"),
    FlowState.ARKAON_VERIFIED: (FlowState.ETERNIAN_AUDITING, "ETERNIAN"),
    FlowState.ETERNIAN_AUDITING: (FlowState.ETERNIAN_REMEDIATING, "ETERNIAN"),
    FlowState.ETERNIAN_REMEDIATING: (FlowState.ETERNIAN_VERIFIED, "ETERNIAN"),
    FlowState.ETERNIAN_VERIFIED: (FlowState.CHANGE_REPORTED, "ETERNIAN"),
    FlowState.CHANGE_REPORTED: (FlowState.DEPLOYMENT_APPROVAL_PENDING, "ETERNIAN"),
}


def digest(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    return "sha256:" + sha256(encoded).hexdigest()


class PurposePurchaseStore:
    def __init__(
        self, root: Path, verifier: PaymentVerifier, *, checkout_ttl_seconds: int = 900,
    ) -> None:
        if checkout_ttl_seconds < 0:
            raise ValueError("checkout_ttl_seconds must not be negative")
        self.root = root.resolve()
        self.verifier = verifier
        self.checkout_ttl_seconds = checkout_ttl_seconds

    def create(
        self, *, tenant_id: UUID, owner_principal_id: UUID, selection: PurposeSelection,
    ) -> dict[str, object]:
        order_id = str(uuid4())
        selected = selection.model_dump(mode="json")
        document: dict[str, object] = {
            "schema_version": "apf.purpose-purchase-flow/1.0",
            "order_id": order_id,
            "tenant_id": str(tenant_id),
            "owner_principal_id": str(owner_principal_id),
            "state": FlowState.PURPOSE_CONFIRMED.value,
            "selection": selected,
            "selection_digest": digest(selected),
            "checkout_attempts": [],
            "payment_events": [],
            "implementation_events": [],
            "automatic_merge_allowed": False,
            "deployment_allowed": False,
        }
        document["flow_digest"] = digest(document)
        _exclusive_json(self._path(order_id), document)
        return document

    def open_checkout(
        self, order_id: str, *, tenant_id: UUID, owner_principal_id: UUID,
    ) -> dict[str, object]:
        document = self._owner_bound(order_id, tenant_id, owner_principal_id)
        if document["state"] not in {
            FlowState.PURPOSE_CONFIRMED.value, FlowState.PAYMENT_RETRY_REQUIRED.value,
        }:
            raise PurposePurchaseError("CHECKOUT_NOT_ALLOWED")
        selection = document["selection"]
        assert isinstance(selection, dict)
        opened_at = datetime.now(UTC)
        checkout = {
            "checkout_id": str(uuid4()),
            "attempt": len(document["checkout_attempts"]) + 1,
            "selection_digest": document["selection_digest"],
            "scope_digest": selection["scope_digest"],
            "amount_minor": selection["amount_minor"],
            "currency": selection["currency"],
            "environment": "SANDBOX",
            "opened_at": opened_at.isoformat(),
            "expires_at": (opened_at + timedelta(seconds=self.checkout_ttl_seconds)).isoformat(),
            "consumed": False,
        }
        checkout["checkout_digest"] = digest(checkout)
        document["checkout_attempts"] = [*document["checkout_attempts"], checkout]
        document["state"] = FlowState.CHECKOUT_OPEN.value
        self._rewrite(document)
        return checkout

    def record_payment(
        self, order_id: str, *, tenant_id: UUID, event: RawPaymentEvent,
    ) -> dict[str, object]:
        document = self._bound(order_id, tenant_id)
        verified = self.verifier.verify(event)
        if verified.event != event:
            raise PurposePurchaseError("PAYMENT_VERIFIER_EVENT_MISMATCH")
        prior = next(
            (item for item in document["payment_events"] if item["event_id"] == event.event_id),
            None,
        )
        if prior is not None:
            if prior["event_digest"] != digest(event.model_dump(mode="json")):
                raise PurposePurchaseError("PAYMENT_EVENT_CONFLICT")
            return document
        checkout = _checkout(document, event.checkout_id)
        if event.checkout_digest != checkout["checkout_digest"]:
            raise PurposePurchaseError("PAYMENT_CHECKOUT_BINDING_MISMATCH")
        if event.amount_minor != checkout["amount_minor"] or event.currency != checkout["currency"]:
            raise PurposePurchaseError("PAYMENT_AMOUNT_OR_CURRENCY_MISMATCH")
        if event.occurred_at.tzinfo is None or event.occurred_at > datetime.now(UTC):
            raise PurposePurchaseError("PAYMENT_TIME_INVALID")
        if event.occurred_at > datetime.fromisoformat(str(checkout["expires_at"])):
            raise PurposePurchaseError("PAYMENT_CHECKOUT_EXPIRED")
        provider_events = [
            item for item in document["payment_events"]
            if item["provider_payment_id"] == event.provider_payment_id
        ]
        if provider_events and event.status != PaymentStatus.REVERSED:
            raise PurposePurchaseError("PAYMENT_PROVIDER_ID_REUSED")
        record = {
            **event.model_dump(mode="json"),
            "event_digest": digest(event.model_dump(mode="json")),
            "verification_digest": verified.verification_digest,
        }
        document["payment_events"] = [*document["payment_events"], record]
        if event.status == PaymentStatus.SUCCEEDED:
            if document["state"] != FlowState.CHECKOUT_OPEN.value or checkout["consumed"]:
                raise PurposePurchaseError("PAYMENT_SUCCESS_NOT_EXPECTED")
            checkout["consumed"] = True
            document["state"] = FlowState.IMPLEMENTATION_READY.value
            document["paid_receipt_digest"] = digest(record)
        elif event.status in {PaymentStatus.FAILED, PaymentStatus.CANCELLED}:
            if document["state"] != FlowState.CHECKOUT_OPEN.value:
                raise PurposePurchaseError("PAYMENT_FAILURE_NOT_EXPECTED")
            checkout["consumed"] = True
            document["state"] = FlowState.PAYMENT_RETRY_REQUIRED.value
        else:
            if not document.get("paid_receipt_digest"):
                raise PurposePurchaseError("PAYMENT_REVERSAL_WITHOUT_SUCCESS")
            if not any(
                item["provider_payment_id"] == event.provider_payment_id
                and item["status"] == PaymentStatus.SUCCEEDED.value
                for item in document["payment_events"][:-1]
            ):
                raise PurposePurchaseError("PAYMENT_REVERSAL_TARGET_MISMATCH")
            document["state"] = FlowState.HOLD_PAYMENT_REVERSED.value
        self._rewrite(document)
        return document

    def start_implementation(
        self, order_id: str, *, tenant_id: UUID, scope_digest: str,
    ) -> dict[str, object]:
        document = self._bound(order_id, tenant_id)
        selection = document["selection"]
        assert isinstance(selection, dict)
        if document["state"] != FlowState.IMPLEMENTATION_READY.value:
            raise PurposePurchaseError("VERIFIED_PAYMENT_REQUIRED")
        if scope_digest != selection["scope_digest"]:
            raise PurposePurchaseError("IMPLEMENTATION_SCOPE_MISMATCH")
        event = {
            "from_state": document["state"],
            "to_state": FlowState.SANDBOX_IMPLEMENTING.value,
            "actor_role": "ARKAON",
            "scope_digest": scope_digest,
            "payment_receipt_digest": document["paid_receipt_digest"],
            "occurred_at": datetime.now(UTC).isoformat(),
        }
        event["event_digest"] = digest(event)
        document["implementation_events"] = [*document["implementation_events"], event]
        document["state"] = FlowState.SANDBOX_IMPLEMENTING.value
        self._rewrite(document)
        return document

    def advance(
        self, order_id: str, *, tenant_id: UUID, actor_role: str,
        evidence_digest: str, skip_remediation: bool = False,
    ) -> dict[str, object]:
        document = self._bound(order_id, tenant_id)
        current = FlowState(document["state"])
        if current == FlowState.ETERNIAN_AUDITING and skip_remediation:
            target, required_role = FlowState.ETERNIAN_VERIFIED, "ETERNIAN"
        else:
            try:
                target, required_role = _IMPLEMENTATION_TRANSITIONS[current]
            except KeyError as exc:
                raise PurposePurchaseError("IMPLEMENTATION_TRANSITION_NOT_ALLOWED") from exc
        if actor_role != required_role:
            raise PurposePurchaseError("IMPLEMENTATION_ROLE_MISMATCH")
        if _DIGEST.fullmatch(evidence_digest) is None:
            raise PurposePurchaseError("IMPLEMENTATION_EVIDENCE_REQUIRED")
        event = {
            "from_state": current.value,
            "to_state": target.value,
            "actor_role": actor_role,
            "evidence_digest": evidence_digest,
            "occurred_at": datetime.now(UTC).isoformat(),
        }
        event["event_digest"] = digest(event)
        document["implementation_events"] = [*document["implementation_events"], event]
        document["state"] = target.value
        self._rewrite(document)
        return document

    def get(self, order_id: str, *, tenant_id: UUID) -> dict[str, object]:
        return self._bound(order_id, tenant_id)

    def _bound(self, order_id: str, tenant_id: UUID) -> dict[str, object]:
        document = _load(self._path(order_id))
        _validate(document)
        if document["tenant_id"] != str(tenant_id):
            raise PurposePurchaseError("PURPOSE_ORDER_NOT_FOUND")
        return document

    def _owner_bound(
        self, order_id: str, tenant_id: UUID, owner_principal_id: UUID,
    ) -> dict[str, object]:
        document = self._bound(order_id, tenant_id)
        if document["owner_principal_id"] != str(owner_principal_id):
            raise PurposePurchaseError("PURPOSE_ORDER_OWNER_MISMATCH")
        return document

    def _path(self, order_id: str) -> Path:
        try:
            UUID(order_id)
        except ValueError as exc:
            raise PurposePurchaseError("PURPOSE_ORDER_ID_INVALID") from exc
        return self.root / "state" / "purpose-purchase-flows" / f"{order_id}.json"

    def _rewrite(self, document: dict[str, object]) -> None:
        path = self._path(str(document["order_id"]))
        lock = path.with_suffix(path.suffix + ".lock")
        try:
            descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise PurposePurchaseError("PURPOSE_FLOW_BUSY") from exc
        try:
            expected = document["flow_digest"]
            current = _load(path)
            if current.get("flow_digest") != expected:
                raise PurposePurchaseError("PURPOSE_FLOW_CONCURRENT_UPDATE")
            document.pop("flow_digest", None)
            document["flow_digest"] = digest(document)
            _atomic_json(path, document)
        finally:
            os.close(descriptor)
            lock.unlink(missing_ok=True)


def _checkout(document: dict[str, object], checkout_id: UUID) -> dict[str, object]:
    for item in document["checkout_attempts"]:
        if item["checkout_id"] == str(checkout_id):
            if item is not document["checkout_attempts"][-1]:
                raise PurposePurchaseError("PAYMENT_STALE_CHECKOUT")
            return item
    raise PurposePurchaseError("PAYMENT_CHECKOUT_NOT_FOUND")


def _validate(document: dict[str, object]) -> None:
    supplied = document.get("flow_digest")
    unsigned = {key: value for key, value in document.items() if key != "flow_digest"}
    if (
        document.get("schema_version") != "apf.purpose-purchase-flow/1.0"
        or supplied != digest(unsigned)
        or document.get("automatic_merge_allowed") is not False
        or document.get("deployment_allowed") is not False
    ):
        raise PurposePurchaseError("PURPOSE_FLOW_TAMPERED")


def _load(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PurposePurchaseError("PURPOSE_ORDER_NOT_FOUND") from exc
    if not isinstance(value, dict):
        raise PurposePurchaseError("PURPOSE_FLOW_INVALID")
    return value


def _exclusive_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise PurposePurchaseError("PURPOSE_ORDER_CONFLICT") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _atomic_json(path: Path, value: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + f".{uuid4().hex}.tmp")
    try:
        _exclusive_json(temporary, value)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
