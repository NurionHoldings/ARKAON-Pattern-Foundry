from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from apf.learning_safety import scan_learning_text


class AuthGateError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class AuthState(StrEnum):
    REQUESTED = "REQUESTED"
    ETHERNIAN_PREFLIGHT_PASSED = "ETHERNIAN_PREFLIGHT_PASSED"
    WAITING_USER_AUTH = "WAITING_USER_AUTH"
    GRANTED = "GRANTED"
    COLLECTED = "COLLECTED"
    ETHERNIAN_ASSET_REVIEW = "ETHERNIAN_ASSET_REVIEW"
    READY_TO_REPORT = "READY_TO_REPORT"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class AuthMethod(StrEnum):
    BROWSER_AUTH = "browserAuth"
    OAUTH = "OAuth"
    CONNECTOR = "connector"


TERMINAL = frozenset(
    {AuthState.READY_TO_REPORT, AuthState.DENIED, AuthState.EXPIRED, AuthState.REVOKED}
)
_GRANT_REF = re.compile(r"\Agrantref:[0-9a-f-]{36}\Z")
_HASH = re.compile(r"\Asha256:[0-9a-f]{64}\Z")
_NONCE = re.compile(r"\A[0-9a-f-]{36}\Z")


def _safe(*values: str) -> None:
    if {code for value in values for code in scan_learning_text(value)}:
        raise AuthGateError("SECRET_OR_PII_BLOCKED")


def _canonical_origin(value: str) -> str:
    try:
        parsed = urlsplit(value)
        port_number = parsed.port
    except (TypeError, ValueError):
        raise AuthGateError("NON_CANONICAL_ORIGIN") from None
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise AuthGateError("NON_CANONICAL_ORIGIN")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise AuthGateError("NON_CANONICAL_ORIGIN")
    port = f":{port_number}" if port_number and port_number != 443 else ""
    return f"https://{parsed.hostname.lower()}{port}"


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise AuthGateError("NAIVE_EXPIRY")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _payload(value: object) -> bytes:
    data = asdict(value)  # type: ignore[arg-type]
    data.pop("signature", None)
    for key, item in tuple(data.items()):
        if isinstance(item, datetime):
            data[key] = _timestamp(item)
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()


@dataclass(frozen=True)
class AuthRequest:
    service_origin: str
    purpose: str
    scopes: tuple[str, ...]
    read_only: bool
    expected_asset_types: tuple[str, ...]
    public_source_gap: str
    terms_and_license: str
    risks: tuple[str, ...]
    expires_at: datetime
    correlation_id: UUID = field(default_factory=uuid4)
    auth_method: AuthMethod = AuthMethod.BROWSER_AUTH
    user_actions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if _canonical_origin(self.service_origin) != self.service_origin:
            raise AuthGateError("NON_CANONICAL_ORIGIN")
        if not self.scopes or not self.expected_asset_types:
            raise AuthGateError("MISSING_MINIMUM_REQUEST_DETAIL")
        _timestamp(self.expires_at)
        _safe(
            self.purpose,
            *self.scopes,
            *self.expected_asset_types,
            self.public_source_gap,
            self.terms_and_license,
            *self.risks,
            *self.user_actions,
        )

    @property
    def fingerprint(self) -> str:
        data = {
            "auth_method": self.auth_method.value,
            "correlation_id": str(self.correlation_id),
            "expected_asset_types": list(self.expected_asset_types),
            "expires_at": _timestamp(self.expires_at),
            "public_source_gap": self.public_source_gap,
            "purpose": self.purpose,
            "read_only": self.read_only,
            "risks": list(self.risks),
            "scopes": list(self.scopes),
            "service_origin": self.service_origin,
            "terms_and_license": self.terms_and_license,
            "user_actions": list(self.user_actions),
        }
        return (
            "sha256:"
            + sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        )


@dataclass(frozen=True)
class PreflightAttestation:
    request_fingerprint: str
    official_domain: bool
    auth_method_allowlisted: bool
    scopes_minimal: bool
    source_authorized: bool
    robots_terms_license_ok: bool
    assetization_possible: bool
    privacy_secret_boundary_ok: bool
    expires_at: datetime
    nonce: str
    signature: str

    @property
    def passed(self) -> bool:
        data = asdict(self)
        fields = (
            "official_domain",
            "auth_method_allowlisted",
            "scopes_minimal",
            "source_authorized",
            "robots_terms_license_ok",
            "assetization_possible",
            "privacy_secret_boundary_ok",
        )
        return all(data[name] for name in fields)


