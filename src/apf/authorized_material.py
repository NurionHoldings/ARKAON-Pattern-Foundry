from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


class MaterialError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class SourceRights(StrEnum):
    USER_OWNED = "USER_OWNED"
    EXPLICIT_PERMISSION = "EXPLICIT_PERMISSION"
    PERMISSIVE_LICENSE = "PERMISSIVE_LICENSE"
    ATTRIBUTION_LICENSE = "ATTRIBUTION_LICENSE"
    COPYLEFT_LICENSE = "COPYLEFT_LICENSE"
    PUBLIC_OBSERVATION = "PUBLIC_OBSERVATION"
    UNKNOWN = "UNKNOWN"


class UseRoute(StrEnum):
    LICENSED_REUSE = "LICENSED_REUSE"
    ADAPTIVE_REIMPLEMENTATION = "ADAPTIVE_REIMPLEMENTATION"


class MaterialState(StrEnum):
    REQUESTED = "REQUESTED"
    RIGHTS_EVALUATED = "RIGHTS_EVALUATED"
    COLLECTION_POLICY_PASSED = "COLLECTION_POLICY_PASSED"
    CAPTURED = "CAPTURED"
    SANITIZED = "SANITIZED"
    NORMALIZED = "NORMALIZED"
    LICENSE_ORIGINALITY_REVIEW = "LICENSE_ORIGINALITY_REVIEW"
    ASSET_CANDIDATE = "ASSET_CANDIDATE"
    ETHERNIAN_REVIEW = "ETHERNIAN_REVIEW"
    DENIED = "DENIED"
    QUARANTINED = "QUARANTINED"
    EXPIRED = "EXPIRED"


class ReviewDecision(StrEnum):
    APPROVE = "APPROVE"
    REVIEW = "REVIEW"
    DENY = "DENY"


_DIGEST = re.compile(r"\Asha256:[0-9a-f]{64}\Z")
_NONCE = re.compile(r"\A[0-9a-f-]{36}\Z")
_SECRET_KEY = re.compile(
    r"(?i)(authorization|cookie|set-cookie|password|passwd|token|secret|api[-_]?key|session|localstorage|sessionstorage)"
)
_QUERY_SECRET = re.compile(r"(?i)(token|secret|password|code|key|session|auth)")
_EMAIL = re.compile(r"(?i)[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9-]+(?:\.[A-Z0-9-]+)+")
_PHONE = re.compile(r"(?<!\d)01[016789][ -.]?\d{3,4}[ -.]?\d{4}(?!\d)")
_KOREAN_RRN = re.compile(r"(?<!\d)\d{6}[ -]?[1-8]\d{6}(?!\d)")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}")
_INLINE_SECRET = re.compile(
    r"(?i)(\b(?:password|passwd|token|secret|api[-_]?key|session)\b\s*[:=]\s*)"
    r"(?:['\"]?)[^\s,'\";}]{4,}"
)


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise MaterialError("NAIVE_TIMESTAMP")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _origin(url: str) -> str:
    try:
        parsed, port = urlsplit(url), urlsplit(url).port
    except (TypeError, ValueError):
        raise MaterialError("INVALID_URL") from None
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise MaterialError("INVALID_URL")
    suffix = f":{port}" if port and port != 443 else ""
    return f"https://{parsed.hostname.lower()}{suffix}"


def _canonical(value: object) -> bytes:
    data = asdict(value)  # type: ignore[arg-type]
    data.pop("signature", None)
    for key, item in tuple(data.items()):
        if isinstance(item, datetime):
            data[key] = _timestamp(item)
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()


@dataclass(frozen=True)
class LicenseTerms:
    identifier: str
    allow_use: bool
    allow_modify: bool
    allow_redistribute: bool
    attribution_required: bool = False
    source_disclosure_required: bool = False
    notice: str = ""

    @property
    def obligations(self) -> tuple[str, ...]:
        result = []
        if self.attribution_required:
            result.append("ATTRIBUTION")
        if self.source_disclosure_required:
            result.append("SOURCE_DISCLOSURE")
        return tuple(result)


