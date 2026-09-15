from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from apf.approval_tokens import ApprovalTokenDenied, ApprovalTokenService

SECRET = b"a" * 32
ROLES = frozenset({"OWNER", "HUMAN_APPROVER"})
NOW = datetime(2026, 9, 15, 12, tzinfo=UTC)
BINDINGS = {
    "task_id": "task-42",
    "kind": "ASSET_PROMOTION",
    "intent_fingerprint": "intent:abc",
    "expected_result_fingerprint": "asset:def",
}


def service() -> ApprovalTokenService:
    return ApprovalTokenService(SECRET, human_roles=ROLES)


def issue(issuer: ApprovalTokenService, **changes: object) -> str:
    values = {
        **BINDINGS,
        "approver_id": uuid4(),
        "approver_role": "OWNER",
        "expires_at": NOW + timedelta(minutes=5),
        **changes,
    }
    return issuer.issue(**values)  # type: ignore[arg-type]


def test_token_is_bound_and_consumed_once() -> None:
    verifier = service()
    token = issue(verifier)

    claims = verifier.verify_and_consume(token, **BINDINGS, now=NOW)

    assert claims.task_id == BINDINGS["task_id"]
    assert claims.approver_role == "OWNER"
    with pytest.raises(ApprovalTokenDenied, match="APPROVAL_TOKEN_ALREADY_USED"):
        verifier.verify_and_consume(token, **BINDINGS, now=NOW)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("task_id", "another-task"),
        ("kind", "INTENT_MUTATION"),
        ("intent_fingerprint", "intent:old"),
        ("expected_result_fingerprint", "asset:other"),
    ],
)
def test_each_approval_binding_is_enforced(field: str, replacement: str) -> None:
    verifier = service()
    token = issue(verifier)
    expected = {**BINDINGS, field: replacement}

    with pytest.raises(ApprovalTokenDenied, match="APPROVAL_BINDING_MISMATCH"):
        verifier.verify_and_consume(token, **expected, now=NOW)

    # A mismatched attempt must not burn the valid one-time approval.
    verifier.verify_and_consume(token, **BINDINGS, now=NOW)


def test_tampering_is_rejected() -> None:
    verifier = service()
    token = issue(verifier)
    payload, signature = token.split(".")
    tampered = f"{payload[:-1]}A.{signature}"

    with pytest.raises(ApprovalTokenDenied, match="INVALID_APPROVAL_SIGNATURE"):
        verifier.verify_and_consume(tampered, **BINDINGS, now=NOW)


def test_expired_token_is_rejected() -> None:
    verifier = service()
    token = issue(verifier, expires_at=NOW)

    with pytest.raises(ApprovalTokenDenied, match="APPROVAL_TOKEN_EXPIRED"):
        verifier.verify_and_consume(token, **BINDINGS, now=NOW)


def test_non_human_approver_is_rejected() -> None:
    issuer = service()

    with pytest.raises(ApprovalTokenDenied, match="HUMAN_APPROVER_REQUIRED"):
        issue(issuer, is_human=False)
    with pytest.raises(ApprovalTokenDenied, match="HUMAN_APPROVER_REQUIRED"):
        issue(issuer, approver_role="ARKAON_WORKER")


def test_short_secret_is_rejected() -> None:
    with pytest.raises(ValueError, match="APPROVAL_SECRET_TOO_SHORT"):
        ApprovalTokenService(b"short", human_roles=ROLES)
