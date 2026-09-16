"""ARKAON advisory audits for content, UX, benchmarks, and operational consistency."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from hashlib import sha256
from urllib.parse import urlsplit


class AuditRejected(ValueError):
    pass


class FindingSeverity(str, Enum):
    BLOCKER = "BLOCKER"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class MaximumOutcome(str, Enum):
    IMPROVEMENT_PROPOSAL = "IMPROVEMENT_PROPOSAL"


@dataclass(frozen=True)
class PageSnapshot:
    page_id: str
    path: str
    title: str
    heading_levels: tuple[int, ...]
    primary_actions: tuple[str, ...]
    visible_texts: tuple[str, ...]
    navigation_targets: tuple[str, ...]
    average_contrast_ratio: float
    minimum_touch_target_px: int
    mobile_overflow: bool
    synthetic: bool = True


@dataclass(frozen=True)
class OperationalManifest:
    frontend_routes: frozenset[str]
    api_routes: frozenset[str]
    policy_route_refs: frozenset[str]
    required_home_actions: frozenset[str]


@dataclass(frozen=True)
class BenchmarkFeature:
    evidence_id: str
    source_url: str
    source_title: str
    publisher: str
    retrieved_at: datetime
    expires_at: datetime
    evidence_digest: str
    feature_name: str
    observed_pattern: str
    official: bool
    copy_prohibited: bool = True


@dataclass(frozen=True)
class ImprovementFinding:
    finding_id: str
    category: str
    severity: FindingSeverity
    title: str
    affected_paths: tuple[str, ...]
    evidence_digest: str
    recommendation: str
    requires_human_review: bool
    user_impact: str = ""
    required_synthetic_tests: tuple[str, ...] = ()


@dataclass(frozen=True)
class ImprovementProposal:
    schema_version: str
    maximum_outcome: MaximumOutcome
    platform_id: str
    candidate_commit: str
    generated_at: datetime
    finding: ImprovementFinding
    location: str
    evidence_digest: str
    user_impact: str
    recommendation: str
    required_synthetic_tests: tuple[str, ...]
    requires_human_review: bool
    automatic_change_allowed: bool = False
    proposal_digest: str = ""

    def to_document(self) -> dict[str, object]:
        document = {
            "schema_version": self.schema_version,
            "maximum_outcome": self.maximum_outcome.value,
            "platform_id": self.platform_id,
            "candidate_commit": self.candidate_commit,
            "generated_at": self.generated_at.isoformat(),
            "finding": {
                **{key: (value.value if isinstance(value, Enum) else value) for key, value in asdict(self.finding).items()},
            },
            "location": self.location,
            "evidence_digest": self.evidence_digest,
            "user_impact": self.user_impact,
            "recommendation": self.recommendation,
            "required_synthetic_tests": list(self.required_synthetic_tests),
            "requires_human_review": self.requires_human_review,
            "automatic_change_allowed": self.automatic_change_allowed,
        }
        if self.proposal_digest:
            document["proposal_digest"] = self.proposal_digest
        return document


@dataclass(frozen=True)
class ExperienceOperationsReport:
    report_id: str
    candidate_commit: str
    generated_at: datetime
    findings: tuple[ImprovementFinding, ...]
    immediate_proposal_count: int
    automatic_change_allowed: bool
    competitor_copy_allowed: bool
    report_digest: str
    maximum_outcome: MaximumOutcome = MaximumOutcome.IMPROVEMENT_PROPOSAL


class ArkaonExperienceOperationsAuditor:
    """Finds inconsistencies immediately but emits proposals only."""

    def audit(
        self,
        *,
        report_id: str,
        candidate_commit: str,
        pages: tuple[PageSnapshot, ...],
        manifest: OperationalManifest,
        benchmarks: tuple[BenchmarkFeature, ...] = (),
        now: datetime,
    ) -> ExperienceOperationsReport:
        if not report_id or not self._sha_ok(candidate_commit) or now.tzinfo is None or not pages:
            raise AuditRejected("complete candidate-bound audit input required")
        if len({page.page_id for page in pages}) != len(pages):
            raise AuditRejected("duplicate page snapshot")
        findings: list[ImprovementFinding] = []
        page_paths = {page.path for page in pages}

        for page in pages:
            if not page.synthetic:
                raise AuditRejected("synthetic page snapshot required")
            evidence = self._digest(page.__dict__)
            if not page.title.strip() or not page.heading_levels or page.heading_levels[0] != 1:
                findings.append(
                    self._finding(
                        "HEADING",
                        page.path,
                        FindingSeverity.HIGH,
                        "제목·헤딩 계층 불일치",
                        evidence,
                        "하나의 H1부터 순차적인 제목 구조로 재배치한다.",
                        "화면 목적 파악과 스크린리더 탐색이 어려워집니다.",
                        ("synthetic-home-heading-hierarchy",),
                    )
                )
            if len(page.primary_actions) != 1:
                findings.append(
                    self._finding(
                        "PRIMARY_ACTION",
                        page.path,
                        FindingSeverity.MEDIUM,
                        "핵심 행동이 불명확하거나 중복됨",
                        evidence,
                        "사용자 역할별 핵심 행동 하나를 우선 배치한다.",
                        "다음 행동 선택이 지연되거나 잘못된 경로로 유도될 수 있습니다.",
                        ("synthetic-primary-action-clarity",),
                    )
                )
            if page.average_contrast_ratio < 4.5 or page.minimum_touch_target_px < 44 or page.mobile_overflow:
                findings.append(
                    self._finding(
                        "READABILITY",
                        page.path,
                        FindingSeverity.HIGH,
                        "모바일 가독성·접근성 기준 미달",
                        evidence,
                        "대비 4.5:1, 터치 44px, 가로 넘침 제거를 합성 화면에서 검증한다.",
                        "저시력·모바일 사용자가 핵심 정보를 놓치거나 조작에 실패할 수 있습니다.",
                        ("synthetic-mobile-accessibility",),
                    )
                )
            if any(len(text) >= 120 for text in page.visible_texts):
                findings.append(
                    self._finding(
                        "CONTENT",
                        page.path,
                        FindingSeverity.MEDIUM,
                        "화면 문구가 과도하게 길음",
                        evidence,
                        "핵심 안내·조건·권리를 짧은 문단과 목록으로 분리한다.",
                        "핵심 안내가 묻혀 이탈 또는 오해가 발생할 수 있습니다.",
                        ("synthetic-content-brevity",),
                    )
                )
            broken = tuple(sorted(set(page.navigation_targets) - manifest.frontend_routes))
            if broken:
                findings.append(
                    self._finding(
                        "BROKEN_PATH",
                        page.path,
                        FindingSeverity.BLOCKER,
                        f"등록되지 않은 화면경로: {', '.join(broken)}",
                        evidence,
                        "경로를 등록하거나 링크를 제거하고 회귀시험을 추가한다.",
                        "사용자가 끊어진 화면으로 이동해 작업을 완료하지 못할 수 있습니다.",
                        ("synthetic-route-regression",),
                    )
                )

        missing_pages = manifest.required_home_actions - {
            action for page in pages if page.path == "/" for action in page.primary_actions
        }
        if missing_pages:
            findings.append(
                self._finding(
                    "HOME_IA",
                    "/",
                    FindingSeverity.HIGH,
                    "홈 필수 행동 누락",
                    self._digest(sorted(missing_pages)),
                    "역할별 필수 행동을 홈 정보구조에 반영한다.",
                    "첫 화면에서 핵심 업무를 시작하지 못할 수 있습니다.",
                    ("synthetic-home-required-actions",),
                )
            )
        for category, missing in (
            ("FRONTEND_API", manifest.frontend_routes - manifest.api_routes),
            ("POLICY_ROUTE", manifest.policy_route_refs - manifest.api_routes),
            ("PAGE_ROUTE", manifest.frontend_routes - page_paths),
        ):
            if missing:
                findings.append(
                    self._finding(
                        category,
                        "route-manifest",
                        FindingSeverity.BLOCKER,
                        f"경로 계약 불일치: {', '.join(sorted(missing))}",
                        self._digest(sorted(missing)),
                        "Frontend·API·정책·페이지 경로를 같은 후보 커밋에서 정합화한다.",
                        "화면·API·정책 간 불일치로 기능 오동작 또는 승인 누락이 발생할 수 있습니다.",
                        ("synthetic-route-contract",),
                    )
                )

        for benchmark in benchmarks:
            parsed = urlsplit(benchmark.source_url)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or not benchmark.official
                or not benchmark.copy_prohibited
                or now >= benchmark.expires_at
                or not self._digest_ok(benchmark.evidence_digest)
            ):
                raise AuditRejected("fresh official non-copy benchmark evidence required")
            findings.append(
                ImprovementFinding(
                    f"benchmark:{benchmark.evidence_id}",
                    "BENCHMARK",
                    FindingSeverity.LOW,
                    f"비교 검토: {benchmark.feature_name}",
                    (),
                    benchmark.evidence_digest,
                    f"'{benchmark.observed_pattern}'의 사용자 문제와 효과만 분석해 독자적인 합성 초안을 만든다.",
                    True,
                    "유사 플랫폼 대비 기능 격차 가능성을 인지할 수 있습니다.",
                    ("synthetic-benchmark-adaptation",),
                )
            )

        serialized = [{**item.__dict__, "severity": item.severity.value} for item in findings]
        report_digest = self._digest(
            {"id": report_id, "commit": candidate_commit, "at": now.isoformat(), "findings": serialized}
        )
        return ExperienceOperationsReport(
            report_id,
            candidate_commit,
            now,
            tuple(findings),
            len(findings),
            False,
            False,
            report_digest,
        )

    def apply_improvement(self) -> None:
        raise AuditRejected("ARKAON may propose but cannot apply experience or operational changes")

    @classmethod
    def _finding(
        cls,
        category: str,
        path: str,
        severity: FindingSeverity,
        title: str,
        evidence: str,
        recommendation: str,
        user_impact: str,
        required_synthetic_tests: tuple[str, ...],
    ) -> ImprovementFinding:
        return ImprovementFinding(
            f"{category.lower()}:{sha256(f'{path}|{title}'.encode()).hexdigest()[:12]}",
            category,
            severity,
            title,
            (path,),
            evidence,
            recommendation,
            True,
            user_impact,
            required_synthetic_tests,
        )

    @staticmethod
    def _digest(value: object) -> str:
        return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()

    @staticmethod
    def _digest_ok(value: str) -> bool:
        return len(value) == 64 and all(character in "0123456789abcdef" for character in value)

    @staticmethod
    def _sha_ok(value: str) -> bool:
        return len(value) == 40 and all(character in "0123456789abcdef" for character in value)
