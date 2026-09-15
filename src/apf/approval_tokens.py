from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from uuid import UUID, uuid4


class ApprovalTokenDenied(ValueError):
    """Raised when an approval token cannot authorize the requested operation."""


@dataclass(frozen=True)
class ApprovalTokenClaims:
    token_id: UUID
    task_id: str
    kind: str
    intent_fingerprint: str
    expected_result_fingerprint: str
    approver_id: UUID
    approver_role: str
    expires_at: datetime


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, UnicodeEncodeError) as exc:
        raise ApprovalTokenDenied("MALFORMED_APPROVAL_TOKEN") from exc


class ApprovalTokenService:
    """Issues and atomically consumes narrowly-bound human approval tokens."""

    def __init__(self, secret: bytes, *, human_roles: frozenset[str]) -> None:
        if len(secret) < 32:
            raise ValueError("APPROVAL_SECRET_TOO_SHORT")
        if not human_roles or any(not role.strip() for role in human_roles):
            raise ValueError("HUMAN_APPROVER_ROLES_REQUIRED")
        self._secret = secret
        self._human_roles = human_roles
        self._consumed: set[UUID] = set()
        self._lock = Lock()

    def issue(
        self,
        *,
        task_id: str,
        kind: str,
        intent_fingerprint: str,
        expected_result_fingerprint: str,
        approver_id: UUID,
        approver_role: str,
        expires_at: datetime,
        is_human: bool = True,
    ) -> str:
        if not is_human or approver_role not in self._human_roles:
            raise ApprovalTokenDenied("HUMAN_APPROVER_REQUIRED")
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            raise ApprovalTokenDenied("TIMEZONE_AWARE_EXPIRY_REQUIRED")
        if not all((task_id, kind, intent_fingerprint, expected_result_fingerprint)):
            raise ApprovalTokenDenied("APPROVAL_BINDINGS_REQUIRED")

        payload = {
            "approver_id": str(approver_id),
            "approver_role": approver_role,
            "expected_result_fingerprint": expected_result_fingerprint,
            "expires_at": int(expires_at.astimezone(UTC).timestamp()),
            "intent_fingerprint": intent_fingerprint,
            "kind": kind,
            "task_id": task_id,
            "token_id": str(uuid4()),
            "version": 1,
        }
        encoded_payload = _encode(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        signature = hmac.new(
            self._secret, encoded_payload.encode("ascii"), hashlib.sha256
        ).digest()
        return f"{encoded_payload}.{_encode(signature)}"

    def verify_and_consume(
        self,
        token: str,
        *,
        task_id: str,
        kind: str,
        intent_fingerprint: str,
        expected_result_fingerprint: str,
        now: datetime | None = None,
    ) -> ApprovalTokenClaims:
        try:
            encoded_payload, encoded_signature = token.split(".")
        except ValueError as exc:
            raise ApprovalTokenDenied("MALFORMED_APPROVAL_TOKEN") from exc

        supplied_signature = _decode(encoded_signature)
        expected_signature = hmac.new(
            self._secret, encoded_payload.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise ApprovalTokenDenied("INVALID_APPROVAL_SIGNATURE")

        try:
            payload = json.loads(_decode(encoded_payload))
            if payload["version"] != 1:
                raise ValueError
            claims = ApprovalTokenClaims(
                token_id=UUID(payload["token_id"]),
                task_id=payload["task_id"],
                kind=payload["kind"],
                intent_fingerprint=payload["intent_fingerprint"],
                expected_result_fingerprint=payload["expected_result_fingerprint"],
                approver_id=UUID(payload["approver_id"]),
                approver_role=payload["approver_role"],
                expires_at=datetime.fromtimestamp(payload["expires_at"], UTC),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ApprovalTokenDenied("MALFORMED_APPROVAL_TOKEN") from exc

        if claims.approver_role not in self._human_roles:
            raise ApprovalTokenDenied("HUMAN_APPROVER_REQUIRED")
        actual = (
            claims.task_id,
            claims.kind,
            claims.intent_fingerprint,
            claims.expected_result_fingerprint,
        )
        expected = (task_id, kind, intent_fingerprint, expected_result_fingerprint)
        if actual != expected:
            raise ApprovalTokenDenied("APPROVAL_BINDING_MISMATCH")

        checked_at = now or datetime.now(UTC)
        if checked_at.tzinfo is None or checked_at.utcoffset() is None:
            raise ApprovalTokenDenied("TIMEZONE_AWARE_VERIFICATION_REQUIRED")
        if checked_at.astimezone(UTC) >= claims.expires_at:
            raise ApprovalTokenDenied("APPROVAL_TOKEN_EXPIRED")

        with self._lock:
            if claims.token_id in self._consumed:
                raise ApprovalTokenDenied("APPROVAL_TOKEN_ALREADY_USED")
            self._consumed.add(claims.token_id)
        return claims
