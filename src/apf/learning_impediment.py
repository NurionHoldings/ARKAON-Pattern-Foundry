"""Detect ARKAON functional limits that hinder learning; request modification from eternian/beom."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from hashlib import sha256
from pathlib import Path

from .accumulation_policy import AccumulationPolicy, parse_optional_limit


class LearningImpedimentRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ImpedimentSeverity(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ModificationTarget(str, Enum):
    ETERNIAN = "ETERNIAN"
    BEOM = "BEOM"


class ImpedimentCategory(str, Enum):
    SELF_LIMIT = "SELF_LIMIT"
    LEARNING_STORAGE = "LEARNING_STORAGE"
    BUSINESS_IMPROVEMENT_PROGRAM = "BUSINESS_IMPROVEMENT_PROGRAM"


_EVOLUTION_TO_AUDIT_AREAS: dict[str, tuple[str, ...]] = {
    "TYPOGRAPHY_MOTION": ("HOME_READABILITY", "ACCESSIBILITY"),
    "TEMPLATE_COMPOSITION": ("PLACEMENT", "CONTENT"),
    "HOME_SURFACE_OPTIMIZATION": ("HOME_READABILITY", "PLACEMENT"),
    "AUTH_ONBOARDING_UX": ("NAVIGATION", "ACCESSIBILITY"),
    "SIGNATURE_MOTION": ("CONTENT", "HOME_READABILITY"),
    "VIDEO_TEMPLATE_EFFECTS": ("CONTENT", "PLACEMENT"),
    "CROSS_FEATURE_COHERENCE": ("ROUTE_CONSISTENCY", "NAVIGATION"),
    "PAYMENT_CHECKOUT_FLOW": ("NAVIGATION", "ROUTE_CONSISTENCY"),
    "EMERGING_MARKET_SIGNALS": ("OFFICIAL_BENCHMARK", "CONTENT"),
    "LIFECYCLE_STEWARDSHIP": ("ROUTE_CONSISTENCY", "OFFICIAL_BENCHMARK"),
}

_LEARNING_STORAGE_DIRS = (
    "state",
    "knowledge",
    "inbox",
    "state/hourly-learning",
    "knowledge/shorts-production-assets",
)


@dataclass(frozen=True)
class LearningImpedimentPolicy:
    enabled: bool = True
    emit_research_packet: bool = True
    emit_eternian_packet: bool = True
    emit_beom_packet: bool = True
    minimum_impediments_for_packet: int = 1
    audit_lookback_events: int = 200
    learning_blocking_decisions: frozenset[str] = frozenset(
        {
            "RESPONSE_TOO_LARGE",
            "FETCH_FAILED",
            "SOURCE_POLICY_BLOCKED",
            "COLLECTION_DISABLED",
            "CREDENTIAL_ACCESS_BLOCKED",
        }
    )
    scan_learning_storage: bool = True
    scan_business_improvement_program: bool = True
    mailbox_pending_backlog_threshold: int = 50
    automatic_implement_allowed: bool = False
    production_change_allowed: bool = False

    @classmethod
    def load(cls, path: Path) -> LearningImpedimentPolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.learning-impediment/v1":
            raise LearningImpedimentRejected("POLICY_SCHEMA", "unsupported learning impediment schema")
        if document.get("automatic_implement_allowed") or document.get("production_change_allowed"):
            raise LearningImpedimentRejected("POLICY_FORBIDDEN", "learning impediment must remain request-only")
        decisions = frozenset(
            str(item).strip()
            for item in (document.get("learning_blocking_decisions") or ())
            if str(item).strip()
        )
        return cls(
            enabled=bool(document.get("enabled", True)),
            emit_research_packet=bool(document.get("emit_research_packet", True)),
            emit_eternian_packet=bool(document.get("emit_eternian_packet", True)),
            emit_beom_packet=bool(document.get("emit_beom_packet", True)),
            minimum_impediments_for_packet=max(1, int(document.get("minimum_impediments_for_packet", 1))),
            audit_lookback_events=max(10, int(document.get("audit_lookback_events", 200))),
            learning_blocking_decisions=decisions or cls.learning_blocking_decisions,
            scan_learning_storage=bool(document.get("scan_learning_storage", True)),
            scan_business_improvement_program=bool(document.get("scan_business_improvement_program", True)),
            mailbox_pending_backlog_threshold=max(
                1, int(document.get("mailbox_pending_backlog_threshold", 50))
            ),
            automatic_implement_allowed=bool(document.get("automatic_implement_allowed")),
            production_change_allowed=bool(document.get("production_change_allowed")),
        )


@dataclass(frozen=True)
class ModificationRequest:
    request_id: str
    target: ModificationTarget
    limit_kind: str
    modification_summary: str
    user_message: str
    evidence_refs: tuple[str, ...]
    category: ImpedimentCategory = ImpedimentCategory.SELF_LIMIT

    def to_document(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "target": self.target.value,
            "limit_kind": self.limit_kind,
            "category": self.category.value,
            "modification_summary": self.modification_summary,
            "user_message": self.user_message,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True)
class LearningImpediment:
    impediment_id: str
    limit_kind: str
    severity: ImpedimentSeverity
    learning_domain: str | None
    user_message: str
    modification_requests: tuple[ModificationRequest, ...]
    evidence_refs: tuple[str, ...]
    category: ImpedimentCategory = ImpedimentCategory.SELF_LIMIT

    def to_document(self) -> dict[str, object]:
        return {
            "impediment_id": self.impediment_id,
            "limit_kind": self.limit_kind,
            "category": self.category.value,
            "severity": self.severity.value,
            "learning_domain": self.learning_domain,
            "user_message": self.user_message,
            "modification_requests": [item.to_document() for item in self.modification_requests],
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True)
class LearningImpedimentReport:
    foundry_root: Path
    evaluated_at: datetime
    impediments: tuple[LearningImpediment, ...]
    report_digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.learning-impediment-report/v1",
            "foundry_root": self.foundry_root.as_posix(),
            "evaluated_at": self.evaluated_at.isoformat(),
            "impediment_count": len(self.impediments),
            "report_digest": self.report_digest,
            "impediments": [item.to_document() for item in self.impediments],
            "automatic_implement_allowed": False,
            "production_change_allowed": False,
        }


def _request_id(limit_kind: str, target: ModificationTarget, suffix: str) -> str:
    return sha256(f"{limit_kind}|{target.value}|{suffix}".encode()).hexdigest()[:16]


@dataclass(frozen=True)
class EngineLimitSnapshot:
    is_unbounded: bool
    max_inbox_packets: int | None
    max_platforms_per_run: int | None
    max_files_per_platform: int | None
    max_seconds_per_platform: int | None

    @classmethod
    def from_foundry(cls, foundry_root: Path) -> EngineLimitSnapshot:
        path = foundry_root / "config" / "resource-limits.json"
        if not path.is_file():
            return cls(True, None, None, None, None)
        document = json.loads(path.read_text(encoding="utf-8"))
        schema = str(document.get("schema_version", "apf.resource-limits/v1"))
        accumulation_mode = str(document.get("accumulation_mode", "bounded")).strip().lower()
        if schema == "apf.resource-limits/v2" or accumulation_mode == "unbounded":
            return cls(
                is_unbounded=True,
                max_inbox_packets=parse_optional_limit(document.get("max_inbox_packets"), default=None),
                max_platforms_per_run=parse_optional_limit(document.get("max_platforms_per_run"), default=None),
                max_files_per_platform=parse_optional_limit(document.get("max_files_per_platform"), default=None),
                max_seconds_per_platform=parse_optional_limit(document.get("max_seconds_per_platform"), default=None),
            )
        return cls(
            is_unbounded=False,
            max_inbox_packets=int(document.get("max_inbox_packets", 32)),
            max_platforms_per_run=int(document.get("max_platforms_per_run", 8)),
            max_files_per_platform=int(document.get("max_files_per_platform", 5000)),
            max_seconds_per_platform=int(document.get("max_seconds_per_platform", 120)),
        )


def _scan_bounded_resource_limits(foundry_root: Path, limits: EngineLimitSnapshot) -> list[LearningImpediment]:
    if limits.is_unbounded:
        return []
    bounded_fields = [
        ("max_inbox_packets", limits.max_inbox_packets, "inbox 패킷 상한"),
        ("max_platforms_per_run", limits.max_platforms_per_run, "run당 플랫폼 상한"),
        ("max_files_per_platform", limits.max_files_per_platform, "플랫폼 파일 스캔 상한"),
        ("max_seconds_per_platform", limits.max_seconds_per_platform, "플랫폼 분석 타임아웃"),
    ]
    active = [(name, value, label) for name, value, label in bounded_fields if value is not None]
    if not active:
        return []
    summary = "; ".join(f"{label}={value}" for _, value, label in active)
    limit_kind = "BOUNDED_RESOURCE_LIMITS"
    impediment_id = sha256(f"{limit_kind}|{summary}".encode()).hexdigest()[:16]
    return [
        LearningImpediment(
            impediment_id=impediment_id,
            limit_kind=limit_kind,
            severity=ImpedimentSeverity.HIGH,
            learning_domain=None,
            user_message=(
                f"학습 축적·분석에 인위적 리소스 상한이 활성화되어 있습니다: {summary}. "
                "무제한 축적 정책(#060)과 충돌할 수 있습니다."
            ),
            modification_requests=(
                ModificationRequest(
                    request_id=_request_id(limit_kind, ModificationTarget.BEOM, "resource"),
                    target=ModificationTarget.BEOM,
                    limit_kind=limit_kind,
                    modification_summary=(
                        "config/resource-limits.json v2에서 accumulation_mode=unbounded 및 limit null로 전환"
                    ),
                    user_message="범: resource-limits를 unbounded로 갱신해 학습 run 상한을 해제해 주세요.",
                    evidence_refs=("config/resource-limits.json", "docs/60-unbounded-accumulation-engine.md"),
                ),
                ModificationRequest(
                    request_id=_request_id(limit_kind, ModificationTarget.ETERNIAN, "resource"),
                    target=ModificationTarget.ETERNIAN,
                    limit_kind=limit_kind,
                    modification_summary="학습 엔진 상한 제거가 거버넌스·안전 경계와 양립하는지 eternian 검토",
                    user_message="에테르니언: 학습 방해 리소스 cap 해제가 안전한지 검토해 주세요.",
                    evidence_refs=("config/resource-limits.json", "config/arkaon-accumulation-policy.json"),
                ),
            ),
            evidence_refs=("config/resource-limits.json",),
        )
    ]


def _scan_bounded_accumulation(foundry_root: Path) -> list[LearningImpediment]:
    path = foundry_root / "config" / "arkaon-accumulation-policy.json"
    if not path.is_file():
        return []
    policy = AccumulationPolicy.load(path)
    if policy.is_unbounded and policy.learning_memory_unbounded:
        return []
    limit_kind = "BOUNDED_ACCUMULATION_POLICY"
    parts: list[str] = []
    if not policy.is_unbounded:
        parts.append("accumulation_mode=bounded")
    if not policy.learning_memory_unbounded:
        parts.append("learning_memory_unbounded=false")
    if policy.failure_family_limit is not None:
        parts.append(f"failure_family_limit={policy.failure_family_limit}")
    summary = ", ".join(parts)
    impediment_id = sha256(f"{limit_kind}|{summary}".encode()).hexdigest()[:16]
    return [
        LearningImpediment(
            impediment_id=impediment_id,
            limit_kind=limit_kind,
            severity=ImpedimentSeverity.MEDIUM,
            learning_domain=None,
            user_message=f"학습 메모리·축적 정책에 상한이 남아 있습니다: {summary}.",
            modification_requests=(
                ModificationRequest(
                    request_id=_request_id(limit_kind, ModificationTarget.BEOM, "accumulation"),
                    target=ModificationTarget.BEOM,
                    limit_kind=limit_kind,
                    modification_summary="arkaon-accumulation-policy.json을 unbounded 학습 축적으로 갱신",
                    user_message="범: accumulation policy를 unbounded로 맞춰 lesson·recall 상한을 해제해 주세요.",
                    evidence_refs=("config/arkaon-accumulation-policy.json",),
                ),
            ),
            evidence_refs=("config/arkaon-accumulation-policy.json",),
        )
    ]


def _scan_collection_audit(
    foundry_root: Path,
    *,
    policy: LearningImpedimentPolicy,
) -> list[LearningImpediment]:
    audit_path = foundry_root / "state" / "arkaon-collection-audit.jsonl"
    if not audit_path.is_file():
        return []
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    recent = lines[-policy.audit_lookback_events :]
    blocked: dict[str, list[dict[str, object]]] = {}
    for line in recent:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            event = row.get("event") or {}
        except json.JSONDecodeError:
            continue
        decision = str(event.get("decision", ""))
        if not decision:
            continue
        matched = decision
        for prefix in policy.learning_blocking_decisions:
            if decision == prefix or decision.startswith(f"{prefix}:"):
                matched = prefix
                break
        else:
            continue
        blocked.setdefault(matched, []).append(event)
    impediments: list[LearningImpediment] = []
    for decision, events in blocked.items():
        source_ids = sorted({str(item.get("source_id", "unknown")) for item in events})
        limit_kind = f"COLLECTION_{decision}"
        impediment_id = sha256(f"{limit_kind}|{'|'.join(source_ids)}".encode()).hexdigest()[:16]
        if decision == "RESPONSE_TOO_LARGE":
            beom_summary = "collector max_response_bytes 상향 또는 해당 소스 분할/대체 소스 등록"
            eternian_summary = "대용량 공개 소스 수집 확대가 clean-room·거버넌스와 양립하는지 검토"
            severity = ImpedimentSeverity.HIGH
            user_message = (
                f"수집 단계에서 {len(events)}건의 RESPONSE_TOO_LARGE로 학습 소스 수집이 차단되었습니다 "
                f"(source: {', '.join(source_ids[:5])})."
            )
        elif decision.startswith("FETCH_FAILED"):
            beom_summary = "네트워크·소스 locator 점검 또는 collector 재기동"
            eternian_summary = "실패한 외부 학습 소스 목록의 정책 적합성 검토"
            severity = ImpedimentSeverity.MEDIUM
            user_message = (
                f"수집 fetch 실패 {len(events)}건으로 학습이 지연되고 있습니다 "
                f"(source: {', '.join(source_ids[:5])})."
            )
        else:
            beom_summary = f"collector 정책·소스 설정에서 {decision} 차단 요인 완화"
            eternian_summary = f"{decision} 관련 학습 경로의 eternian 승인 범위 검토"
            severity = ImpedimentSeverity.MEDIUM
            user_message = (
                f"수집 정책 {decision}로 학습이 {len(events)}건 차단되었습니다 "
                f"(source: {', '.join(source_ids[:5])})."
            )
        impediments.append(
            LearningImpediment(
                impediment_id=impediment_id,
                limit_kind=limit_kind,
                severity=severity,
                learning_domain=None,
                user_message=user_message,
                modification_requests=(
                    ModificationRequest(
                        request_id=_request_id(limit_kind, ModificationTarget.BEOM, decision),
                        target=ModificationTarget.BEOM,
                        limit_kind=limit_kind,
                        modification_summary=beom_summary,
                        user_message=f"범: {beom_summary}",
                        evidence_refs=("state/arkaon-collection-audit.jsonl", "config/collector.default.json"),
                    ),
                    ModificationRequest(
                        request_id=_request_id(limit_kind, ModificationTarget.ETERNIAN, decision),
                        target=ModificationTarget.ETERNIAN,
                        limit_kind=limit_kind,
                        modification_summary=eternian_summary,
                        user_message=f"에테르니언: {eternian_summary}",
                        evidence_refs=("state/arkaon-collection-audit.jsonl",),
                    ),
                ),
                evidence_refs=("state/arkaon-collection-audit.jsonl",),
            )
        )
    return impediments


def _scan_hourly_learning_cycle(foundry_root: Path) -> list[LearningImpediment]:
    path = foundry_root / "state" / "hourly-learning-current.json"
    if not path.is_file():
        return []
    document = json.loads(path.read_text(encoding="utf-8"))
    cycle = document.get("cycle") or {}
    topic = document.get("topic") or {}
    failed = int(cycle.get("failed", 0))
    denied = int(cycle.get("denied", 0))
    skipped = int(cycle.get("skipped_out_of_topic", 0))
    considered = int(cycle.get("considered", 0))
    collected = int(cycle.get("collected", 0))
    domain_id = str(topic.get("domain_id", "")) or None
    impediments: list[LearningImpediment] = []
    if failed > 0:
        limit_kind = "HOURLY_COLLECTION_FAILURES"
        impediment_id = sha256(f"{limit_kind}|{failed}|{domain_id}".encode()).hexdigest()[:16]
        impediments.append(
            LearningImpediment(
                impediment_id=impediment_id,
                limit_kind=limit_kind,
                severity=ImpedimentSeverity.HIGH,
                learning_domain=domain_id,
                user_message=(
                    f"시간별 학습 주제 '{topic.get('topic_title', domain_id)}' 사이클에서 "
                    f"fetch/처리 실패 {failed}건이 발생했습니다."
                ),
                modification_requests=(
                    ModificationRequest(
                        request_id=_request_id(limit_kind, ModificationTarget.BEOM, "failures"),
                        target=ModificationTarget.BEOM,
                        limit_kind=limit_kind,
                        modification_summary="collector 데몬·네트워크·소스 locator 점검 및 hourly cycle 재실행",
                        user_message="범: hourly learning cycle 실패 원인을 점검하고 collector를 복구해 주세요.",
                        evidence_refs=("state/hourly-learning-current.json",),
                    ),
                ),
                evidence_refs=("state/hourly-learning-current.json",),
            )
        )
    if considered > 0 and collected == 0 and denied > 0:
        limit_kind = "HOURLY_TOPIC_ZERO_YIELD"
        impediment_id = sha256(f"{limit_kind}|{domain_id}|{denied}".encode()).hexdigest()[:16]
        impediments.append(
            LearningImpediment(
                impediment_id=impediment_id,
                limit_kind=limit_kind,
                severity=ImpedimentSeverity.MEDIUM,
                learning_domain=domain_id,
                user_message=(
                    f"주제 '{topic.get('topic_title', domain_id)}'에서 {considered}건 검토했으나 "
                    f"수집 0건·거부 {denied}건 — 정책/소스 매칭 제한이 학습을 막고 있습니다."
                ),
                modification_requests=(
                    ModificationRequest(
                        request_id=_request_id(limit_kind, ModificationTarget.BEOM, "zero-yield"),
                        target=ModificationTarget.BEOM,
                        limit_kind=limit_kind,
                        modification_summary=(
                            "collector.default.json에 해당 domain_id 소스 추가 또는 "
                            "minimum_intent_relevance·hourly topic collect_all_domains 조정"
                        ),
                        user_message="범: hourly 주제에 맞는 수집 소스·임계값을 보강해 주세요.",
                        evidence_refs=(
                            "state/hourly-learning-current.json",
                            "config/collector.default.json",
                            "config/arkaon-hourly-learning-schedule.json",
                        ),
                    ),
                    ModificationRequest(
                        request_id=_request_id(limit_kind, ModificationTarget.ETERNIAN, "zero-yield"),
                        target=ModificationTarget.ETERNIAN,
                        limit_kind=limit_kind,
                        modification_summary="hourly domain 소스 확대가 학습 거버넌스 범위 내인지 검토",
                        user_message="에테르니언: hourly 주제 소스 확대 승인 범위를 검토해 주세요.",
                        evidence_refs=("config/arkaon-hourly-learning-schedule.json",),
                    ),
                ),
                evidence_refs=("state/hourly-learning-current.json",),
            )
        )
    if skipped > 0 and considered == 0 and not bool(topic.get("collect_all_domains")):
        limit_kind = "HOURLY_TOPIC_SOURCE_GAP"
        impediment_id = sha256(f"{limit_kind}|{domain_id}|{skipped}".encode()).hexdigest()[:16]
        impediments.append(
            LearningImpediment(
                impediment_id=impediment_id,
                limit_kind=limit_kind,
                severity=ImpedimentSeverity.MEDIUM,
                learning_domain=domain_id,
                user_message=(
                    f"주제 domain '{domain_id}'에 매칭되는 collector 소스가 없어 "
                    f"{skipped}건이 topic 밖으로 스킵되었습니다."
                ),
                modification_requests=(
                    ModificationRequest(
                        request_id=_request_id(limit_kind, ModificationTarget.BEOM, "source-gap"),
                        target=ModificationTarget.BEOM,
                        limit_kind=limit_kind,
                        modification_summary=f"collector sources에 domain_ids '{domain_id}' 태그 소스 추가",
                        user_message=f"범: {domain_id} 주제용 HTTPS 소스를 collector에 등록해 주세요.",
                        evidence_refs=("config/collector.default.json", "config/arkaon-hourly-learning-schedule.json"),
                    ),
                ),
                evidence_refs=("state/hourly-learning-current.json", "config/collector.default.json"),
            )
        )
    return impediments


def _scan_disabled_learning_subsystems(foundry_root: Path) -> list[LearningImpediment]:
    impediments: list[LearningImpediment] = []
    collector_path = foundry_root / "config" / "collector.default.json"
    if collector_path.is_file():
        document = json.loads(collector_path.read_text(encoding="utf-8"))
        if not document.get("enabled", True):
            limit_kind = "COLLECTION_DISABLED"
            impediment_id = sha256(limit_kind.encode()).hexdigest()[:16]
            impediments.append(
                LearningImpediment(
                    impediment_id=impediment_id,
                    limit_kind=limit_kind,
                    severity=ImpedimentSeverity.HIGH,
                    learning_domain=None,
                    user_message="continuous collector가 disabled 상태라 외부 학습 수집이 중단되었습니다.",
                    modification_requests=(
                        ModificationRequest(
                            request_id=_request_id(limit_kind, ModificationTarget.BEOM, "collector"),
                            target=ModificationTarget.BEOM,
                            limit_kind=limit_kind,
                            modification_summary="collector.default.json enabled=true 및 데몬 기동",
                            user_message="범: collector를 enabled로 전환하고 arkaon-collector-daemon을 기동해 주세요.",
                            evidence_refs=("config/collector.default.json",),
                        ),
                    ),
                    evidence_refs=("config/collector.default.json",),
                )
            )
    hourly_path = foundry_root / "config" / "arkaon-hourly-learning-schedule.json"
    if hourly_path.is_file():
        document = json.loads(hourly_path.read_text(encoding="utf-8"))
        if not document.get("enabled", True):
            limit_kind = "HOURLY_LEARNING_DISABLED"
            impediment_id = sha256(limit_kind.encode()).hexdigest()[:16]
            impediments.append(
                LearningImpediment(
                    impediment_id=impediment_id,
                    limit_kind=limit_kind,
                    severity=ImpedimentSeverity.MEDIUM,
                    learning_domain=None,
                    user_message="hourly learning schedule가 disabled 상태입니다.",
                    modification_requests=(
                        ModificationRequest(
                            request_id=_request_id(limit_kind, ModificationTarget.BEOM, "hourly"),
                            target=ModificationTarget.BEOM,
                            limit_kind=limit_kind,
                            modification_summary="arkaon-hourly-learning-schedule.json enabled=true",
                            user_message="범: hourly learning schedule를 enabled로 전환해 주세요.",
                            evidence_refs=("config/arkaon-hourly-learning-schedule.json",),
                        ),
                    ),
                    evidence_refs=("config/arkaon-hourly-learning-schedule.json",),
                )
            )
    return impediments


def _is_writable_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    probe = path / ".arkaon-write-probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def _count_mailbox_pending(foundry_root: Path) -> int:
    items_root = foundry_root / "state" / "mailbox" / "items"
    if not items_root.is_dir():
        return 0
    pending = 0
    for path in items_root.glob("*.json"):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if str(document.get("status", "")).upper() == "PENDING":
            pending += 1
    return pending


def _scan_learning_storage_capability(
    foundry_root: Path,
    *,
    policy: LearningImpedimentPolicy,
) -> list[LearningImpediment]:
    impediments: list[LearningImpediment] = []
    non_writable = [
        relative
        for relative in _LEARNING_STORAGE_DIRS
        if not _is_writable_dir(foundry_root / relative)
    ]
    if non_writable:
        limit_kind = "STORAGE_PATH_NOT_WRITABLE"
        summary = ", ".join(non_writable)
        impediment_id = sha256(f"{limit_kind}|{summary}".encode()).hexdigest()[:16]
        impediments.append(
            LearningImpediment(
                impediment_id=impediment_id,
                limit_kind=limit_kind,
                category=ImpedimentCategory.LEARNING_STORAGE,
                severity=ImpedimentSeverity.HIGH,
                learning_domain=None,
                user_message=(
                    f"학습 저장 경로에 쓰기 불가: {summary}. "
                    "lesson·digest·inbox 축적이 중단될 수 있습니다."
                ),
                modification_requests=(
                    ModificationRequest(
                        request_id=_request_id(limit_kind, ModificationTarget.BEOM, "write"),
                        target=ModificationTarget.BEOM,
                        limit_kind=limit_kind,
                        category=ImpedimentCategory.LEARNING_STORAGE,
                        modification_summary="foundry state/knowledge/inbox 디렉터리 권한·디스크 용량 점검 및 복구",
                        user_message="범: 학습 저장 경로 쓰기 권한·디스크를 점검하고 저장소를 복구해 주세요.",
                        evidence_refs=tuple(non_writable),
                    ),
                ),
                evidence_refs=tuple(non_writable),
            )
        )

    collector_path = foundry_root / "config" / "collector.default.json"
    sqlite_path = foundry_root / "state" / "arkaon-collection-state.sqlite3"
    if collector_path.is_file():
        collector = json.loads(collector_path.read_text(encoding="utf-8"))
        if collector.get("enabled", True) and not sqlite_path.is_file():
            limit_kind = "STORAGE_COLLECTION_STATE_MISSING"
            impediment_id = sha256(limit_kind.encode()).hexdigest()[:16]
            impediments.append(
                LearningImpediment(
                    impediment_id=impediment_id,
                    limit_kind=limit_kind,
                    category=ImpedimentCategory.LEARNING_STORAGE,
                    severity=ImpedimentSeverity.MEDIUM,
                    learning_domain=None,
                    user_message="collector는 활성인데 content-hash SQLite 저장소가 없어 dedup·축적 메타가 불안정합니다.",
                    modification_requests=(
                        ModificationRequest(
                            request_id=_request_id(limit_kind, ModificationTarget.BEOM, "sqlite"),
                            target=ModificationTarget.BEOM,
                            limit_kind=limit_kind,
                            category=ImpedimentCategory.LEARNING_STORAGE,
                            modification_summary="collector 데몬 1회 실행으로 arkaon-collection-state.sqlite3 초기화",
                            user_message="범: collector를 1회 실행해 학습 저장 SQLite를 생성해 주세요.",
                            evidence_refs=("config/collector.default.json", "state/arkaon-collection-state.sqlite3"),
                        ),
                    ),
                    evidence_refs=("config/collector.default.json",),
                )
            )

    reflective_path = foundry_root / "config" / "arkaon-reflective-learning-policy.json"
    if reflective_path.is_file():
        reflective = json.loads(reflective_path.read_text(encoding="utf-8"))
        disabled_flags = [
            name
            for name, key in (
                ("strengths_and_gaps", "records_strengths_and_gaps"),
                ("rejected_and_failed", "records_rejected_and_failed_lessons"),
                ("regression_gaps", "records_regression_and_expectation_gap"),
            )
            if not reflective.get(key, True)
        ]
        if disabled_flags:
            limit_kind = "STORAGE_REFLECTIVE_RECORDING_DISABLED"
            impediment_id = sha256(f"{limit_kind}|{'|'.join(disabled_flags)}".encode()).hexdigest()[:16]
            impediments.append(
                LearningImpediment(
                    impediment_id=impediment_id,
                    limit_kind=limit_kind,
                    category=ImpedimentCategory.LEARNING_STORAGE,
                    severity=ImpedimentSeverity.MEDIUM,
                    learning_domain=None,
                    user_message=(
                        f"reflective learning 기록 플래그 비활성: {', '.join(disabled_flags)} — "
                        "학습 lesson 축적이 제한됩니다."
                    ),
                    modification_requests=(
                        ModificationRequest(
                            request_id=_request_id(limit_kind, ModificationTarget.ETERNIAN, "reflective"),
                            target=ModificationTarget.ETERNIAN,
                            limit_kind=limit_kind,
                            category=ImpedimentCategory.LEARNING_STORAGE,
                            modification_summary="reflective learning policy에서 lesson 기록 플래그 활성화 검토",
                            user_message="에테르니언: 실패·격차 lesson 저장 범위 확대를 검토해 주세요.",
                            evidence_refs=("config/arkaon-reflective-learning-policy.json",),
                        ),
                        ModificationRequest(
                            request_id=_request_id(limit_kind, ModificationTarget.BEOM, "reflective"),
                            target=ModificationTarget.BEOM,
                            limit_kind=limit_kind,
                            category=ImpedimentCategory.LEARNING_STORAGE,
                            modification_summary="arkaon-reflective-learning-policy.json records_* 플래그 true",
                            user_message="범: reflective lesson 기록 플래그를 활성화해 주세요.",
                            evidence_refs=("config/arkaon-reflective-learning-policy.json",),
                        ),
                    ),
                    evidence_refs=("config/arkaon-reflective-learning-policy.json",),
                )
            )

    pending = _count_mailbox_pending(foundry_root)
    if pending >= policy.mailbox_pending_backlog_threshold:
        limit_kind = "STORAGE_MAILBOX_BACKLOG"
        impediment_id = sha256(f"{limit_kind}|{pending}".encode()).hexdigest()[:16]
        impediments.append(
            LearningImpediment(
                impediment_id=impediment_id,
                limit_kind=limit_kind,
                category=ImpedimentCategory.LEARNING_STORAGE,
                severity=ImpedimentSeverity.MEDIUM,
                learning_domain=None,
                user_message=(
                    f"우편함 PENDING {pending}건 — 학습·개선 요청 저장은 되나 "
                    "전달·이행 병목으로 축적 효과가 저하될 수 있습니다."
                ),
                modification_requests=(
                    ModificationRequest(
                        request_id=_request_id(limit_kind, ModificationTarget.BEOM, "mailbox"),
                        target=ModificationTarget.BEOM,
                        limit_kind=limit_kind,
                        category=ImpedimentCategory.LEARNING_STORAGE,
                        modification_summary="우편함 delivery·fulfillment 처리량 확대 또는 저장·아카이브 tier 추가",
                        user_message="범: 우편함 backlog를 처리하고 학습 저장·전달 용량을 확장해 주세요.",
                        evidence_refs=("state/mailbox/items", "docs/53-mailbox-delivery-flow.md"),
                    ),
                    ModificationRequest(
                        request_id=_request_id(limit_kind, ModificationTarget.ETERNIAN, "mailbox"),
                        target=ModificationTarget.ETERNIAN,
                        limit_kind=limit_kind,
                        category=ImpedimentCategory.LEARNING_STORAGE,
                        modification_summary="학습 artifact 장기 보관·인덱스 정책( durable storage tier ) 검토",
                        user_message="에테르니언: 학습 저장·아카이브 tier 확장안을 검토해 주세요.",
                        evidence_refs=("docs/60-unbounded-accumulation-engine.md",),
                    ),
                ),
                evidence_refs=("state/mailbox/items",),
            )
        )
    return impediments


def _load_evolution_domain_ids(foundry_root: Path) -> tuple[str, ...]:
    path = foundry_root / "config" / "arkaon-evolution-domains.json"
    if not path.is_file():
        return ()
    document = json.loads(path.read_text(encoding="utf-8"))
    return tuple(
        str(item.get("domain_id", "")).strip()
        for item in (document.get("domains") or ())
        if isinstance(item, dict) and str(item.get("domain_id", "")).strip()
    )


def _scan_business_improvement_program(foundry_root: Path) -> list[LearningImpediment]:
    impediments: list[LearningImpediment] = []
    audit_path = foundry_root / "config" / "arkaon-experience-operations-audit.json"
    if not audit_path.is_file():
        limit_kind = "IMPROVEMENT_PROGRAM_CONFIG_MISSING"
        impediment_id = sha256(limit_kind.encode()).hexdigest()[:16]
        impediments.append(
            LearningImpediment(
                impediment_id=impediment_id,
                limit_kind=limit_kind,
                category=ImpedimentCategory.BUSINESS_IMPROVEMENT_PROGRAM,
                severity=ImpedimentSeverity.HIGH,
                learning_domain=None,
                user_message="업무개선프로그램(experience operations audit) 설정이 없어 학습→개선 연결이 불가합니다.",
                modification_requests=(
                    ModificationRequest(
                        request_id=_request_id(limit_kind, ModificationTarget.BEOM, "config"),
                        target=ModificationTarget.BEOM,
                        limit_kind=limit_kind,
                        category=ImpedimentCategory.BUSINESS_IMPROVEMENT_PROGRAM,
                        modification_summary="config/arkaon-experience-operations-audit.json 배포 및 오케스트레이터 연동",
                        user_message="범: 업무개선프로그램(audit) 설정을 배포해 주세요.",
                        evidence_refs=("docs/39-arkaon-experience-operations-audit.md",),
                    ),
                ),
                evidence_refs=("docs/39-arkaon-experience-operations-audit.md",),
            )
        )
        return impediments

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit_areas = frozenset(str(item) for item in (audit.get("areas") or ()) if str(item).strip())
    uncovered: list[str] = []
    for domain_id in _load_evolution_domain_ids(foundry_root):
        mapped = _EVOLUTION_TO_AUDIT_AREAS.get(domain_id, ())
        if not mapped or not any(area in audit_areas for area in mapped):
            uncovered.append(domain_id)
    if uncovered:
        limit_kind = "IMPROVEMENT_PROGRAM_AREA_GAP"
        summary = ", ".join(uncovered)
        impediment_id = sha256(f"{limit_kind}|{summary}".encode()).hexdigest()[:16]
        impediments.append(
            LearningImpediment(
                impediment_id=impediment_id,
                limit_kind=limit_kind,
                category=ImpedimentCategory.BUSINESS_IMPROVEMENT_PROGRAM,
                severity=ImpedimentSeverity.MEDIUM,
                learning_domain=None,
                user_message=(
                    f"진화 학습 domain {len(uncovered)}개가 업무개선프로그램 audit areas에 매핑되지 않습니다: "
                    f"{summary}."
                ),
                modification_requests=(
                    ModificationRequest(
                        request_id=_request_id(limit_kind, ModificationTarget.ETERNIAN, "areas"),
                        target=ModificationTarget.ETERNIAN,
                        limit_kind=limit_kind,
                        category=ImpedimentCategory.BUSINESS_IMPROVEMENT_PROGRAM,
                        modification_summary="experience audit areas·roles 확장으로 evolution domain 커버리지 정렬",
                        user_message="에테르니언: 업무개선프로그램 감사 영역을 evolution domain에 맞게 확장 검토해 주세요.",
                        evidence_refs=(
                            "config/arkaon-experience-operations-audit.json",
                            "config/arkaon-evolution-domains.json",
                        ),
                    ),
                    ModificationRequest(
                        request_id=_request_id(limit_kind, ModificationTarget.BEOM, "areas"),
                        target=ModificationTarget.BEOM,
                        limit_kind=limit_kind,
                        category=ImpedimentCategory.BUSINESS_IMPROVEMENT_PROGRAM,
                        modification_summary="arkaon-experience-operations-audit.json areas 목록에 신규 감사 영역 추가",
                        user_message="범: audit areas 설정을 업데이트해 학습 domain을 커버해 주세요.",
                        evidence_refs=("config/arkaon-experience-operations-audit.json",),
                    ),
                ),
                evidence_refs=(
                    "config/arkaon-experience-operations-audit.json",
                    "config/arkaon-evolution-domains.json",
                ),
            )
        )

    if str(audit.get("maximum_outcome", "IMPROVEMENT_PROPOSAL")).upper() == "IMPROVEMENT_PROPOSAL":
        learning_artifacts = sum(
            1
            for relative in ("knowledge/shorts-production-assets", "knowledge/sns-digests", "state/hourly-learning")
            if (foundry_root / relative).is_dir() and any((foundry_root / relative).glob("*"))
        )
        if learning_artifacts >= 2:
            limit_kind = "IMPROVEMENT_PROGRAM_OUTCOME_CAP"
            impediment_id = sha256(limit_kind.encode()).hexdigest()[:16]
            impediments.append(
                LearningImpediment(
                    impediment_id=impediment_id,
                    limit_kind=limit_kind,
                    category=ImpedimentCategory.BUSINESS_IMPROVEMENT_PROGRAM,
                    severity=ImpedimentSeverity.MEDIUM,
                    learning_domain=None,
                    user_message=(
                        "학습 artifact가 축적 중인데 업무개선프로그램 최대 산출이 IMPROVEMENT_PROPOSAL에 고정되어 "
                        "학습→업무개선 이행 경로가 제한됩니다."
                    ),
                    modification_requests=(
                        ModificationRequest(
                            request_id=_request_id(limit_kind, ModificationTarget.ETERNIAN, "outcome"),
                            target=ModificationTarget.ETERNIAN,
                            limit_kind=limit_kind,
                            category=ImpedimentCategory.BUSINESS_IMPROVEMENT_PROGRAM,
                            modification_summary=(
                                "업무개선 프로그램 phase-2: 학습-derived proposal의 fulfillment·검증 단계 확장 검토"
                            ),
                            user_message=(
                                "에테르니언: 학습 결과를 업무개선으로 연결하는 program phase 확장을 검토해 주세요."
                            ),
                            evidence_refs=(
                                "config/arkaon-experience-operations-audit.json",
                                "docs/39-arkaon-experience-operations-audit.md",
                                "docs/53-mailbox-delivery-flow.md",
                            ),
                        ),
                        ModificationRequest(
                            request_id=_request_id(limit_kind, ModificationTarget.BEOM, "outcome"),
                            target=ModificationTarget.BEOM,
                            limit_kind=limit_kind,
                            category=ImpedimentCategory.BUSINESS_IMPROVEMENT_PROGRAM,
                            modification_summary="fulfillment-queue 처리·experience audit trigger 주기 강화",
                            user_message="범: 학습→개선 proposal 이행 큐 처리를 강화해 주세요.",
                            evidence_refs=("config/arkaon-mailbox-delivery.json",),
                        ),
                    ),
                    evidence_refs=("config/arkaon-experience-operations-audit.json",),
                )
            )

    gap_path = foundry_root / "config" / "arkaon-capability-gap.json"
    if gap_path.is_file():
        gap_policy = json.loads(gap_path.read_text(encoding="utf-8"))
        max_gaps = int(gap_policy.get("max_gaps_per_report", 20))
        if max_gaps < 100:
            limit_kind = "IMPROVEMENT_PROGRAM_GAP_REPORT_CAP"
            impediment_id = sha256(f"{limit_kind}|{max_gaps}".encode()).hexdigest()[:16]
            impediments.append(
                LearningImpediment(
                    impediment_id=impediment_id,
                    limit_kind=limit_kind,
                    category=ImpedimentCategory.BUSINESS_IMPROVEMENT_PROGRAM,
                    severity=ImpedimentSeverity.LOW,
                    learning_domain=None,
                    user_message=(
                        f"capability gap 리포트 상한 max_gaps_per_report={max_gaps} — "
                        "학습·격차 축적 시 개선 후보가 잘릴 수 있습니다."
                    ),
                    modification_requests=(
                        ModificationRequest(
                            request_id=_request_id(limit_kind, ModificationTarget.BEOM, "gap-cap"),
                            target=ModificationTarget.BEOM,
                            limit_kind=limit_kind,
                            category=ImpedimentCategory.BUSINESS_IMPROVEMENT_PROGRAM,
                            modification_summary="arkaon-capability-gap.json max_gaps_per_report 상향 또는 null(unbounded)",
                            user_message="범: capability gap 리포트 상한을 해제·상향해 주세요.",
                            evidence_refs=("config/arkaon-capability-gap.json",),
                        ),
                    ),
                    evidence_refs=("config/arkaon-capability-gap.json",),
                )
            )

    promotion_path = foundry_root / "config" / "arkaon-pattern-promotion.json"
    if promotion_path.is_file():
        promotion = json.loads(promotion_path.read_text(encoding="utf-8"))
        candidates_dir = foundry_root / "knowledge" / "patterns" / "candidates"
        candidate_count = len(list(candidates_dir.glob("*.json"))) if candidates_dir.is_dir() else 0
        if not promotion.get("production_promotion_allowed", False) and candidate_count >= 10:
            limit_kind = "IMPROVEMENT_PROGRAM_PATTERN_PROMOTION_BLOCKED"
            impediment_id = sha256(f"{limit_kind}|{candidate_count}".encode()).hexdigest()[:16]
            impediments.append(
                LearningImpediment(
                    impediment_id=impediment_id,
                    limit_kind=limit_kind,
                    category=ImpedimentCategory.BUSINESS_IMPROVEMENT_PROGRAM,
                    severity=ImpedimentSeverity.MEDIUM,
                    learning_domain=None,
                    user_message=(
                        f"pattern candidate {candidate_count}개 축적 중인데 production_promotion_allowed=false — "
                        "학습→패턴 자산→업무개선 연결이 막혀 있습니다."
                    ),
                    modification_requests=(
                        ModificationRequest(
                            request_id=_request_id(limit_kind, ModificationTarget.ETERNIAN, "promotion"),
                            target=ModificationTarget.ETERNIAN,
                            limit_kind=limit_kind,
                            category=ImpedimentCategory.BUSINESS_IMPROVEMENT_PROGRAM,
                            modification_summary="pattern promotion governance·서명 경로 활성화 검토",
                            user_message="에테르니언: 학습 pattern 승격·reuse program 경로를 검토해 주세요.",
                            evidence_refs=(
                                "config/arkaon-pattern-promotion.json",
                                "knowledge/patterns/candidates",
                            ),
                        ),
                    ),
                    evidence_refs=("config/arkaon-pattern-promotion.json",),
                )
            )
    return impediments


class LearningImpedimentEngine:
    def __init__(self, *, foundry_root: Path, policy: LearningImpedimentPolicy | None = None) -> None:
        self.foundry_root = foundry_root.resolve()
        config = self.foundry_root / "config" / "arkaon-learning-impediment.json"
        self.policy = policy or LearningImpedimentPolicy.load(config)
        self.store_root = self.foundry_root / "state" / "learning-impediment"
        self.store_root.mkdir(parents=True, exist_ok=True)

    def analyze(self, *, now: datetime, limits: EngineLimitSnapshot | None = None) -> LearningImpedimentReport:
        if now.tzinfo is None:
            raise LearningImpedimentRejected("TIMESTAMP", "timezone-aware timestamp required")
        if not self.policy.enabled:
            return self._empty_report(now=now)
        if limits is None:
            limits = EngineLimitSnapshot.from_foundry(self.foundry_root)
        impediments: list[LearningImpediment] = []
        impediments.extend(_scan_bounded_resource_limits(self.foundry_root, limits))
        impediments.extend(_scan_bounded_accumulation(self.foundry_root))
        impediments.extend(_scan_collection_audit(self.foundry_root, policy=self.policy))
        impediments.extend(_scan_hourly_learning_cycle(self.foundry_root))
        impediments.extend(_scan_disabled_learning_subsystems(self.foundry_root))
        if self.policy.scan_learning_storage:
            impediments.extend(_scan_learning_storage_capability(self.foundry_root, policy=self.policy))
        if self.policy.scan_business_improvement_program:
            impediments.extend(_scan_business_improvement_program(self.foundry_root))
        digest_payload = {
            "evaluated_at": now.isoformat(),
            "impediment_count": len(impediments),
            "limit_kinds": sorted({item.limit_kind for item in impediments}),
        }
        digest = sha256(json.dumps(digest_payload, sort_keys=True).encode()).hexdigest()
        report = LearningImpedimentReport(
            foundry_root=self.foundry_root,
            evaluated_at=now,
            impediments=tuple(impediments),
            report_digest=digest,
        )
        dated = self.store_root / f"{now.strftime('%Y-%m-%d')}-{digest[:12]}.json"
        dated.write_text(json.dumps(report.to_document(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        latest = self.store_root / "latest.json"
        latest.write_text(json.dumps(report.to_document(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return report

    def _empty_report(self, *, now: datetime) -> LearningImpedimentReport:
        digest = sha256(now.isoformat().encode()).hexdigest()
        return LearningImpedimentReport(self.foundry_root, now, (), digest)
