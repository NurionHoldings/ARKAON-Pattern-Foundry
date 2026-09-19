"""Clean-room launch-flow intelligence for the visual platform dialogue."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator

from .visual_platform_dialogue import PlatformBrief


class LaunchIntelligenceError(ValueError):
    pass


class OfficialFlowObservation(BaseModel):
    source_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")
    provider: str = Field(min_length=1, max_length=80)
    official_url: str
    retrieved_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T")
    observed_steps: list[str] = Field(min_length=2, max_length=12)
    generic_capabilities: set[str] = Field(min_length=1, max_length=20)
    copied_code: bool = False
    copied_visual_design: bool = False
    copied_marketing_copy: bool = False

    @model_validator(mode="after")
    def validate_clean_room_source(self) -> OfficialFlowObservation:
        parsed = urlparse(self.official_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("official HTTPS source required")
        if self.copied_code or self.copied_visual_design or self.copied_marketing_copy:
            raise ValueError("copied implementation material is forbidden")
        return self


class LaunchIntent(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    purpose: str = Field(min_length=1, max_length=2000)
    audience: list[str] = Field(default_factory=list, max_length=20)
    core_action: str | None = Field(default=None, max_length=500)
    collects_personal_data: bool | None = None
    needs_roles_or_permissions: bool | None = None
    needs_payment: bool | None = None
    constraints: list[str] = Field(default_factory=list, max_length=50)


class LaunchAnswer(BaseModel):
    question_id: str
    answer: str = Field(min_length=1, max_length=2000)


class LaunchBlueprint(BaseModel):
    schema_version: str = "apf.platform-launch-blueprint/1.0"
    pattern_asset_digest: str
    brief: PlatformBrief
    required_questions: list[str]
    next_step: str
    implementation_allowed: bool = False
    deployment_allowed: bool = False


_QUESTIONS = {
    "audience": "이 플랫폼을 가장 자주 사용할 사람은 누구인가요?",
    "core_action": "그 사람이 여기서 반드시 끝낼 한 가지 일은 무엇인가요?",
    "personal_data": "이름·연락처처럼 개인을 알아볼 수 있는 정보를 받나요?",
    "roles": "운영자·판매자·고객처럼 서로 다른 권한이 필요한가요?",
    "payment": "결제·구독·정산 기능이 필요한가요?",
    "data_detail": "받을 개인정보와 보관 이유를 적어주세요.",
    "role_detail": "각 역할이 볼 수 있고 바꿀 수 있는 범위를 적어주세요.",
    "payment_detail": "누가 누구에게 언제 얼마를 결제·정산하는지 적어주세요.",
}


def load_observations(path: Path) -> list[OfficialFlowObservation]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = raw["observations"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise LaunchIntelligenceError("LAUNCH_EVIDENCE_INVALID") from exc
    observations = [OfficialFlowObservation.model_validate(item) for item in items]
    if len({item.provider.casefold() for item in observations}) < 3:
        raise LaunchIntelligenceError("LAUNCH_EVIDENCE_DIVERSITY_REQUIRED")
    if len({item.source_id for item in observations}) != len(observations):
        raise LaunchIntelligenceError("LAUNCH_EVIDENCE_DUPLICATE")
    return observations


def abstract_patterns(observations: list[OfficialFlowObservation]) -> dict[str, tuple[str, ...]]:
    """Keep only generic capabilities independently evidenced by two providers."""
    support: dict[str, set[str]] = {}
    for item in observations:
        for capability in item.generic_capabilities:
            support.setdefault(capability, set()).add(item.provider)
    return {
        capability: tuple(sorted(providers))
        for capability, providers in sorted(support.items())
        if len(providers) >= 2
    }


def asset_digest(observations: list[OfficialFlowObservation]) -> str:
    evidence = [item.model_dump(mode="json") for item in observations]
    encoded = json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + sha256(encoded).hexdigest()


def next_questions(intent: LaunchIntent, answers: list[LaunchAnswer] | None = None) -> list[dict[str, str]]:
    """Ask only missing, decision-changing questions; reveal sensitive branches conditionally."""
    answered = {item.question_id for item in answers or []}
    ids: list[str] = []
    if not intent.audience:
        ids.append("audience")
    if not intent.core_action:
        ids.append("core_action")
    if intent.collects_personal_data is None:
        ids.append("personal_data")
    if intent.needs_roles_or_permissions is None:
        ids.append("roles")
    if intent.needs_payment is None:
        ids.append("payment")
    if intent.collects_personal_data is True:
        ids.append("data_detail")
    if intent.needs_roles_or_permissions is True:
        ids.append("role_detail")
    if intent.needs_payment is True:
        ids.append("payment_detail")
    return [{"question_id": item, "plain_text": _QUESTIONS[item]} for item in ids if item not in answered]


def build_blueprint(
    intent: LaunchIntent,
    observations: list[OfficialFlowObservation],
    answers: list[LaunchAnswer] | None = None,
) -> LaunchBlueprint:
    patterns = abstract_patterns(observations)
    required = {"prompt_to_draft", "editable_preview", "iterative_refinement"}
    if not required.issubset(patterns):
        raise LaunchIntelligenceError("LAUNCH_PATTERN_SUPPORT_INSUFFICIENT")
    questions = next_questions(intent, answers)
    audience = intent.audience or ["확인 필요"]
    capabilities = [intent.core_action or "핵심 이용 흐름 확인"]
    if intent.collects_personal_data:
        capabilities.append("개인정보 최소수집·보관 통제")
    if intent.needs_roles_or_permissions:
        capabilities.append("역할별 접근 권한")
    if intent.needs_payment:
        capabilities.append("결제·정산 sandbox")
    brief = PlatformBrief(
        name=intent.name,
        purpose=intent.purpose,
        audience=audience,
        required_capabilities=capabilities,
        constraints=[*intent.constraints, "명세 승인 전 구현 금지", "운영반영 별도 승인"],
    )
    return LaunchBlueprint(
        pattern_asset_digest=asset_digest(observations),
        brief=brief,
        required_questions=[str(item["question_id"]) for item in questions],
        next_step="ASK_MINIMUM_QUESTIONS" if questions else "GENERATE_VISUAL_OPTIONS",
    )


@dataclass(frozen=True)
class LaunchFlow:
    stages: tuple[str, ...] = (
        "ONE_SENTENCE_INTENT",
        "MINIMUM_ADAPTIVE_QUESTIONS",
        "GENERATE_VISUAL_OPTIONS",
        "CONVERSATIONAL_REFINEMENT",
        "INTERACTIVE_PREVIEW",
        "OWNER_UNDERSTANDING_CONFIRMATION",
        "SPEC_APPROVAL",
        "SANDBOX_IMPLEMENTATION_APPROVAL",
        "DEPLOYMENT_APPROVAL",
    )
