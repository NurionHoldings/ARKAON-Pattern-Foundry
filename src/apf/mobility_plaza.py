"""Rider mobility plaza foundation: commons, not a dispatch or surveillance surface.

A plaza is a branch-scoped rest/wait/notice commons. Occupancy is a count.
Rider identity is hashed. Precise GPS is forbidden. ARKAON may advise capacity
or safety; it cannot rank, exclude, or penalize from plaza presence.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from typing import Mapping


class PlazaPurpose(StrEnum):
    REST = "rest"
    WAIT = "wait"
    PEER_NOTICE = "peer_notice"
    SAFETY_ADVISORY = "safety_advisory"
    SHARED_LOGISTICS = "shared_logistics"


class ForbiddenPlazaUse(StrEnum):
    DISPATCH_QUEUE = "dispatch_queue"
    PRESENCE_SURVEILLANCE = "presence_surveillance"
    IDLE_TIME_PENALTY = "idle_time_penalty"
    RANKING_FOR_OFFERS = "ranking_for_offers"
    CONTINUOUS_TRACKING = "continuous_tracking"
    AVAILABILITY_INFERENCE = "availability_inference"


class PlazaRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CoarsePlazaCell:
    """The only durable location shape. Precision matches geospatial coarse bounds."""

    cell: str
    precision: int

    def __post_init__(self) -> None:
        if not (3 <= self.precision <= 5):
            raise PlazaRejected("PRECISE_LOCATION_FORBIDDEN", "plaza cell precision must be 3..5")
        if len(self.cell) != self.precision or not self.cell.isalnum():
            raise PlazaRejected("PRECISE_LOCATION_FORBIDDEN", "invalid coarse plaza cell")


@dataclass(frozen=True)
class MobilityPlaza:
    plaza_id: str
    branch_id: str
    name: str
    purposes: frozenset[PlazaPurpose]
    cell: CoarsePlazaCell
    created_at: datetime
    active: bool = True

    def __post_init__(self) -> None:
        if not self.plaza_id.strip() or not self.branch_id.strip() or not self.name.strip():
            raise PlazaRejected("PLAZA_IDENTITY_REQUIRED", "plaza identity is required")
        if not self.purposes:
            raise PlazaRejected("PLAZA_PURPOSE_REQUIRED", "at least one allowed purpose")
        if self.created_at.tzinfo is None:
            raise PlazaRejected("TIMEZONE_REQUIRED", "plaza timestamps must be timezone-aware")


@dataclass(frozen=True)
class PlazaMembership:
    plaza_id: str
    rider_id_hash: str
    consented_at: datetime
    expires_at: datetime
    active: bool = True

    def public_view(self) -> Mapping[str, object]:
        return {
            "plaza_id": self.plaza_id,
            "membership": "active" if self.active else "withdrawn",
            "expires_at": self.expires_at.isoformat(),
        }


@dataclass(frozen=True)
class PlazaNotice:
    notice_id: str
    plaza_id: str
    purpose: PlazaPurpose
    body: str
    created_at: datetime
    expires_at: datetime
    author_hash: str
    dispatch_signal: bool = False

    def public_view(self) -> Mapping[str, object]:
        return {
            "notice_id": self.notice_id,
            "plaza_id": self.plaza_id,
            "purpose": self.purpose.value,
            "body": self.body,
            "expires_at": self.expires_at.isoformat(),
        }


@dataclass(frozen=True)
class PlazaOccupancy:
    plaza_id: str
    member_count: int
    observed_at: datetime
    identities_disclosed: bool = False
    usable_for_dispatch: bool = False


@dataclass(frozen=True)
class PlazaAdvice:
    plaza_id: str
    advisory_only: bool
    summary: str
    forbidden_uses: tuple[str, ...] = tuple(item.value for item in ForbiddenPlazaUse)

    def __post_init__(self) -> None:
        if not self.advisory_only:
            raise PlazaRejected("ARKAON_PLAZA_MUST_BE_ADVISORY", "plaza advice cannot become control")


def _hash_rider(rider_id: str) -> str:
    if not rider_id.strip() or any(ord(ch) < 32 for ch in rider_id):
        raise PlazaRejected("INVALID_RIDER_SCOPE", "rider identity is invalid")
    return sha256(rider_id.encode()).hexdigest()


class MobilityPlazaFoundation:
    """Registers plazas, opt-in membership, notices, and occupancy counts."""

    MAX_NOTICE_TTL = timedelta(hours=24)
    MAX_MEMBERSHIP_TTL = timedelta(hours=12)

    def __init__(self) -> None:
        self._plazas: dict[str, MobilityPlaza] = {}
        self._members: dict[tuple[str, str], PlazaMembership] = {}
        self._notices: dict[str, PlazaNotice] = {}

    def register(self, plaza: MobilityPlaza) -> MobilityPlaza:
        if plaza.plaza_id in self._plazas:
            raise PlazaRejected("DUPLICATE_PLAZA", "plaza already registered")
        self._plazas[plaza.plaza_id] = plaza
        return plaza

    def join(
        self,
        *,
        plaza_id: str,
        rider_id: str,
        consent: bool,
        now: datetime,
        ttl: timedelta,
    ) -> PlazaMembership:
        plaza = self._require_active_plaza(plaza_id)
        if not consent:
            raise PlazaRejected("CONSENT_REQUIRED", "plaza membership requires explicit consent")
        if ttl <= timedelta(0) or ttl > self.MAX_MEMBERSHIP_TTL:
            raise PlazaRejected("INVALID_MEMBERSHIP_TTL", "membership TTL exceeds foundation bound")
        rider_hash = _hash_rider(rider_id)
        membership = PlazaMembership(
            plaza_id=plaza.plaza_id,
            rider_id_hash=rider_hash,
            consented_at=now,
            expires_at=now + ttl,
        )
        self._members[(plaza_id, rider_hash)] = membership
        return membership

    def leave(self, *, plaza_id: str, rider_id: str, now: datetime) -> PlazaMembership:
        del now
        key = (plaza_id, _hash_rider(rider_id))
        membership = self._members.get(key)
        if membership is None:
            raise PlazaRejected("MEMBERSHIP_NOT_FOUND", "no plaza membership")
        closed = replace(membership, active=False)
        self._members[key] = closed
        return closed

    def post_notice(
        self,
        *,
        plaza_id: str,
        rider_id: str,
        purpose: PlazaPurpose,
        body: str,
        now: datetime,
        ttl: timedelta,
    ) -> PlazaNotice:
        plaza = self._require_active_plaza(plaza_id)
        if purpose not in plaza.purposes:
            raise PlazaRejected("PURPOSE_NOT_ALLOWED", "notice purpose is outside plaza charter")
        membership = self._require_active_member(plaza_id, rider_id, now)
        if not body.strip() or any(ord(ch) < 32 and ch not in "\t" for ch in body):
            raise PlazaRejected("INVALID_NOTICE", "notice body is empty or unsafe")
        if ttl <= timedelta(0) or ttl > self.MAX_NOTICE_TTL:
            raise PlazaRejected("INVALID_NOTICE_TTL", "notice TTL exceeds foundation bound")
        lowered = body.casefold()
        if any(token in lowered for token in ("주민", "계좌", "전화번호", "gps", "위도", "경도")):
            raise PlazaRejected("PII_FORBIDDEN", "plaza notices cannot carry personal or precise location data")
        notice_id = sha256(
            f"{plaza_id}|{membership.rider_id_hash}|{now.isoformat()}|{body}".encode()
        ).hexdigest()[:24]
        notice = PlazaNotice(
            notice_id=notice_id,
            plaza_id=plaza_id,
            purpose=purpose,
            body=body.strip(),
            created_at=now,
            expires_at=now + ttl,
            author_hash=membership.rider_id_hash,
        )
        self._notices[notice_id] = notice
        return notice

    def occupancy(self, *, plaza_id: str, now: datetime) -> PlazaOccupancy:
        self._require_active_plaza(plaza_id)
        count = sum(
            1
            for (pid, _), member in self._members.items()
            if pid == plaza_id and member.active and now < member.expires_at
        )
        return PlazaOccupancy(plaza_id=plaza_id, member_count=count, observed_at=now)

    def public_notices(self, *, plaza_id: str, now: datetime) -> tuple[Mapping[str, object], ...]:
        self._require_active_plaza(plaza_id)
        return tuple(
            notice.public_view()
            for notice in self._notices.values()
            if notice.plaza_id == plaza_id and now < notice.expires_at and not notice.dispatch_signal
        )

    def advise(self, *, plaza_id: str, summary: str) -> PlazaAdvice:
        self._require_active_plaza(plaza_id)
        if not summary.strip():
            raise PlazaRejected("ADVICE_REQUIRED", "advisory summary is required")
        return PlazaAdvice(plaza_id=plaza_id, advisory_only=True, summary=summary.strip())

    def assert_use_allowed(self, requested: str) -> None:
        try:
            forbidden = ForbiddenPlazaUse(requested)
        except ValueError:
            return
        raise PlazaRejected(
            f"FORBIDDEN_PLAZA_USE:{forbidden.value}",
            "plaza presence cannot become labor control",
        )

    def _require_active_plaza(self, plaza_id: str) -> MobilityPlaza:
        plaza = self._plazas.get(plaza_id)
        if plaza is None or not plaza.active:
            raise PlazaRejected("PLAZA_NOT_FOUND", "plaza is missing or inactive")
        return plaza

    def _require_active_member(self, plaza_id: str, rider_id: str, now: datetime) -> PlazaMembership:
        membership = self._members.get((plaza_id, _hash_rider(rider_id)))
        if membership is None or not membership.active or now >= membership.expires_at:
            raise PlazaRejected("MEMBERSHIP_INACTIVE", "active consented membership is required")
        return membership
