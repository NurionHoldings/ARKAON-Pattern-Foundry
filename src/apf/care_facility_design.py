"""Deterministic residential-care design brief checks and proposal-only image packets.

No provider calls, filesystem writes, legal approval or measured-fit certification.
"""
from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Area = Annotated[float, Field(gt=0, le=200_000, allow_inf_nan=False)]
SpaceKind = Literal[
    "living_dining", "program", "physical_occupational_therapy", "nursing",
    "caregiver_work", "office_counseling", "volunteer", "male_bathing",
    "female_bathing", "staff_rest", "staff_changing", "laundry_drying",
    "clean_linen", "dirty_utility", "food_storage", "public_toilet",
    "clean_utility", "evacuation_reserve", "circulation_reserve", "structure_reserve",
]
# Baseline review checklist plus explicit owner-requested staff facilities.
# Exceptions and legal applicability remain subject to external review.
REVIEW_SPACES = frozenset({
    "living_dining", "program", "physical_occupational_therapy", "nursing",
    "caregiver_work", "office_counseling", "volunteer", "male_bathing",
    "female_bathing", "staff_rest", "staff_changing", "laundry_drying",
})
SCENES = {
    "overview": "One oblique cutaway overview: left/right private residential wings, central "
                "shared living/dining and distinct support rooms. Show enclosed ensuite WCs. "
                "Do not invent measured columns, stairs, exits or verified capacity.",
    "bedroom": "One private residential bedroom example with the requested number of beds, "
               "individual storage/call buttons and a separate accessible-toilet concept. "
               "Distinguish this room example from the full facility plan.",
    "staff_support": "One staff support view with separate enclosed staff rest and changing/locker "
                     "rooms, distinguished from caregiver work and resident living areas.",
    "kitchen_bathing": "One service-area concept: separate kitchen/food service and sex-separated "
                       "assisted bathing/changing facilities. Keep clean/dirty circulation separate.",
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RoomSpec(StrictModel):
    occupancy: int = Field(ge=1, le=4)
    count: int = Field(ge=1, le=1000)
    ensuite_wc: bool = True
    bedroom_target_m2: Area | None = None
    toilet_target_m2: Area | None = None

    @model_validator(mode="after")
    def toilet_budget_requires_toilet(self):
        if self.toilet_target_m2 is not None and not self.ensuite_wc:
            raise ValueError("toilet budget requires an ensuite toilet")
        return self


class SupportSpace(StrictModel):
    kind: SpaceKind
    target_m2: Area | None = None


class CareFacilityBrief(StrictModel):
    target_residents: int = Field(ge=1, le=4000)
    room_types: list[RoomSpec] = Field(min_length=1, max_length=4)
    ensuite_each_room: bool = True
    kitchen_pyeong: Area
    support_spaces: list[SupportSpace] = Field(max_length=20)
    available_area_m2: Area | None = None

    @model_validator(mode="after")
    def unique_categories(self):
        if len({r.occupancy for r in self.room_types}) != len(self.room_types):
            raise ValueError("duplicate room occupancy category")
        if len({s.kind for s in self.support_spaces}) != len(self.support_spaces):
            raise ValueError("duplicate support-space category")
        return self


class CareDesignRequest(StrictModel):
    brief: CareFacilityBrief
    confirmed_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    scene: Literal["overview", "bedroom", "staff_support", "kitchen_bathing"] = "overview"
    bedroom_occupancy: int = Field(default=2, ge=1, le=4)


def assess_care_brief(brief: CareFacilityBrief) -> dict:
    canonical = brief.model_dump(mode="json")
    # Categories are order-independent; reorder alone must not invalidate confirmation.
    canonical["room_types"] = sorted(canonical["room_types"], key=lambda r: r["occupancy"])
    canonical["support_spaces"] = sorted(canonical["support_spaces"], key=lambda s: s["kind"])
    digest = hashlib.sha256(json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()
    rooms = sum(r.count for r in brief.room_types)
    residents = sum(r.count * r.occupancy for r in brief.room_types)
    toilets = sum(r.count for r in brief.room_types if r.ensuite_wc)
    missing = sorted(REVIEW_SPACES - {s.kind for s in brief.support_spaces})
    blockers = []
    if residents != brief.target_residents:
        blockers.append({"code": "CAPACITY_MISMATCH", "requested": brief.target_residents,
                         "computed": residents, "message": "방 구성과 목표 정원이 다릅니다. 사용자 재확인이 필요합니다."})
    if brief.ensuite_each_room and rooms != toilets:
        blockers.append({"code": "ENSUITE_MISSING", "message": "모든 침실의 전용 화장실 요구를 충족하지 않습니다."})
    if missing:
        blockers.append({"code": "SPACE_REVIEW_REQUIRED", "missing_spaces": missing,
                         "message": "기본·요청 공간을 보완하거나 예외 적용을 별도 검토하세요."})
    kitchen = round(brief.kitchen_pyeong * 400 / 121, 2)
    room_area_complete = all(
        r.bedroom_target_m2 is not None and
        (not r.ensuite_wc or r.toilet_target_m2 is not None) for r in brief.room_types
    )
    complete = room_area_complete and all(s.target_m2 is not None for s in brief.support_spaces)
    known = kitchen + sum(
        r.count * ((r.bedroom_target_m2 or 0) + (r.toilet_target_m2 or 0))
        for r in brief.room_types
    ) + sum(s.target_m2 or 0 for s in brief.support_spaces)
    known = round(known, 2)
    if brief.available_area_m2 is not None and known > brief.available_area_m2:
        blockers.append({"code": "AREA_BUDGET_EXCEEDED", "message": "면적 예산이 입력된 가용면적을 초과합니다."})
    return {
        "schema_version": "apf.care-facility-design/v1", "brief_digest": digest,
        "status": "NEEDS_REVISION" if blockers else "USER_CONFIRMATION_REQUIRED",
        "room_count": rooms, "computed_residents": residents, "ensuite_wc_count": toilets,
        "kitchen_m2": kitchen, "known_budget_m2": known, "area_budget_complete": complete,
        "area_difference_m2": round(brief.available_area_m2 - known, 2)
        if complete and brief.available_area_m2 is not None else None,
        "blockers": blockers, "legal_compliance": "NOT_VERIFIED",
        "measured_fit": "NOT_VERIFIED", "automatic_generation": False,
        "production_change_allowed": False,
        "warnings": [
            "요구·법정 기준·설계 목표·실측값을 구분하세요. 이 산술검사는 인허가 판정이 아닙니다.",
            "면적 여유만으로 22실 등 실제 배치·창·화장실 접근·피난 적합성을 증명할 수 없습니다.",
            "설치신고·기관지정, 소유권, 창·계단·대피시설·설비는 현행 근거와 전문가 검토가 필요합니다.",
            "이 체크리스트는 공식 법령 전체가 아닙니다. 공간 합병·위탁 예외는 자동 적용하지 않습니다.",
        ],
    }


def build_care_design_packet(request: CareDesignRequest) -> dict:
    result = assess_care_brief(request.brief)
    result["image_prompt"] = None
    result["scene"] = request.scene
    if result["blockers"]:
        return result
    if request.confirmed_digest != result["brief_digest"]:
        if request.confirmed_digest is not None:
            result["status"] = "CONFIRMATION_STALE"
        return result
    if request.scene == "bedroom" and request.bedroom_occupancy not in {
        r.occupancy for r in request.brief.room_types
    }:
        result["status"] = "NEEDS_REVISION"
        result["blockers"].append({"code": "BEDROOM_TYPE_NOT_REQUESTED"})
        return result
    brief = request.brief
    room_mix = "; ".join(
        f"{r.occupancy}-resident bedroom x {r.count}, ensuite_wc={r.ensuite_wc}"
        for r in sorted(brief.room_types, key=lambda r: r.occupancy)
    )
    result["status"] = "PROPOSAL_PACKET_READY"
    result["image_prompt"] = (
        f"Photoreal post-construction residential elderly-care concept. Requested program: "
        f"{brief.target_residents} residents, {result['room_count']} rooms, {room_mix}. "
        f"Ensuite WCs: {result['ensuite_wc_count']}. Separate kitchen design target "
        f"{brief.kitchen_pyeong} pyeong ({result['kitchen_m2']} m2); do not double-count dining. "
        f"Support program: {', '.join(sorted(s.kind for s in brief.support_spaces))}. "
        f"{SCENES[request.scene]} "
        + (f"For this bedroom example use exactly {request.bedroom_occupancy} beds. "
           if request.scene == "bedroom" else "")
        + "Separate private living/sleeping, common living/dining, nursing/caregiver work, "
        "staff rest/changing, sex-separated assisted bathing and clean/dirty service paths. "
        "Keep source photograph geometry only when provided; no unverified measured structures. "
        "No medical-clinic treatment bays, no open dormitory, no image collage, no text. "
        "This is a visual proposal, never proof of room counts, legal approval, structural safety "
        "or measured fit. Verify generated visual against the confirmed brief, keep failures visible."
    )
    return result


def main() -> None:
    """Read a caller-selected brief; write a proposal packet to stdout only."""
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="요양원 요구 검산과 제안용 이미지 요청 생성")
    parser.add_argument("input", type=Path)
    parser.add_argument("--confirmed-digest")
    parser.add_argument("--scene", choices=tuple(SCENES), default="overview")
    parser.add_argument("--bedroom-occupancy", type=int, default=2)
    args = parser.parse_args()
    request = CareDesignRequest.model_validate({
        "brief": json.loads(args.input.read_text(encoding="utf-8")),
        "confirmed_digest": args.confirmed_digest,
        "scene": args.scene,
        "bedroom_occupancy": args.bedroom_occupancy,
    })
    print(json.dumps(build_care_design_packet(request), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
