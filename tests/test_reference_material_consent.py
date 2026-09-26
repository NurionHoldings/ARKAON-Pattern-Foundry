from datetime import UTC, datetime
from uuid import uuid4

import pytest

from apf.reference_material_consent import (
    NOTICE_VERSION,
    REQUIRED_ACKNOWLEDGEMENTS,
    ReferenceConsentError,
    ReferenceConsentStore,
    ReferenceUseConsent,
    ReferenceUseMode,
    ReferenceUseRequest,
    RightsBasis,
    decide_reference_use,
    digest,
)


def request(**changes):
    values = {
        "request_id": "reference-use-001",
        "source_id": "public-product-page",
        "source_locator": "https://example.org/product",
        "intended_use": "기능 원리만 분석하여 독립적인 화면 흐름을 구현한다.",
        "mode": ReferenceUseMode.CLEAN_ROOM_IMPLEMENTATION,
        "rights_basis": RightsBasis.UNKNOWN,
        "requested_paths": ["src/apf/new_flow.py", "tests/test_new_flow.py"],
        "scope_digest": "sha256:" + "b" * 64,
    }
    values.update(changes)
    return ReferenceUseRequest.model_validate(values)


def consent(item, **changes):
    values = {
        "request_digest": digest(item.model_dump(mode="json")),
        "notice_version": NOTICE_VERSION,
        "acknowledged_items": REQUIRED_ACKNOWLEDGEMENTS,
        "principal_id": uuid4(),
        "nonce": uuid4(),
        "confirmed_at": datetime.now(UTC),
    }
    values.update(changes)
    return ReferenceUseConsent.model_validate(values)


def test_user_can_request_clean_room_use_but_not_direct_expression_reuse():
    item = request()
    decision = decide_reference_use(item, consent(item))
    assert decision.decision == "SANDBOX_IMPLEMENTATION_ALLOWED"
    assert decision.implementation_allowed is True
    assert decision.direct_expression_reuse_allowed is False
    assert decision.merge_allowed is False and decision.deployment_allowed is False


def test_notice_checkbox_set_must_be_exact_and_scope_bound():
    item = request()
    with pytest.raises(ReferenceConsentError, match="INCOMPLETE"):
        decide_reference_use(
            item, consent(item, acknowledged_items={"USER_REQUESTED_SPECIFIC_USE"})
        )
    with pytest.raises(ReferenceConsentError, match="SCOPE_MISMATCH"):
        decide_reference_use(item, consent(item, request_digest="sha256:" + "c" * 64))


def test_direct_reuse_requires_rights_basis_and_evidence_even_after_checkbox():
    item = request(mode=ReferenceUseMode.DIRECT_REUSE)
    blocked = decide_reference_use(item, consent(item))
    assert blocked.decision == "BLOCKED"
    assert blocked.reason == "REFERENCE_REUSE_RIGHTS_REQUIRED"
    permitted = request(
        mode=ReferenceUseMode.DIRECT_REUSE,
        rights_basis=RightsBasis.EXPLICIT_PERMISSION,
        rights_evidence_digest="sha256:" + "d" * 64,
    )
    allowed = decide_reference_use(permitted, consent(permitted))
    assert allowed.direct_expression_reuse_allowed is True


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("contains_personal_data", "REFERENCE_SENSITIVE_MATERIAL_BLOCKED"),
        ("contains_secret_or_private_material", "REFERENCE_SENSITIVE_MATERIAL_BLOCKED"),
        ("bypasses_access_control", "REFERENCE_ACCESS_BYPASS_BLOCKED"),
    ],
)
def test_consent_never_overrides_sensitive_or_access_boundaries(field, reason):
    item = request(**{field: True})
    decision = decide_reference_use(item, consent(item))
    assert decision.decision == "BLOCKED"
    assert decision.reason == reason


def test_reference_only_consent_does_not_authorize_implementation():
    item = request(mode=ReferenceUseMode.PRINCIPLE_REFERENCE)
    decision = decide_reference_use(item, consent(item))
    assert decision.decision == "REFERENCE_ANALYSIS_ALLOWED"
    assert decision.implementation_allowed is False


def test_receipt_is_durable_digest_bound_and_exclusive(tmp_path):
    item = request()
    agreement = consent(item)
    store = ReferenceConsentStore(tmp_path)
    receipt = store.record(item, agreement)
    assert receipt["scope_digest"] == item.scope_digest
    assert receipt["decision"]["deployment_allowed"] is False
    assert receipt["notice_digest"].startswith("sha256:")
    with pytest.raises(ReferenceConsentError, match="ALREADY_RECORDED"):
        store.record(item, agreement)
