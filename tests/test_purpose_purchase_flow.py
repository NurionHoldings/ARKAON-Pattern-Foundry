from datetime import UTC, datetime
from uuid import uuid4

import pytest

from apf.purpose_purchase_flow import (
    FlowState,
    PaymentStatus,
    PurposePurchaseError,
    PurposePurchaseStore,
    PurposeSelection,
    RawPaymentEvent,
    VerifiedPayment,
    digest,
)


class SandboxVerifier:
    def verify(self, event):
        return VerifiedPayment(
            event=event, verifier="PAYMENT_ADAPTER",
            verification_digest=digest({"sandbox_verified": event.model_dump(mode="json")}),
        )


def selection():
    return PurposeSelection(
        product_code="platform-starter", product_name="플랫폼 시작 상품",
        purpose="사용자의 목적에 맞는 플랫폼 sandbox를 단계적으로 구현한다.",
        amount_minor=5500000, currency="KRW",
        allowed_paths=["src/apf/generated/**", "tests/generated/**"],
        scope_digest="sha256:" + "a" * 64,
        owner_approval_digest="sha256:" + "b" * 64,
    )


def setup(tmp_path):
    store = PurposePurchaseStore(tmp_path, SandboxVerifier())
    tenant, owner = uuid4(), uuid4()
    order = store.create(tenant_id=tenant, owner_principal_id=owner, selection=selection())
    checkout = store.open_checkout(
        order["order_id"], tenant_id=tenant, owner_principal_id=owner
    )
    return store, tenant, owner, order["order_id"], checkout


def payment(checkout, status=PaymentStatus.SUCCEEDED, **changes):
    values = {
        "event_id": str(uuid4()), "checkout_id": checkout["checkout_id"],
        "checkout_digest": checkout["checkout_digest"], "provider_payment_id": str(uuid4()),
        "amount_minor": checkout["amount_minor"], "currency": checkout["currency"],
        "status": status, "occurred_at": datetime.now(UTC), "environment": "SANDBOX",
    }
    values.update(changes)
    return RawPaymentEvent.model_validate(values)


def test_end_to_end_payment_unlocks_scoped_work_and_stops_before_deployment(tmp_path):
    store, tenant, _, order_id, checkout = setup(tmp_path)
    paid = store.record_payment(order_id, tenant_id=tenant, event=payment(checkout))
    assert paid["state"] == FlowState.IMPLEMENTATION_READY
    current = store.start_implementation(
        order_id, tenant_id=tenant, scope_digest=selection().scope_digest
    )
    assert current["state"] == FlowState.SANDBOX_IMPLEMENTING
    for role, skip in [
        ("ARKAON", False), ("ARKAON", False), ("ETERNIAN", False),
        ("ETERNIAN", True), ("ETERNIAN", False), ("ETERNIAN", False),
    ]:
        current = store.advance(
            order_id, tenant_id=tenant, actor_role=role,
            evidence_digest="sha256:" + "c" * 64, skip_remediation=skip,
        )
    assert current["state"] == FlowState.DEPLOYMENT_APPROVAL_PENDING
    assert current["automatic_merge_allowed"] is False
    assert current["deployment_allowed"] is False


def test_payment_is_required_and_never_expands_owner_scope(tmp_path):
    store, tenant, _, order_id, checkout = setup(tmp_path)
    with pytest.raises(PurposePurchaseError, match="VERIFIED_PAYMENT_REQUIRED"):
        store.start_implementation(
            order_id, tenant_id=tenant, scope_digest=selection().scope_digest
        )
    store.record_payment(order_id, tenant_id=tenant, event=payment(checkout))
    with pytest.raises(PurposePurchaseError, match="SCOPE_MISMATCH"):
        store.start_implementation(
            order_id, tenant_id=tenant, scope_digest="sha256:" + "d" * 64
        )


@pytest.mark.parametrize("field", ["amount_minor", "currency"])
def test_amount_and_currency_mismatch_fail_closed(tmp_path, field):
    store, tenant, _, order_id, checkout = setup(tmp_path)
    changed = 1 if field == "amount_minor" else "USD"
    with pytest.raises(PurposePurchaseError, match="AMOUNT_OR_CURRENCY"):
        store.record_payment(
            order_id, tenant_id=tenant, event=payment(checkout, **{field: changed})
        )


def test_failed_payment_allows_new_checkout_and_rejects_stale_success(tmp_path):
    store, tenant, owner, order_id, first = setup(tmp_path)
    store.record_payment(
        order_id, tenant_id=tenant, event=payment(first, PaymentStatus.FAILED)
    )
    second = store.open_checkout(order_id, tenant_id=tenant, owner_principal_id=owner)
    with pytest.raises(PurposePurchaseError, match="STALE_CHECKOUT"):
        store.record_payment(order_id, tenant_id=tenant, event=payment(first))
    ready = store.record_payment(order_id, tenant_id=tenant, event=payment(second))
    assert ready["state"] == FlowState.IMPLEMENTATION_READY


