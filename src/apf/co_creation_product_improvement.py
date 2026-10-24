"""Strict before/after product evaluation — trace alone does not count as improvement."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from .co_creation_studio import StudioBrief, brief_has_empty_sections, render_legacy_baseline_html

SCHEMA_EVAL = "apf.co-creation-product-improvement-eval/v1"
EXECUTION_VERSION = "co_creation_studio_pipeline/1.0"

_MOBILE_MEDIA = re.compile(r"@media\s*\(\s*max-width", re.IGNORECASE)
_PLACEHOLDER = re.compile(r"입력\s*필요|입력해\s*주세요|확인\s*후\s*입력")


class ProductImprovementRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ProductImprovementScores:
    content_completeness: float
    usability_steps: float
    mobile_readiness: float
    empty_section_count: int

    def to_document(self) -> dict[str, float | int]:
        return {
            "content_completeness": self.content_completeness,
            "usability_steps": self.usability_steps,
            "mobile_readiness": self.mobile_readiness,
            "empty_section_count": self.empty_section_count,
        }


@dataclass(frozen=True)
class ProductImprovementEvaluation:
    evaluation_id: str
    session_id: str
    proposal_id: str
    baseline_html_digest: str
    candidate_html_digest: str
    scores_before: ProductImprovementScores
    scores_after: ProductImprovementScores
    automated_check_passed: bool
    improvement_accepted: bool
    independent_review_status: str
    status_display: str
    failure_codes: tuple[str, ...]
    derived_learning_task_id: str | None
    scoring_artifact_ref: str
    execution_version: str
    lesson_ref: str | None
    evaluated_at: datetime
    evaluation_digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_EVAL,
            "evaluation_id": self.evaluation_id,
            "session_id": self.session_id,
            "proposal_id": self.proposal_id,
            "baseline_html_digest": self.baseline_html_digest,
            "candidate_html_digest": self.candidate_html_digest,
            "scores_before": self.scores_before.to_document(),
            "scores_after": self.scores_after.to_document(),
            "automated_check_passed": self.automated_check_passed,
            "improvement_accepted": self.improvement_accepted,
            "independent_review_status": self.independent_review_status,
            "status_display": self.status_display,
            "failure_codes": list(self.failure_codes),
            "derived_learning_task_id": self.derived_learning_task_id,
            "scoring_artifact_ref": self.scoring_artifact_ref,
            "execution_version": self.execution_version,
            "lesson_ref": self.lesson_ref,
            "evaluated_at": self.evaluated_at.isoformat(),
            "evaluation_digest": self.evaluation_digest,
        }


def _digest_text(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def _score_html(*, html: str, brief: StudioBrief | None) -> ProductImprovementScores:
    placeholder_hits = len(_PLACEHOLDER.findall(html))
    empty_sections = html.count("<!-- copy-angle slot") + html.count("data-filled=\"false\"")
    completeness = 1.0
    if brief is not None:
        ok, gaps = brief_has_empty_sections(brief)
        if not ok:
            completeness -= min(0.5, 0.1 * len(gaps))
    completeness -= min(0.4, 0.05 * placeholder_hits)
    completeness = max(0.0, min(1.0, completeness))
    usability = 0.35
    if "process" in html.lower() or "<ol" in html:
        usability += 0.25
    if html.count("<section") >= 3 or html.count('class="section"') >= 2:
        usability += 0.2
    if "hero" in html or "<h1" in html:
        usability += 0.2
    usability = max(0.0, min(1.0, usability))
    mobile = 1.0 if _MOBILE_MEDIA.search(html) else 0.0
    return ProductImprovementScores(
        content_completeness=round(completeness, 3),
        usability_steps=round(usability, 3),
        mobile_readiness=mobile,
        empty_section_count=empty_sections + placeholder_hits,
    )


def _write_learning_followup(
    *,
    foundry_root: Path,
    session_id: str,
    proposal_id: str,
    failure_codes: tuple[str, ...],
    evaluation_id: str,
    now: datetime,
) -> str:
    task_id = f"co-creation-product-{evaluation_id[:12]}"
    document = {
        "schema_version": "apf.failure-learning-feedback/v1",
        "failure_source_ref": f"state/co-creation/product-improvement/{evaluation_id}.json",
        "root_cause_code": failure_codes[0] if failure_codes else "PRODUCT_IMPROVEMENT_INSUFFICIENT",
        "derived_learning_task_id": task_id,
        "independent_review_ref": "inbox/operator-decision/pending-co-creation-product-improvement",
        "session_id": session_id,
        "proposal_id": proposal_id,
        "created_at": now.isoformat(),
    }
    path = foundry_root / "state" / "co-creation" / "learning-followups" / f"{task_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return task_id


class CoCreationProductImprovementEngine:
    def __init__(self, *, foundry_root: Path) -> None:
        self.foundry_root = foundry_root.resolve()
        self.eval_root = self.foundry_root / "state" / "co-creation" / "product-improvement"
        self.artifact_root = self.eval_root / "artifacts"
        self.eval_root.mkdir(parents=True, exist_ok=True)
        self.artifact_root.mkdir(parents=True, exist_ok=True)

    def evaluate(
        self,
        *,
        session_id: str,
        proposal_id: str,
        brief: StudioBrief,
        candidate_html: str,
        mobile_issue_notes: tuple[str, ...] = (),
        now: datetime,
    ) -> ProductImprovementEvaluation:
        if now.tzinfo is None:
            raise ProductImprovementRejected("TIMESTAMP", "timezone-aware timestamp required")
        if not candidate_html.strip():
            raise ProductImprovementRejected("CANDIDATE_MISSING", "candidate html required")

        baseline_html = render_legacy_baseline_html(brief)
        baseline_digest = _digest_text(baseline_html)
        candidate_digest = _digest_text(candidate_html)

        scores_before = _score_html(html=baseline_html, brief=brief)
        scores_after = _score_html(html=candidate_html, brief=brief)

        failure_codes: list[str] = []
        if scores_after.content_completeness < scores_before.content_completeness:
            failure_codes.append("CONTENT_REGRESSED")
        improved = (
            scores_after.content_completeness > scores_before.content_completeness
            or scores_after.usability_steps > scores_before.usability_steps + 0.15
            or scores_after.mobile_readiness > scores_before.mobile_readiness
        )
        if not improved:
            failure_codes.append("NO_MEASURABLE_GAIN")
        if scores_after.usability_steps < 0.7:
            failure_codes.append("USABILITY_STEPS_LOW")
        if scores_after.mobile_readiness < 1.0:
            failure_codes.append("MOBILE_LAYOUT_MISSING")
        if scores_after.empty_section_count > 0:
            failure_codes.append("EMPTY_OR_PLACEHOLDER_SECTIONS")
        if mobile_issue_notes:
            failure_codes.append("MOBILE_ISSUES_REPORTED")
        ok_brief, _brief_gaps = brief_has_empty_sections(brief)
        if not ok_brief:
            failure_codes.append("BRIEF_INCOMPLETE")

        automated_check_passed = len(failure_codes) == 0 and improved
        # Automated heuristics only — design/usability efficacy requires independent review.
        improvement_accepted = False
        independent_review_status = "PENDING"
        status_display = (
            "자동 검사 통과·독립 검토 대기"
            if automated_check_passed
            else "자동 검사 미통과"
        )

        evaluation_id = uuid4().hex[:24]
        artifact_ref = self.artifact_root / f"{evaluation_id}.json"
        artifact_body: dict[str, Any] = {
            "baseline_html_digest": baseline_digest,
            "candidate_html_digest": candidate_digest,
            "mobile_issue_notes": list(mobile_issue_notes),
            "brief": brief.to_document(),
        }
        artifact_ref.write_text(json.dumps(artifact_body, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

        derived_task: str | None = None
        if not automated_check_passed:
            derived_task = _write_learning_followup(
                foundry_root=self.foundry_root,
                session_id=session_id,
                proposal_id=proposal_id,
                failure_codes=tuple(failure_codes),
                evaluation_id=evaluation_id,
                now=now,
            )

        lesson_ref = None

        body = {
            "evaluation_id": evaluation_id,
            "session_id": session_id,
            "proposal_id": proposal_id,
            "baseline_html_digest": baseline_digest,
            "candidate_html_digest": candidate_digest,
            "automated_check_passed": automated_check_passed,
            "improvement_accepted": improvement_accepted,
            "failure_codes": failure_codes,
            "execution_version": EXECUTION_VERSION,
        }
        evaluation_digest = sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()

        evaluation = ProductImprovementEvaluation(
            evaluation_id=evaluation_id,
            session_id=session_id,
            proposal_id=proposal_id,
            baseline_html_digest=baseline_digest,
            candidate_html_digest=candidate_digest,
            scores_before=scores_before,
            scores_after=scores_after,
            automated_check_passed=automated_check_passed,
            improvement_accepted=improvement_accepted,
            independent_review_status=independent_review_status,
            status_display=status_display,
            failure_codes=tuple(failure_codes),
            derived_learning_task_id=derived_task,
            scoring_artifact_ref=artifact_ref.relative_to(self.foundry_root).as_posix(),
            execution_version=EXECUTION_VERSION,
            lesson_ref=lesson_ref,
            evaluated_at=now,
            evaluation_digest=evaluation_digest,
        )
        eval_path = self.eval_root / f"{evaluation_id}.json"
        eval_path.write_text(
            json.dumps(evaluation.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return evaluation
