"""Bridge co-creation conversation into filled studio briefs and HTML sections."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from html import escape
from pathlib import Path
from typing import Any

from .conversational_co_creation import ChatTurn, CoCreationProposal, TemplateSectionBlueprint

SCHEMA_STUDIO_DRAFT = "apf.co-creation-studio-draft/v1"
SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{7,127}$")

_PLACEHOLDER_MARKERS = (
    "입력 필요",
    "입력해 주세요",
    "확인 후 입력",
    "입력해주세요",
)

_LABEL_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?:고객|대상\s*고객|타깃)[:：]\s*(.+)", re.IGNORECASE), "audience"),
    (re.compile(r"(?:목적|만들\s*목적)[:：]\s*(.+)", re.IGNORECASE), "story"),
    (re.compile(r"(?:서비스|하는\s*일|제공)[:：]\s*(.+)", re.IGNORECASE), "story"),
    (re.compile(r"(?:차별점|강점|우리만의)[:：]\s*(.+)", re.IGNORECASE), "difference"),
    (re.compile(r"(?:이름|브랜드|상호)[:：]\s*(.+)", re.IGNORECASE), "title"),
    (re.compile(r"(?:연락|문의)[:：]\s*(.+)", re.IGNORECASE), "contact"),
)

_INDUSTRY_HINTS: tuple[tuple[str, str], ...] = (
    ("portfolio", r"포트폴리오|개인\s*사이트|작업\s*소개|프리랜"),
    ("shop", r"가게|매장|카페|음식|상품|브랜드\s*샵|쇼핑"),
    ("service", r"서비스|상담|스튜디오|에이전시|교육|클리닉"),
)

_SECTION_COPY: dict[str, tuple[str, str]] = {
    "hero": ("핵심 가치", "방문자가 처음 이해해야 할 문제와 약속"),
    "process": ("진행 방식", "의뢰부터 결과 확인까지의 단계"),
    "trust": ("신뢰 근거", "정책·환불·보증 등 리스크 완화"),
    "comparison": ("선택 이유", "다른 선택지 대비 장점"),
    "faq": ("자주 묻는 질문", "의사결정 전 확인 사항"),
    "contact": ("연락 안내", "문의·예약 채널"),
}


class CoCreationStudioRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class StudioBrief:
    industry: str
    title: str
    audience: str
    story: str
    offerings: str
    difference: str
    process: str
    contact: str
    theme: str = "editorial"

    def to_document(self) -> dict[str, str]:
        return {
            "industry": self.industry,
            "title": self.title,
            "audience": self.audience,
            "story": self.story,
            "offerings": self.offerings,
            "difference": self.difference,
            "process": self.process,
            "contact": self.contact,
            "theme": self.theme,
        }


def _first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        cleaned = line.strip()
        if cleaned:
            return cleaned[:160]
    return text.strip()[:160]


def _extract_labeled_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        for pattern, key in _LABEL_PATTERNS:
            match = pattern.search(line.strip())
            if match:
                value = match.group(1).strip()
                if value and key not in fields:
                    fields[key] = value[:2000]
    return fields


def infer_industry(*, message: str, scope: str) -> str:
    blob = message.lower()
    for industry, pattern in _INDUSTRY_HINTS:
        if re.search(pattern, blob, re.IGNORECASE):
            return industry
    if scope == "PLATFORM":
        return "service"
    return "service"


def _default_offerings(*, industry: str, story: str, sections: tuple[TemplateSectionBlueprint, ...]) -> str:
    labels = {
        "service": ("핵심 상담", "맞춤 설계", "사후 점검"),
        "shop": ("시그니처 메뉴", "추천 구성", "선물·예약"),
        "portfolio": ("대표 프로젝트", "협업 방식", "추가 사례"),
    }
    titles = labels.get(industry, labels["service"])
    details = story[:120] if story else "대화에서 정리한 목적과 제공 범위를 반영합니다."
    lines: list[str] = []
    for index, title in enumerate(titles):
        section = sections[index].section_id if index < len(sections) else None
        purpose = _SECTION_COPY.get(section or "", ("", ""))[1]
        detail = purpose or details
        lines.append(f"{title} | {detail}")
    return "\n".join(lines)


def _default_process(story: str) -> str:
    seed = _first_nonempty_line(story) or "요청 내용"
    return "\n".join(
        (
            f"목적과 {seed[:40]} 범위 확인",
            "구성·디자인 방향과 일정 협의",
            "초안 공유 후 수정·확정",
        )
    )


def build_studio_brief_from_conversation(
    *,
    message: str,
    scope: str,
    proposal: CoCreationProposal,
    turns: tuple[ChatTurn, ...] = (),
) -> StudioBrief:
    combined = "\n".join(
        turn.content for turn in turns if turn.role == "user"
    )
    if message.strip():
        combined = f"{combined}\n{message.strip()}".strip()
    labeled = _extract_labeled_fields(combined)
    industry = infer_industry(message=combined, scope=scope)
    title = labeled.get("title") or _first_nonempty_line(combined) or proposal.platform_id
    audience = labeled.get("audience") or f"{title}를 찾는 방문자와 잠재 고객"
    story = labeled.get("story") or _first_nonempty_line(combined) or proposal.domain_brief[:500]
    difference = (
        labeled.get("difference")
        or f"{title}는 {audience}에게 맞춘 구성과 읽기 쉬운 설명을 우선합니다."
    )
    offerings = _default_offerings(
        industry=industry,
        story=story,
        sections=proposal.template_blueprint,
    )
    process = _default_process(story)
    contact = labeled.get("contact") or "공개 전에 이 화면에서 이메일·전화·상담 채널을 확인·수정할 수 있습니다."
    return StudioBrief(
        industry=industry,
        title=title[:80],
        audience=audience[:160],
        story=story[:2000],
        offerings=offerings[:1200],
        difference=difference[:1200],
        process=process[:1200],
        contact=contact[:200],
    )


def brief_has_empty_sections(brief: StudioBrief) -> tuple[bool, list[str]]:
    missing: list[str] = []
    for key, value in brief.to_document().items():
        if key == "theme":
            continue
        if not str(value).strip():
            missing.append(key)
    for line in brief.offerings.splitlines():
        if "|" not in line:
            missing.append("offerings_detail")
            break
        _, _, detail = line.partition("|")
        if not detail.strip():
            missing.append("offerings_detail")
            break
    for marker in _PLACEHOLDER_MARKERS:
        blob = json.dumps(brief.to_document(), ensure_ascii=False)
        if marker in blob:
            missing.append(f"placeholder:{marker}")
    return len(missing) == 0, missing


def _draft_digest(body: dict[str, Any]) -> str:
    return sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def assert_valid_session_id(session_id: str) -> str:
    cleaned = session_id.strip()
    if not SESSION_ID_RE.fullmatch(cleaned):
        raise CoCreationStudioRejected("SESSION_ID_INVALID", "invalid co-creation session id")
    return cleaned


def studio_draft_path(foundry_root: Path, session_id: str) -> Path:
    safe = assert_valid_session_id(session_id)
    return foundry_root / "state" / "co-creation" / "studio-drafts" / f"{safe}.json"


def save_studio_draft(
    *,
    foundry_root: Path,
    session_id: str,
    proposal_id: str,
    tenant_id: str,
    principal_id: str,
    brief: StudioBrief,
    now: datetime,
    local_project_id: str | None = None,
    reference_consent_request_id: str | None = None,
) -> dict[str, object]:
    if now.tzinfo is None:
        raise CoCreationStudioRejected("TIMESTAMP", "timezone-aware timestamp required")
    assert_valid_session_id(session_id)
    complete, gaps = brief_has_empty_sections(brief)
    if not complete:
        raise CoCreationStudioRejected("BRIEF_INCOMPLETE", "studio brief has empty sections: " + ",".join(gaps))
    body = {
        "schema_version": SCHEMA_STUDIO_DRAFT,
        "session_id": session_id,
        "proposal_id": proposal_id,
        "tenant_id": tenant_id,
        "principal_id": principal_id,
        "brief": brief.to_document(),
        "updated_at": now.isoformat(),
        "local_project_id": local_project_id,
    }
    if reference_consent_request_id is not None:
        body["reference_consent_request_id"] = reference_consent_request_id
    body["draft_digest"] = _draft_digest({k: v for k, v in body.items() if k != "draft_digest"})
    path = studio_draft_path(foundry_root, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return body


def load_studio_draft(foundry_root: Path, session_id: str) -> dict[str, object] | None:
    path = studio_draft_path(foundry_root, session_id)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def sync_studio_draft_from_proposal(
    *,
    foundry_root: Path,
    proposal: CoCreationProposal,
    user_message: str,
    turns: tuple[ChatTurn, ...],
    now: datetime,
) -> dict[str, object]:
    brief = build_studio_brief_from_conversation(
        message=user_message,
        scope=proposal.scope.value,
        proposal=proposal,
        turns=turns,
    )
    return save_studio_draft(
        foundry_root=foundry_root,
        session_id=proposal.session_id,
        proposal_id=proposal.proposal_id,
        tenant_id=proposal.tenant_id,
        principal_id=proposal.principal_id,
        brief=brief,
        now=now,
    )


def render_legacy_baseline_html(brief: StudioBrief) -> str:
    """Single-column intro page (pre-studio) for before/after comparison."""
    title = escape(brief.title)
    story = escape(brief.story).replace("\n", "<br>")
    audience = escape(brief.audience)
    return (
        "<!doctype html><html lang=\"ko\"><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{title}</title>"
        "<style>body{margin:0;font-family:system-ui,sans-serif;background:#0a1220;color:#eef3ff;"
        "line-height:1.7}.wrap{max-width:720px;margin:auto;padding:48px 24px}</style>"
        f"<div class=\"wrap\"><h1>{title}</h1><p>{audience}</p><p>{story}</p>"
        "<footer style=\"margin-top:48px;font-size:.85rem;color:#7a8fa6\">"
        "아르카온 이전 단일 소개 초안</footer></div></html>"
    )


def render_filled_section_html(
    *,
    section_id: str,
    purpose: str,
    brief: StudioBrief,
) -> str:
    """Replace comment-only stubs with titles and body copy derived from the studio brief."""
    heading, lead = _SECTION_COPY.get(section_id, (section_id, purpose))
    offerings = [line for line in brief.offerings.splitlines() if line.strip()]
    if section_id == "hero":
        inner = (
            f"<h1>{escape(brief.title)}</h1>"
            f"<p>{escape(brief.audience)}</p>"
            f"<p>{escape(brief.story)}</p>"
        )
    elif section_id in {"offer", "comparison"}:
        cards = []
        for index, line in enumerate(offerings[:3]):
            title, _, detail = line.partition("|")
            cards.append(
                f"<article><h3>{escape(title.strip())}</h3><p>{escape(detail.strip())}</p></article>"
            )
        inner = f"<h2>{escape(heading)}</h2><p>{escape(lead)}</p><div>{''.join(cards)}</div>"
    elif section_id == "process":
        steps = [s.strip() for s in brief.process.splitlines() if s.strip()][:3]
        inner = (
            f"<h2>{escape(heading)}</h2><ol>"
            + "".join(f"<li><p>{escape(step)}</p></li>" for step in steps)
            + "</ol>"
        )
    elif section_id == "about":
        inner = f"<h2>{escape(heading)}</h2><p>{escape(brief.difference)}</p>"
    elif section_id == "contact":
        inner = f"<h2>{escape(heading)}</h2><p>{escape(brief.contact)}</p>"
    else:
        inner = f"<h2>{escape(heading)}</h2><p>{escape(purpose)}</p><p>{escape(brief.story[:400])}</p>"
    return (
        "<!-- apf co-creation filled section — derived from studio brief, not verbatim reference copy -->\n"
        f'<section data-section-id="{escape(section_id)}" data-filled="true">\n'
        f"{inner}\n"
        "</section>\n"
    )


def studio_open_query(session_id: str, proposal_id: str, project_id: str | None = None) -> str:
    params = f"session={session_id}&proposal={proposal_id}"
    if project_id:
        params += f"&project={project_id}"
    return f"/services/site-builder.html?{params}"
