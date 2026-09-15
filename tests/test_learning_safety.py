import pytest

from apf.learning_safety import (
    LearningSafetyViolation,
    require_safe_learning_payload,
    scan_learning_payload,
    scan_learning_text,
)

EVIDENCE_ID = "evidence://sha256/" + "a" * 64


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("api_key=dummyValue123456789", "SECRET_API_KEY"),
        ("token: dummyTokenValue123456789", "SECRET_TOKEN"),
        ("password=not-a-real-password", "SECRET_PASSWORD"),
        ("-----BEGIN PRIVATE KEY-----", "SECRET_PRIVATE_KEY"),
        ("문의: learner@example.com", "PII_EMAIL"),
        ("연락처 010-1234-5678", "PII_KOREAN_PHONE"),
        ("식별번호 900101-1234568", "PII_KOREAN_RRN"),
    ],
)
def test_scanner_blocks_secret_and_pii_without_returning_source(text: str, code: str) -> None:
    codes = scan_learning_text(text)

    assert code in codes
    assert text not in repr(codes)


def test_rrn_checksum_reduces_false_positives() -> None:
    assert "PII_KOREAN_RRN" not in scan_learning_text("문서 번호 900101-1234567")


def test_normal_technical_learning_text_is_allowed() -> None:
    result = scan_learning_payload(
        {
            "problem": "A stale approval may authorize an unintended result.",
            "principle": "Bind approval to the exact resulting fingerprint.",
            "failure_mode": None,
        },
        (EVIDENCE_ID,),
    )

    assert result.safe
    assert result.violation_codes == ()


@pytest.mark.parametrize(
    "reference",
    [
        "https://example.com/source?token=dummyTokenValue123456789",
        "evidence://official/specification",
        "file:///tmp/raw-source.txt",
        "evidence://sha256/" + "A" * 64,
        "",
    ],
)
def test_only_canonical_opaque_evidence_ids_are_allowed(reference: str) -> None:
    result = scan_learning_payload({"principle": "Safe principle"}, (reference,))

    assert not result.safe
    assert result.violation_codes == ("EVIDENCE_REF_NOT_OPAQUE",)


def test_all_fields_are_scanned_and_codes_are_deterministic() -> None:
    result = scan_learning_payload(
        {
            "principle": "문의 learner@example.com",
            "problem": "password=not-a-real-password",
        },
        ("raw reference",),
    )

    assert result.violation_codes == (
        "EVIDENCE_REF_NOT_OPAQUE",
        "PII_EMAIL",
        "SECRET_PASSWORD",
    )


def test_rejection_exception_contains_codes_but_not_original_content() -> None:
    original = "learner@example.com"

    with pytest.raises(LearningSafetyViolation) as caught:
        require_safe_learning_payload({"principle": original}, (EVIDENCE_ID,))

    assert caught.value.codes == ("PII_EMAIL",)
    assert original not in str(caught.value)


def test_invalid_payload_fails_closed_without_crashing() -> None:
    result = scan_learning_payload({"principle": 123}, (EVIDENCE_ID,))  # type: ignore[dict-item]

    assert result.violation_codes == ("LEARNING_PAYLOAD_INVALID",)
