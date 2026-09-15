from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Protocol

from .continuous_collection import AssetLifecycle, assetization_route


class AssetPromotionDenied(ValueError):
    pass


@dataclass(frozen=True)
class AssetRecord:
    asset_id: str
    source_id: str
    title: str
    stage: AssetLifecycle
    provenance_ref: str
    principle_ref: str | None = None
    implementation_ref: str | None = None
    test_refs: tuple[str, ...] = ()
    approval_ref: str | None = None
    copied_source_code: bool = False
    updated_at: datetime = field(default_factory=lambda: datetime.min.replace(tzinfo=UTC))


@dataclass(frozen=True)
class AssetizationReport:
    generated_at: datetime
    total: int
    by_stage: dict[str, int]
    owned_assets: tuple[str, ...]
    blocked_assets: tuple[str, ...]


@dataclass(frozen=True)
class AssetConceptReport:
    report_type: str
    asset_id: str
    source_id: str
    title: str
    principle_ref: str
    provenance_ref: str
    generated_at: datetime


class ConceptReportSink(Protocol):
    def publish(self, report: AssetConceptReport) -> None: ...


def promote(
    record: AssetRecord,
    target: AssetLifecycle,
    *,
    report_sink: ConceptReportSink | None = None,
) -> AssetRecord:
    route = assetization_route(record.stage)
    if route.next_step != target:
        raise AssetPromotionDenied("NON_SEQUENTIAL_PROMOTION")
    if not record.provenance_ref:
        raise AssetPromotionDenied("PROVENANCE_REQUIRED")
    if target == AssetLifecycle.PRINCIPLE_ABSTRACTED and not record.principle_ref:
        raise AssetPromotionDenied("PRINCIPLE_EVIDENCE_REQUIRED")
    if target == AssetLifecycle.INDEPENDENT_IMPLEMENTATION and (
        not record.implementation_ref or record.copied_source_code
    ):
        raise AssetPromotionDenied("INDEPENDENT_IMPLEMENTATION_REQUIRED")
    if target == AssetLifecycle.INDEPENDENTLY_VERIFIED and not record.test_refs:
        raise AssetPromotionDenied("INDEPENDENT_TEST_EVIDENCE_REQUIRED")
    if target == AssetLifecycle.OWNED_ASSET and not record.approval_ref:
        raise AssetPromotionDenied("HUMAN_APPROVAL_REQUIRED")
    updated = replace(record, stage=target, updated_at=datetime.now(UTC))
    if target == AssetLifecycle.PRINCIPLE_ABSTRACTED and report_sink is not None:
        report_sink.publish(
            AssetConceptReport(
                report_type="NEW_ASSET_CONCEPTUALIZED",
                asset_id=updated.asset_id,
                source_id=updated.source_id,
                title=updated.title,
                principle_ref=updated.principle_ref or "",
                provenance_ref=updated.provenance_ref,
                generated_at=updated.updated_at,
            )
        )
    return updated


def build_assetization_report(records: list[AssetRecord]) -> AssetizationReport:
    counts = {stage.value: 0 for stage in AssetLifecycle}
    for record in records:
        counts[record.stage.value] += 1
    owned = tuple(sorted(r.asset_id for r in records if r.stage == AssetLifecycle.OWNED_ASSET))
    blocked = tuple(
        sorted(
            r.asset_id
            for r in records
            if r.stage != AssetLifecycle.OWNED_ASSET
            and (
                not r.provenance_ref
                or r.copied_source_code
                or (r.stage == AssetLifecycle.INDEPENDENTLY_VERIFIED and not r.approval_ref)
            )
        )
    )
    return AssetizationReport(datetime.now(UTC), len(records), counts, owned, blocked)
