"""M6 synthetic reuse proof measurement harness for planning-time reduction baseline."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
from pathlib import Path

from .pattern_catalog import PatternCatalogError, build_reuse_proof


class ReuseMeasurementRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class MeasurementStatus(str, Enum):
    PASS = "PASS"
    SKIP = "SKIP"
    FAIL = "FAIL"


@dataclass(frozen=True)
class ReuseMeasurementPolicy:
    production_claim_allowed: bool = False
    minimum_reduction_percent: int = 50
    target_platform_id: str = "SIDEJOB_MARKET"

    @classmethod
    def load(cls, path: Path) -> ReuseMeasurementPolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.arkaon-reuse-proof-measurement/v1":
            raise ReuseMeasurementRejected("POLICY_SCHEMA", "unsupported reuse measurement schema")
        if document.get("production_claim_allowed"):
            raise ReuseMeasurementRejected("POLICY_FORBIDDEN", "production reuse claims remain external")
        return cls(
            production_claim_allowed=bool(document.get("production_claim_allowed")),
            minimum_reduction_percent=int(document.get("minimum_reduction_percent", 50)),
            target_platform_id=str(document.get("target_platform_id", "SIDEJOB_MARKET")),
        )


@dataclass(frozen=True)
class ReuseMeasurementReport:
    foundry_root: Path
    evaluated_at: datetime
    target_platform_id: str
    baseline: dict[str, object]
    reuse: dict[str, object]
    reduction_percent: float
    reuse_proof_digest: str
    overall: MeasurementStatus
    report_digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.reuse-proof-measurement-report/v1",
            "foundry_root": self.foundry_root.as_posix(),
            "evaluated_at": self.evaluated_at.isoformat(),
            "target_platform_id": self.target_platform_id,
            "baseline": self.baseline,
            "reuse": self.reuse,
            "reduction_percent": self.reduction_percent,
            "reuse_proof_digest": self.reuse_proof_digest,
            "overall": self.overall.value,
            "report_digest": self.report_digest,
            "production_claim": False,
            "measurement_mode": "M6_SYNTHETIC_BASELINE",
        }


def _planning_hours(metrics: dict[str, object]) -> float:
    return float(metrics["planning_hours"])


class ReuseProofMeasurementHarness:
    def __init__(self, *, foundry_root: Path, policy: ReuseMeasurementPolicy | None = None) -> None:
        self.foundry_root = foundry_root.resolve()
        config = self.foundry_root / "config" / "arkaon-reuse-proof-measurement.json"
        self.policy = policy or ReuseMeasurementPolicy.load(config)
        self.store_root = self.foundry_root / "state" / "reuse-proof-measurement"
        self.store_root.mkdir(parents=True, exist_ok=True)

    def run(self, *, now: datetime | None = None, dry_run: bool = False) -> ReuseMeasurementReport:
        evaluated_at = now or datetime.now(tz=UTC)
        if evaluated_at.tzinfo is None:
            raise ReuseMeasurementRejected("TIMESTAMP", "timezone-aware timestamp required")
        baseline_path = self.foundry_root / "knowledge" / "reuse-proof" / "m6-synthetic-baseline.json"
        if not baseline_path.is_file():
            report = self._skip_report(evaluated_at, "M6 synthetic baseline file missing")
            if not dry_run:
                self._persist(report)
            return report
        baseline_doc = json.loads(baseline_path.read_text(encoding="utf-8"))
        if baseline_doc.get("schema_version") != "apf.reuse-proof-baseline/v1":
            raise ReuseMeasurementRejected("BASELINE_SCHEMA", "unsupported baseline schema")
        baseline_metrics = baseline_doc["baseline_metrics"]
        reuse_metrics = baseline_doc["reuse_metrics"]
        approved = baseline_doc.get("approved_patterns") or []
        if len(approved) < 3:
            raise ReuseMeasurementRejected("INSUFFICIENT_PATTERNS", "baseline must include three approved patterns")
        try:
            reuse_proof = build_reuse_proof(approved, project_id="SIDEJOB_MARKET_M6")
        except PatternCatalogError as error:
            raise ReuseMeasurementRejected("REUSE_PROOF", str(error)) from error
        baseline_hours = _planning_hours(baseline_metrics)
        reuse_hours = _planning_hours(reuse_metrics)
        if baseline_hours <= 0:
            raise ReuseMeasurementRejected("INVALID_BASELINE", "baseline planning hours must be positive")
        reduction = round((baseline_hours - reuse_hours) / baseline_hours * 100, 2)
        overall = (
            MeasurementStatus.PASS
            if reduction >= self.policy.minimum_reduction_percent
            else MeasurementStatus.FAIL
        )
        document = {
            "evaluated_at": evaluated_at.isoformat(),
            "foundry_root": self.foundry_root.as_posix(),
            "reduction_percent": reduction,
            "target_platform_id": self.policy.target_platform_id,
        }
        digest = sha256(json.dumps(document, sort_keys=True).encode()).hexdigest()
        report = ReuseMeasurementReport(
            foundry_root=self.foundry_root,
            evaluated_at=evaluated_at,
            target_platform_id=self.policy.target_platform_id,
            baseline=dict(baseline_metrics),
            reuse=dict(reuse_metrics),
            reduction_percent=reduction,
            reuse_proof_digest=str(reuse_proof["proof_digest"]),
            overall=overall,
            report_digest=digest,
        )
        if not dry_run:
            self._persist(report)
        if overall is MeasurementStatus.FAIL:
            raise ReuseMeasurementRejected(
                "REDUCTION_TARGET_NOT_MET",
                f"synthetic reduction {reduction}% below target {self.policy.minimum_reduction_percent}%",
            )
        return report

    def _skip_report(self, evaluated_at: datetime, message: str) -> ReuseMeasurementReport:
        digest = sha256(message.encode()).hexdigest()
        return ReuseMeasurementReport(
            foundry_root=self.foundry_root,
            evaluated_at=evaluated_at,
            target_platform_id=self.policy.target_platform_id,
            baseline={},
            reuse={},
            reduction_percent=0.0,
            reuse_proof_digest="",
            overall=MeasurementStatus.SKIP,
            report_digest=digest,
        )

    def _persist(self, report: ReuseMeasurementReport) -> None:
        target = self.store_root / f"{report.evaluated_at.strftime('%Y-%m-%d')}-{report.report_digest[:16]}.json"
        target.write_text(
            json.dumps(report.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