@dataclass(frozen=True)
class RightsEvidence:
    rights: SourceRights
    evidence_hash: str
    terms: LicenseTerms
    owner_or_licensor: str

    def __post_init__(self) -> None:
        if not _DIGEST.fullmatch(self.evidence_hash):
            raise MaterialError("INVALID_RIGHTS_EVIDENCE_HASH")
        if self.rights is SourceRights.ATTRIBUTION_LICENSE and not self.terms.attribution_required:
            raise MaterialError("ATTRIBUTION_OBLIGATION_MISSING")
        if (
            self.rights is SourceRights.COPYLEFT_LICENSE
            and not self.terms.source_disclosure_required
        ):
            raise MaterialError("COPYLEFT_OBLIGATION_MISSING")

    @property
    def fingerprint(self) -> str:
        return "sha256:" + sha256(_canonical(self)).hexdigest()


@dataclass(frozen=True)
class MaterialRequest:
    source_url: str
    allowed_origins: tuple[str, ...]
    route: UseRoute
    purpose: str
    allowed_content_types: tuple[str, ...]
    max_requests: int
    max_bytes: int
    expires_at: datetime
    attempts_to_bypass_access_control: bool = False
    requests_private_or_secret_material: bool = False
    correlation_id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        source_origin = _origin(self.source_url)
        if any(_QUERY_SECRET.search(key) for key, _ in parse_qsl(urlsplit(self.source_url).query)):
            raise MaterialError("REQUEST_URL_SECRET_BLOCKED")
        if source_origin not in self.allowed_origins or any(
            _origin(x) != x for x in self.allowed_origins
        ):
            raise MaterialError("ORIGIN_NOT_ALLOWLISTED")
        if (
            not self.purpose
            or not self.allowed_content_types
            or self.max_requests < 1
            or self.max_bytes < 1
        ):
            raise MaterialError("INVALID_COLLECTION_BUDGET")
        _timestamp(self.expires_at)

    @property
    def fingerprint(self) -> str:
        return "sha256:" + sha256(_canonical(self)).hexdigest()


@dataclass(frozen=True)
class EthernianAttestation:
    request_fingerprint: str
    stage: str
    rights_fingerprint: str
    stage_payload_fingerprint: str
    decision: ReviewDecision
    expires_at: datetime
    nonce: str
    signature: str


class EthernianSigner:
    """External reviewer helper. The acquisition pipeline receives only its public key."""

    def __init__(self, private_key: Ed25519PrivateKey) -> None:
        self._key = private_key

    def sign(
        self,
        request: MaterialRequest,
        rights: RightsEvidence,
        *,
        stage: str,
        stage_payload_fingerprint: str,
        decision: ReviewDecision,
        expires_at: datetime,
        nonce: str,
    ) -> EthernianAttestation:
        unsigned = EthernianAttestation(
            request.fingerprint,
            stage,
            rights.fingerprint,
            stage_payload_fingerprint,
            decision,
            expires_at,
            nonce,
            "",
        )
        return EthernianAttestation(
            **{**asdict(unsigned), "signature": self._key.sign(_canonical(unsigned)).hex()}
        )


@dataclass(frozen=True)
class CollectionPosture:
    robots: str
    terms: str
    explicit_authorization_overrides_conflict: bool = False
    access_authorized: bool = True

    def __post_init__(self) -> None:
        if self.robots not in {"ALLOW", "DISALLOW", "UNKNOWN"}:
            raise MaterialError("INVALID_ROBOTS_POSTURE")
        if self.terms not in {"OK", "CONFLICT", "UNKNOWN"}:
            raise MaterialError("INVALID_TERMS_POSTURE")

    @property
    def fingerprint(self) -> str:
        return "sha256:" + sha256(_canonical(self)).hexdigest()


@dataclass(frozen=True)
class CaptureBundle:
    url: str
    content_type: str
    body: str
    har: Mapping[str, object] | None = None
    dom: str | None = None
    source_map: str | None = None


@dataclass(frozen=True)
class SanitizedCapture:
    url: str
    content_type: str
    body: str
    har: Mapping[str, object] | None
    dom: str | None
    source_map: str | None
    content_hash: str


@dataclass(frozen=True)
class NormalizedMaterial:
    language: str
    normalized: str
    structural_summary: tuple[str, ...]
    source_hash: str