@dataclass(frozen=True)
class UserActionAttestation:
    request_fingerprint: str
    actions: tuple[str, ...]
    grant_reference: str
    expires_at: datetime
    nonce: str
    signature: str


@dataclass(frozen=True)
class OpaqueGrant:
    reference: str
    audience: str
    scopes: tuple[str, ...]
    purpose: str
    expires_at: datetime

    def __post_init__(self) -> None:
        if _GRANT_REF.fullmatch(self.reference) is None:
            raise AuthGateError("GRANT_REFERENCE_NOT_OPAQUE")
        _timestamp(self.expires_at)
        _safe(self.reference, self.audience, *self.scopes, self.purpose)


@dataclass(frozen=True)
class AssetReceipt:
    provenance: str
    license_id: str
    content_hash: str

    def __post_init__(self) -> None:
        if _HASH.fullmatch(self.content_hash) is None:
            raise AuthGateError("INVALID_CONTENT_HASH")
        _safe(self.provenance, self.license_id, self.content_hash)


class AttestationSigner:
    """External authority helper. Its private key must never be supplied to the gate."""

    def __init__(self, private_key: Ed25519PrivateKey) -> None:
        self._key = private_key

    def sign_preflight(
        self,
        *,
        request: AuthRequest,
        expires_at: datetime,
        nonce: str,
        official_domain: bool,
        auth_method_allowlisted: bool,
        scopes_minimal: bool,
        source_authorized: bool,
        robots_terms_license_ok: bool,
        assetization_possible: bool,
        privacy_secret_boundary_ok: bool,
    ) -> PreflightAttestation:
        item = PreflightAttestation(
            request.fingerprint,
            official_domain,
            auth_method_allowlisted,
            scopes_minimal,
            source_authorized,
            robots_terms_license_ok,
            assetization_possible,
            privacy_secret_boundary_ok,
            expires_at,
            nonce,
            "",
        )
        return PreflightAttestation(
            **{**asdict(item), "signature": self._key.sign(_payload(item)).hex()}
        )

    def sign_user_actions(
        self,
        *,
        request: AuthRequest,
        actions: tuple[str, ...],
        grant_reference: str,
        expires_at: datetime,
        nonce: str,
    ) -> UserActionAttestation:
        item = UserActionAttestation(
            request.fingerprint, actions, grant_reference, expires_at, nonce, ""
        )
        return UserActionAttestation(
            **{**asdict(item), "signature": self._key.sign(_payload(item)).hex()}
        )


