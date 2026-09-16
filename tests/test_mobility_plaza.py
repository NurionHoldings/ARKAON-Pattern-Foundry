from datetime import UTC, datetime, timedelta

import pytest

from apf.mobility_plaza import (
    CoarsePlazaCell,
    ForbiddenPlazaUse,
    MobilityPlaza,
    MobilityPlazaFoundation,
    PlazaAdvice,
    PlazaPurpose,
    PlazaRejected,
)

NOW = datetime(2026, 9, 16, 14, 0, tzinfo=UTC)


def plaza(**changes):
    values = {
        "plaza_id": "plaza-sejong-1",
        "branch_id": "sejong-hub",
        "name": "세종 라이더 광장",
        "purposes": frozenset(
            {
                PlazaPurpose.REST,
                PlazaPurpose.WAIT,
                PlazaPurpose.PEER_NOTICE,
                PlazaPurpose.SAFETY_ADVISORY,
            }
        ),
        "cell": CoarsePlazaCell("wydm3", 5),
        "created_at": NOW,
    }
    values.update(changes)
    return MobilityPlaza(**values)


def foundation():
    service = MobilityPlazaFoundation()
    service.register(plaza())
    return service


def test_precise_or_identity_cells_are_rejected():
    with pytest.raises(PlazaRejected) as caught:
        CoarsePlazaCell("wydm36", 6)
    assert caught.value.code == "PRECISE_LOCATION_FORBIDDEN"


def test_join_requires_consent_and_occupancy_hides_identities():
    service = foundation()
    with pytest.raises(PlazaRejected) as denied:
        service.join(
            plaza_id="plaza-sejong-1",
            rider_id="rider-1",
            consent=False,
            now=NOW,
            ttl=timedelta(hours=2),
        )
    assert denied.value.code == "CONSENT_REQUIRED"
    membership = service.join(
        plaza_id="plaza-sejong-1",
        rider_id="rider-1",
        consent=True,
        now=NOW,
        ttl=timedelta(hours=2),
    )
    occupancy = service.occupancy(plaza_id="plaza-sejong-1", now=NOW)
    view = membership.public_view()
    assert occupancy.member_count == 1
    assert occupancy.identities_disclosed is False
    assert occupancy.usable_for_dispatch is False
    assert "rider-1" not in repr(view)
    assert "rider-1" not in membership.rider_id_hash


def test_notice_is_not_a_dispatch_signal_and_strips_pii():
    service = foundation()
    service.join(
        plaza_id="plaza-sejong-1",
        rider_id="rider-1",
        consent=True,
        now=NOW,
        ttl=timedelta(hours=2),
    )
    notice = service.post_notice(
        plaza_id="plaza-sejong-1",
        rider_id="rider-1",
        purpose=PlazaPurpose.PEER_NOTICE,
        body="그늘과 물이 있습니다. 대기 중 휴식 가능.",
        now=NOW,
        ttl=timedelta(hours=4),
    )
    assert notice.dispatch_signal is False
    public = service.public_notices(plaza_id="plaza-sejong-1", now=NOW)
    assert public[0]["body"].startswith("그늘")
    assert "author_hash" not in public[0]
    with pytest.raises(PlazaRejected) as pii:
        service.post_notice(
            plaza_id="plaza-sejong-1",
            rider_id="rider-1",
            purpose=PlazaPurpose.PEER_NOTICE,
            body="전화번호 010-0000-0000",
            now=NOW,
            ttl=timedelta(hours=1),
        )
    assert pii.value.code == "PII_FORBIDDEN"


def test_arkaon_advice_is_advisory_and_cannot_control_labor():
    service = foundation()
    advice = service.advise(plaza_id="plaza-sejong-1", summary="오후 소나기 가능성, 휴식 권고")
    assert advice.advisory_only
    assert ForbiddenPlazaUse.DISPATCH_QUEUE.value in advice.forbidden_uses
    with pytest.raises(PlazaRejected):
        PlazaAdvice(plaza_id="plaza-sejong-1", advisory_only=False, summary="배차 제외")
    for use in (
        "dispatch_queue",
        "presence_surveillance",
        "idle_time_penalty",
        "ranking_for_offers",
        "continuous_tracking",
        "availability_inference",
    ):
        with pytest.raises(PlazaRejected) as caught:
            service.assert_use_allowed(use)
        assert caught.value.code.startswith("FORBIDDEN_PLAZA_USE")


def test_withdrawn_or_expired_membership_cannot_post():
    service = foundation()
    service.join(
        plaza_id="plaza-sejong-1",
        rider_id="rider-1",
        consent=True,
        now=NOW,
        ttl=timedelta(hours=1),
    )
    service.leave(plaza_id="plaza-sejong-1", rider_id="rider-1", now=NOW)
    with pytest.raises(PlazaRejected) as caught:
        service.post_notice(
            plaza_id="plaza-sejong-1",
            rider_id="rider-1",
            purpose=PlazaPurpose.REST,
            body="휴식 중",
            now=NOW,
            ttl=timedelta(hours=1),
        )
    assert caught.value.code == "MEMBERSHIP_INACTIVE"
    occupancy = service.occupancy(plaza_id="plaza-sejong-1", now=NOW)
    assert occupancy.member_count == 0