@dataclass(frozen=True)
class ImprovementEvidence:
    dimension: str
    evidence_hash: str
    before_metric: str | None = None
    after_metric: str | None = None
    reviewer_assessment: str | None = None

    def __post_init__(self) -> None:
        if self.dimension not in {"SAFETY", "PERFORMANCE", "STRUCTURE", "USABILITY"}:
            raise MaterialError("INVALID_IMPROVEMENT_DIMENSION")
        if not _DIGEST.fullmatch(self.evidence_hash):
            raise MaterialError("INVALID_IMPROVEMENT_EVIDENCE_HASH")
        measured_change = (
            self.before_metric is not None
            and self.after_metric is not None
            and self.before_metric != self.after_metric
        )
        assessed_change = bool(self.reviewer_assessment and self.reviewer_assessment.strip())
        if not measured_change and not assessed_change:
            raise MaterialError("NO_MEASURABLE_OR_ASSESSED_IMPROVEMENT")

    @property
    def fingerprint(self) -> str:
        return "sha256:" + sha256(_canonical(self)).hexdigest()


def originality_payload_fingerprint(
    *, candidate_content: str, route: UseRoute, evidence: tuple[ImprovementEvidence, ...]
) -> str:
    payload = {
        "candidate_content_hash": "sha256:" + sha256(candidate_content.encode()).hexdigest(),
        "improvement_evidence": [item.fingerprint for item in evidence],
        "route": route.value,
    }
    return (
        "sha256:"
        + sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    )


@dataclass(frozen=True)
class AssetCandidate:
    route: UseRoute
    content_hash: str
    provenance_hash: str
    obligations: tuple[str, ...]
    improvement_dimensions: tuple[str, ...]
    status: str = "CANDIDATE_NOT_OWNED_ASSET"


def _redact_url(url: str) -> str:
    parsed = urlsplit(url)
    query = [
        (key, "[REDACTED]" if _QUERY_SECRET.search(key) else value)
        for key, value in parse_qsl(parsed.query)
    ]
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ""))


def _redact_text(value: str) -> str:
    value = _EMAIL.sub("[REDACTED_PII]", value)
    value = _PHONE.sub("[REDACTED_PII]", value)
    value = _KOREAN_RRN.sub("[REDACTED_PII]", value)
    value = _JWT.sub("[REDACTED_SECRET]", value)
    value = _BEARER.sub("[REDACTED_SECRET]", value)
    return _INLINE_SECRET.sub(r"\1[REDACTED_SECRET]", value)