class MediatedAuthAcquisition:
    """Verification-only gate: stores public keys, never credentials or signing keys."""

    def __init__(
        self,
        request: AuthRequest,
        *,
        ethernian_public_key: Ed25519PublicKey,
        mediator_public_key: Ed25519PublicKey,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.request, self.state = request, AuthState.REQUESTED
        self.grant: OpaqueGrant | None = None
        self.receipt: AssetReceipt | None = None
        self.audit_codes = ["AUTH_REQUEST_CREATED"]
        self._ethernian_key, self._mediator_key = ethernian_public_key, mediator_public_key
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self._used = False
        self._used_nonces: set[tuple[str, str]] = set()
        self._check_request_time()

    def _now(self) -> datetime:
        value = self._now_provider()
        if value.tzinfo is None:
            raise AuthGateError("NAIVE_CLOCK")
        return value

    def _check_request_time(self) -> None:
        if self._now() >= self.request.expires_at:
            self.state = AuthState.EXPIRED
            raise AuthGateError("REQUEST_EXPIRED")

    def _verify(self, item: object, key: Ed25519PublicKey, kind: str) -> None:
        nonce = getattr(item, "nonce", "")
        expiry = getattr(item, "expires_at", None)
        if not _NONCE.fullmatch(nonce) or not isinstance(expiry, datetime):
            raise AuthGateError("INVALID_ATTESTATION")
        if expiry.tzinfo is None or self._now() >= expiry or expiry > self.request.expires_at:
            raise AuthGateError("ATTESTATION_EXPIRED")
        replay_key = (kind, nonce)
        if replay_key in self._used_nonces:
            raise AuthGateError("ATTESTATION_REPLAY_BLOCKED")
        try:
            key.verify(bytes.fromhex(getattr(item, "signature", "")), _payload(item))
        except (InvalidSignature, ValueError, TypeError):
            raise AuthGateError("INVALID_ATTESTATION_SIGNATURE") from None
        self._used_nonces.add(replay_key)

    def preflight(self, attestation: PreflightAttestation) -> None:
        self._require(AuthState.REQUESTED)
        self._check_request_time()
        self._verify(attestation, self._ethernian_key, "preflight")
        if attestation.request_fingerprint != self.request.fingerprint or not attestation.passed:
            self.state = AuthState.DENIED
            self.audit_codes.append("PREFLIGHT_DENIED")
            raise AuthGateError("ETHERNIAN_PREFLIGHT_DENIED")
        self.state = AuthState.ETHERNIAN_PREFLIGHT_PASSED
        self.audit_codes.append("ETHERNIAN_PREFLIGHT_PASSED")

    def await_user_auth(self) -> None:
        self._require(AuthState.ETHERNIAN_PREFLIGHT_PASSED)
        self.state = AuthState.WAITING_USER_AUTH

    def accept_grant(
        self, grant: OpaqueGrant, *, user_action_attestation: UserActionAttestation | None = None
    ) -> None:
        self._require(AuthState.WAITING_USER_AUTH)
        self._check_request_time()
        if (
            grant.audience != self.request.service_origin
            or grant.scopes != self.request.scopes
            or grant.purpose != self.request.purpose
            or grant.expires_at > self.request.expires_at
            or grant.expires_at <= self._now()
        ):
            raise AuthGateError("GRANT_BINDING_MISMATCH")
        if self.request.user_actions:
            if user_action_attestation is None:
                raise AuthGateError("USER_ACTION_ATTESTATION_REQUIRED")
            self._verify(user_action_attestation, self._mediator_key, "user-action")
            if (
                user_action_attestation.request_fingerprint != self.request.fingerprint
                or user_action_attestation.actions != self.request.user_actions
                or user_action_attestation.grant_reference != grant.reference
            ):
                raise AuthGateError("USER_ACTION_ATTESTATION_MISMATCH")
        elif user_action_attestation is not None:
            raise AuthGateError("UNEXPECTED_USER_ACTION_ATTESTATION")
        self.grant, self.state = grant, AuthState.GRANTED
        self.audit_codes.append("OPAQUE_GRANT_ACCEPTED")

    def collect(self, *, provenance: str, license_id: str, content: bytes) -> AssetReceipt:
        if self._used:
            raise AuthGateError("GRANT_REPLAY_BLOCKED")
        self._require(AuthState.GRANTED)
        self._check_request_time()
        if self.grant is None or self.grant.expires_at <= self._now():
            self.state = AuthState.EXPIRED
            raise AuthGateError("GRANT_EXPIRED")
        receipt = AssetReceipt(provenance, license_id, "sha256:" + sha256(content).hexdigest())
        self._used, self.receipt, self.state = True, receipt, AuthState.COLLECTED
        self.audit_codes.append("ASSET_COLLECTED")
        return receipt

    def begin_asset_review(self) -> None:
        self._require(AuthState.COLLECTED)
        self.state = AuthState.ETHERNIAN_ASSET_REVIEW

    def approve_for_report(
        self, *, provenance_ok: bool, license_ok: bool, content_hash_ok: bool
    ) -> None:
        self._require(AuthState.ETHERNIAN_ASSET_REVIEW)
        if not all((provenance_ok, license_ok, content_hash_ok)):
            self.state = AuthState.DENIED
            raise AuthGateError("ASSET_REVIEW_DENIED")
        self.state = AuthState.READY_TO_REPORT
        self.audit_codes.append("READY_TO_REPORT_NOT_OWNED_ASSET")

    def revoke(self) -> None:
        if self.state in TERMINAL:
            raise AuthGateError("TERMINAL_STATE")
        self.grant, self.state = None, AuthState.REVOKED
        self.audit_codes.append("GRANT_REVOKED")

    def _require(self, expected: AuthState) -> None:
        if self.state != expected:
            raise AuthGateError("INVALID_STATE_TRANSITION")