def test_duplicate_event_is_idempotent_but_conflicting_event_is_blocked(tmp_path):
    store, tenant, _, order_id, checkout = setup(tmp_path)
    event = payment(checkout)
    first = store.record_payment(order_id, tenant_id=tenant, event=event)
    second = store.record_payment(order_id, tenant_id=tenant, event=event)
    assert first["flow_digest"] == second["flow_digest"]
    conflict = event.model_copy(update={"status": PaymentStatus.REVERSED})
    with pytest.raises(PurposePurchaseError, match="EVENT_CONFLICT"):
        store.record_payment(order_id, tenant_id=tenant, event=conflict)


def test_payment_reversal_stops_the_flow_without_erasing_evidence(tmp_path):
    store, tenant, _, order_id, checkout = setup(tmp_path)
    succeeded = payment(checkout)
    store.record_payment(order_id, tenant_id=tenant, event=succeeded)
    store.start_implementation(order_id, tenant_id=tenant, scope_digest=selection().scope_digest)
    reversed_event = payment(
        checkout, PaymentStatus.REVERSED,
        provider_payment_id=succeeded.provider_payment_id,
    )
    held = store.record_payment(order_id, tenant_id=tenant, event=reversed_event)
    assert held["state"] == FlowState.HOLD_PAYMENT_REVERSED
    assert held["implementation_events"]
    with pytest.raises(PurposePurchaseError, match="TRANSITION_NOT_ALLOWED"):
        store.advance(
            order_id, tenant_id=tenant, actor_role="ARKAON",
            evidence_digest="sha256:" + "e" * 64,
        )


def test_arkaon_cannot_perform_eternian_audit_or_advance_without_evidence(tmp_path):
    store, tenant, _, order_id, checkout = setup(tmp_path)
    store.record_payment(order_id, tenant_id=tenant, event=payment(checkout))
    store.start_implementation(order_id, tenant_id=tenant, scope_digest=selection().scope_digest)
    store.advance(
        order_id, tenant_id=tenant, actor_role="ARKAON",
        evidence_digest="sha256:" + "1" * 64,
    )
    store.advance(
        order_id, tenant_id=tenant, actor_role="ARKAON",
        evidence_digest="sha256:" + "2" * 64,
    )
    with pytest.raises(PurposePurchaseError, match="ROLE_MISMATCH"):
        store.advance(
            order_id, tenant_id=tenant, actor_role="ARKAON",
            evidence_digest="sha256:" + "3" * 64,
        )
    with pytest.raises(PurposePurchaseError, match="EVIDENCE_REQUIRED"):
        store.advance(order_id, tenant_id=tenant, actor_role="ETERNIAN", evidence_digest="bad")


def test_reversal_must_target_the_verified_success_payment(tmp_path):
    store, tenant, _, order_id, checkout = setup(tmp_path)
    store.record_payment(order_id, tenant_id=tenant, event=payment(checkout))
    with pytest.raises(PurposePurchaseError, match="REVERSAL_TARGET_MISMATCH"):
        store.record_payment(
            order_id, tenant_id=tenant, event=payment(checkout, PaymentStatus.REVERSED)
        )


def test_checkout_expires_and_unsafe_paths_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="safe repository-relative"):
        PurposeSelection.model_validate(
            selection().model_dump() | {"allowed_paths": ["../outside"]}
        )
    store = PurposePurchaseStore(tmp_path, SandboxVerifier(), checkout_ttl_seconds=0)
    tenant, owner = uuid4(), uuid4()
    order = store.create(tenant_id=tenant, owner_principal_id=owner, selection=selection())
    checkout = store.open_checkout(
        order["order_id"], tenant_id=tenant, owner_principal_id=owner
    )
    expired = payment(checkout)
    with pytest.raises(PurposePurchaseError, match="CHECKOUT_EXPIRED"):
        store.record_payment(order["order_id"], tenant_id=tenant, event=expired)


def test_tampered_flow_and_cross_tenant_access_are_blocked(tmp_path):
    store, tenant, _, order_id, _ = setup(tmp_path)
    with pytest.raises(PurposePurchaseError, match="NOT_FOUND"):
        store.get(order_id, tenant_id=uuid4())
    path = tmp_path / "state/purpose-purchase-flows" / f"{order_id}.json"
    text = path.read_text(encoding="utf-8").replace('"deployment_allowed": false', '"deployment_allowed": true')
    path.write_text(text, encoding="utf-8")
    with pytest.raises(PurposePurchaseError, match="TAMPERED"):
        store.get(order_id, tenant_id=tenant)