def _sanitize(value: object, key: str = "") -> object:
    if _SECRET_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, str):
        return (
            _redact_url(value) if value.startswith(("http://", "https://")) else _redact_text(value)
        )
    if isinstance(value, Mapping):
        return {str(k): _sanitize(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize(v) for v in value]
    return value


class AuthorizedMaterialPipeline:
    """Static-only acquisition and adaptation gate; never executes captured code."""

    def __init__(
        self,
        request: MaterialRequest,
        *,
        ethernian_public_key: Ed25519PublicKey,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.request = request
        self.state = MaterialState.REQUESTED
        self.rights: RightsEvidence | None = None
        self.sanitized: SanitizedCapture | None = None
        self.normalized: NormalizedMaterial | None = None
        self._capture: CaptureBundle | None = None
        self._key = ethernian_public_key
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self._nonces: set[tuple[str, str]] = set()
        self._requests = 0
        self._bytes = 0
        self._source_identifiers: set[str] = set()
        self.audit = ["MATERIAL_REQUESTED"]
        self._check_time()

    def _now(self) -> datetime:
        now = self._now_provider()
        if now.tzinfo is None:
            raise MaterialError("NAIVE_CLOCK")
        return now

    def _check_time(self) -> None:
        if self._now() >= self.request.expires_at:
            self.state = MaterialState.EXPIRED
            raise MaterialError("REQUEST_EXPIRED")

    def _require(self, state: MaterialState) -> None:
        if self.state != state:
            raise MaterialError("INVALID_STATE_TRANSITION")

    def _verify(
        self,
        item: EthernianAttestation,
        *,
        stage: str,
        rights: RightsEvidence,
        stage_payload_fingerprint: str,
    ) -> None:
        if item.stage != stage or item.request_fingerprint != self.request.fingerprint:
            raise MaterialError("ATTESTATION_BINDING_MISMATCH")
        if item.rights_fingerprint != rights.fingerprint or not _NONCE.fullmatch(item.nonce):
            raise MaterialError("ATTESTATION_BINDING_MISMATCH")
        if item.stage_payload_fingerprint != stage_payload_fingerprint:
            raise MaterialError("ATTESTATION_PAYLOAD_MISMATCH")
        if (
            item.expires_at.tzinfo is None
            or self._now() >= item.expires_at
            or item.expires_at > self.request.expires_at
        ):
            raise MaterialError("ATTESTATION_EXPIRED")
        replay = (stage, item.nonce)
        if replay in self._nonces:
            raise MaterialError("ATTESTATION_REPLAY_BLOCKED")
        try:
            self._key.verify(bytes.fromhex(item.signature), _canonical(item))
        except (InvalidSignature, ValueError, TypeError):
            raise MaterialError("INVALID_ATTESTATION_SIGNATURE") from None
        self._nonces.add(replay)

    def evaluate_rights(self, rights: RightsEvidence, attestation: EthernianAttestation) -> None:
        self._require(MaterialState.REQUESTED)
        self._check_time()
        self._verify(
            attestation,
            stage="RIGHTS",
            rights=rights,
            stage_payload_fingerprint=rights.fingerprint,
        )
        if (
            self.request.attempts_to_bypass_access_control
            or self.request.requests_private_or_secret_material
        ):
            self.state = MaterialState.DENIED
            raise MaterialError("PROHIBITED_ACQUISITION")
        if attestation.decision is ReviewDecision.DENY:
            self.state = MaterialState.DENIED
            raise MaterialError("RIGHTS_DENIED")
        if rights.rights is SourceRights.UNKNOWN or attestation.decision is ReviewDecision.REVIEW:
            self.state = MaterialState.ETHERNIAN_REVIEW
            self.rights = rights
            return
        if self.request.route is UseRoute.LICENSED_REUSE:
            if rights.rights is SourceRights.PUBLIC_OBSERVATION:
                self.state = MaterialState.ETHERNIAN_REVIEW
                self.rights = rights
                return
            if not all(
                (
                    rights.terms.allow_use,
                    rights.terms.allow_modify,
                    rights.terms.allow_redistribute,
                )
            ):
                self.state = MaterialState.DENIED
                raise MaterialError("LICENSE_ROUTE_NOT_ALLOWED")
        self.rights = rights
        self.state = MaterialState.RIGHTS_EVALUATED

    def pass_collection_policy(
        self, posture: CollectionPosture, *, attestation: EthernianAttestation
    ) -> None:
        self._require(MaterialState.RIGHTS_EVALUATED)
        assert self.rights is not None
        self._verify(
            attestation,
            stage="COLLECTION_POLICY",
            rights=self.rights,
            stage_payload_fingerprint=posture.fingerprint,
        )
        if attestation.decision is ReviewDecision.REVIEW:
            self.state = MaterialState.ETHERNIAN_REVIEW
            return
        if attestation.decision is ReviewDecision.DENY:
            self.state = MaterialState.DENIED
            raise MaterialError("COLLECTION_POLICY_DENIED")
        if not posture.access_authorized:
            self.state = MaterialState.DENIED
            raise MaterialError("UNAUTHORIZED_ACCESS_DENIED")
        conflict = posture.robots == "DISALLOW" or posture.terms == "CONFLICT"
        uncertain = posture.robots == "UNKNOWN" or posture.terms == "UNKNOWN"
        has_direct_right = self.rights.rights in {
            SourceRights.USER_OWNED,
            SourceRights.EXPLICIT_PERMISSION,
        }
        if (conflict or uncertain) and not (
            has_direct_right and posture.explicit_authorization_overrides_conflict
        ):
            self.state = MaterialState.ETHERNIAN_REVIEW
            return
        self.state = MaterialState.COLLECTION_POLICY_PASSED

    def validate_redirect(self, url: str) -> None:
        self._require(MaterialState.COLLECTION_POLICY_PASSED)
        if _origin(url) not in self.request.allowed_origins:
            self.state = MaterialState.DENIED
            raise MaterialError("REDIRECT_ORIGIN_BLOCKED")
        self._consume(1, 0)

    def _consume(self, requests: int, size: int) -> None:
        self._requests += requests
        self._bytes += size
        if self._requests > self.request.max_requests or self._bytes > self.request.max_bytes:
            self.state = MaterialState.DENIED
            raise MaterialError("COLLECTION_BUDGET_EXCEEDED")

    def capture(self, bundle: CaptureBundle) -> None:
        self._require(MaterialState.COLLECTION_POLICY_PASSED)
        if _origin(bundle.url) not in self.request.allowed_origins:
            self.state = MaterialState.DENIED
            raise MaterialError("CAPTURE_ORIGIN_BLOCKED")
        if bundle.content_type not in self.request.allowed_content_types:
            self.state = MaterialState.DENIED
            raise MaterialError("CONTENT_TYPE_BLOCKED")
        if (
            bundle.source_map is not None
            and self.rights
            and self.rights.rights in {SourceRights.PUBLIC_OBSERVATION, SourceRights.UNKNOWN}
        ):
            self.state = MaterialState.ETHERNIAN_REVIEW
            raise MaterialError("SOURCEMAP_AUTHORIZATION_REQUIRED")
        self._consume(
            1,
            len(bundle.body.encode())
            + len((bundle.dom or "").encode())
            + len((bundle.source_map or "").encode()),
        )
        self._capture = bundle
        self.state = MaterialState.CAPTURED

    def sanitize(self) -> SanitizedCapture:
        self._require(MaterialState.CAPTURED)
        item = self._capture
        if item is None:
            raise MaterialError("CAPTURE_MISSING")
        sanitized = SanitizedCapture(
            _redact_url(item.url),
            item.content_type,
            _redact_text(item.body),
            _sanitize(item.har) if item.har is not None else None,  # type: ignore[arg-type]
            _redact_text(item.dom) if item.dom else None,
            _redact_text(item.source_map) if item.source_map else None,
            "sha256:" + sha256(item.body.encode()).hexdigest(),
        )
        self._capture = None
        self.sanitized = sanitized
        self.state = MaterialState.SANITIZED
        return sanitized

    def accept_sanitized_capture(self, capture: SanitizedCapture) -> None:
        """Accept an already-sanitized capture from an approved external collector.

        The pipeline deliberately has no network client.  Callers must retain raw
        material in a quarantine store and pass only a redacted envelope here.
        """
        self._require(MaterialState.COLLECTION_POLICY_PASSED)
        self._check_time()
        if _origin(capture.url) not in self.request.allowed_origins:
            self.state = MaterialState.DENIED
            raise MaterialError("CAPTURE_ORIGIN_BLOCKED")
        if capture.content_type not in self.request.allowed_content_types:
            self.state = MaterialState.DENIED
            raise MaterialError("CONTENT_TYPE_BLOCKED")
        if (
            capture.source_map is not None
            and self.rights
            and self.rights.rights in {SourceRights.PUBLIC_OBSERVATION, SourceRights.UNKNOWN}
        ):
            self.state = MaterialState.ETHERNIAN_REVIEW
            raise MaterialError("SOURCEMAP_AUTHORIZATION_REQUIRED")
        if not _DIGEST.fullmatch(capture.content_hash):
            raise MaterialError("INVALID_CONTENT_HASH")
        values = (capture.body, capture.dom or "", capture.source_map or "")
        if _redact_url(capture.url) != capture.url or any(
            _redact_text(value) != value for value in values
        ):
            self.state = MaterialState.QUARANTINED
            raise MaterialError("UNSANITIZED_CAPTURE_BLOCKED")
        sanitized_har = _sanitize(capture.har) if capture.har is not None else None
        if sanitized_har != capture.har:
            self.state = MaterialState.QUARANTINED
            raise MaterialError("UNSANITIZED_CAPTURE_BLOCKED")
        self._consume(1, len(capture.body.encode()))
        self.sanitized = capture
        self.state = MaterialState.SANITIZED

    def normalize(self) -> NormalizedMaterial:
        self._require(MaterialState.SANITIZED)
        assert self.sanitized is not None
        text, content_type = self.sanitized.body, self.sanitized.content_type
        if "javascript" in content_type:
            language = "javascript"
            tokens = re.findall(
                r"[A-Za-z_$][\w$]*|\d+(?:\.\d+)?|===|!==|=>|[{}()[\];,.=+*/<>:-]", text
            )
            identifiers: dict[str, str] = {}
            keywords = {
                "if",
                "else",
                "for",
                "while",
                "return",
                "function",
                "const",
                "let",
                "var",
                "class",
                "new",
                "async",
                "await",
                "true",
                "false",
                "null",
            }
            normalized_tokens = []
            for token in tokens:
                if re.fullmatch(r"[A-Za-z_$][\w$]*", token) and token not in keywords:
                    identifiers.setdefault(token, f"id{len(identifiers) + 1}")
                    token = identifiers[token]
                normalized_tokens.append(token)
            self._source_identifiers = {item for item in identifiers if len(item) >= 12}
            normalized = " ".join(normalized_tokens)
            summary = (
                f"identifiers:{len(identifiers)}",
                f"branches:{tokens.count('if')}",
                f"functions:{tokens.count('function') + tokens.count('=>')}",
            )
        elif "css" in content_type:
            language, normalized = (
                "css",
                re.sub(r"\s*([{}:;,])\s*", r"\1", re.sub(r"\s+", " ", text)).strip(),
            )
            summary = (f"rules:{normalized.count('{')}", f"declarations:{normalized.count(':')}")
        else:
            language, normalized = "html", re.sub(r">\s+<", "><", re.sub(r"\s+", " ", text)).strip()
            tags = re.findall(r"<\s*([a-zA-Z][\w-]*)", normalized)
            summary = (f"elements:{len(tags)}", f"distinct-tags:{len(set(tags))}")
        result = NormalizedMaterial(language, normalized, summary, self.sanitized.content_hash)
        self.normalized = result
        self.state = MaterialState.NORMALIZED
        return result

    def begin_originality_review(self) -> None:
        self._require(MaterialState.NORMALIZED)
        self.state = MaterialState.LICENSE_ORIGINALITY_REVIEW

    def approve_candidate(
        self,
        candidate_content: str,
        *,
        improvement_evidence: tuple[ImprovementEvidence, ...],
        attestation: EthernianAttestation,
    ) -> AssetCandidate:
        self._require(MaterialState.LICENSE_ORIGINALITY_REVIEW)
        assert self.rights is not None and self.normalized is not None
        payload_fingerprint = originality_payload_fingerprint(
            candidate_content=candidate_content,
            route=self.request.route,
            evidence=improvement_evidence,
        )
        self._verify(
            attestation,
            stage="ORIGINALITY",
            rights=self.rights,
            stage_payload_fingerprint=payload_fingerprint,
        )
        if attestation.decision is not ReviewDecision.APPROVE:
            self.state = (
                MaterialState.ETHERNIAN_REVIEW
                if attestation.decision is ReviewDecision.REVIEW
                else MaterialState.DENIED
            )
            raise MaterialError("ORIGINALITY_NOT_APPROVED")
        if self.request.route is UseRoute.ADAPTIVE_REIMPLEMENTATION and not improvement_evidence:
            raise MaterialError("NO_MATERIAL_IMPROVEMENT")
        if _redact_text(candidate_content) != candidate_content:
            self.state = MaterialState.QUARANTINED
            raise MaterialError("CANDIDATE_SECRET_OR_PII_BLOCKED")
        if self.request.route is UseRoute.ADAPTIVE_REIMPLEMENTATION:
            compact_source = re.sub(
                r"\s+", " ", self.sanitized.body if self.sanitized else ""
            ).strip()
            compact_candidate = re.sub(r"\s+", " ", candidate_content).strip()
            for start in range(max(0, len(compact_candidate) - 119)):
                if compact_candidate[start : start + 120] in compact_source:
                    self.state = MaterialState.QUARANTINED
                    raise MaterialError("LARGE_SOURCE_FRAGMENT_LEAK")
            candidate_identifiers = set(re.findall(r"[A-Za-z_$][\w$]*", candidate_content))
            if candidate_identifiers & self._source_identifiers:
                self.state = MaterialState.QUARANTINED
                raise MaterialError("SOURCE_IDENTIFIER_LEAK")
        content_hash = "sha256:" + sha256(candidate_content.encode()).hexdigest()
        result = AssetCandidate(
            self.request.route,
            content_hash,
            self.rights.evidence_hash,
            self.rights.terms.obligations,
            tuple(sorted({item.dimension for item in improvement_evidence})),
        )
        self.state = MaterialState.ASSET_CANDIDATE
        self.audit.append("ASSET_CANDIDATE_NOT_OWNED_ASSET")
        return result
