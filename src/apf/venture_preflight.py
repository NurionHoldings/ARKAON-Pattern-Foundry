"""Evidence-first preflight for new ventures and real-person IP projects."""
from __future__ import annotations

import json
from hashlib import sha256
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator


class VenturePreflightError(ValueError):
    pass

class VentureIntent(BaseModel):
    project_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")
    working_title: str = Field(min_length=1, max_length=120)
    purpose: str = Field(min_length=20, max_length=2000)
    audiences: list[str] = Field(min_length=1, max_length=20)
    markets: list[str] = Field(min_length=1, max_length=20)
    revenue_hypotheses: list[str] = Field(default_factory=list, max_length=30)
    public_figure_inspired: bool = False
    public_figure_name: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def require_figure_name(self) -> VentureIntent:
        if self.public_figure_inspired and not self.public_figure_name:
            raise ValueError("public figure name required")
        return self

class RightsEnvelope(BaseModel):
    identity_license_verified: bool = False
    name_likeness_voice_scope: list[str] = Field(default_factory=list, max_length=20)
    trademark_clearance_verified: bool = False
    archive_media_rights_verified: bool = False
    territory_and_term_defined: bool = False
    revenue_share_defined: bool = False
    evidence_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")

    @property
    def commercially_ready(self) -> bool:
        return all((self.identity_license_verified, self.trademark_clearance_verified,
                    self.territory_and_term_defined, self.evidence_digest is not None))

class EvidenceCandidate(BaseModel):
    evidence_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")
    topic: str = Field(min_length=3, max_length=160)
    source_url: str
    source_type: str = Field(pattern=r"^(official_person|official_brand|official_registry|official_law|official_statistics|licensed_material|reputable_secondary)$")
    jurisdiction: str = Field(min_length=2, max_length=80)
    retrieved_at: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}T")
    claim: str | None = Field(default=None, max_length=1000)
    verification_status: str = Field(default="PENDING", pattern=r"^(PENDING|VERIFIED|REJECTED|STALE)$")

    @model_validator(mode="after")
    def require_https(self) -> EvidenceCandidate:
        parsed = urlparse(self.source_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("HTTPS evidence source required")
        if self.verification_status == "VERIFIED" and (not self.retrieved_at or not self.claim):
            raise ValueError("verified evidence requires retrieval time and bounded claim")
        return self

class WorkPacket(BaseModel):
    packet_id: str
    discipline: str
    objective: str
    required_outputs: list[str]
    acceptance_checks: list[str]
    blocks_implementation: bool

class VenturePreflight(BaseModel):
    schema_version: str = "apf.venture-preflight/1.0"
    project_id: str
    status: str
    evidence_digest: str
    work_packets: list[WorkPacket]
    unresolved_gates: list[str]
    next_action: str
    planning_allowed: bool = True
    prototype_allowed: bool = False
    commercial_use_allowed: bool = False
    deployment_allowed: bool = False

_DEFAULT_PACKETS = (
    WorkPacket(packet_id="intelligence.search", discipline="검색",
        objective="공식·1차 출처 우선으로 시장, 유사사례, 소비자 문제와 국가별 차이를 조사한다.",
        required_outputs=["검색어 매트릭스", "출처 원장", "상충 주장 목록", "정보 공백 목록"],
        acceptance_checks=["모든 주장에 URL과 검색시각", "사실·추론·가설 분리", "국가별 최신성 확인"],
        blocks_implementation=False),
    WorkPacket(packet_id="intelligence.analysis", discipline="분석",
        objective="사례의 외형이 아니라 가치제안, 유통, 수익, 실패 원인과 재사용 가능한 원리를 추출한다.",
        required_outputs=["사례 비교표", "성공요인", "실패·반발 요인", "clean-room 원리"],
        acceptance_checks=["최소 3개 독립 사례군", "단일 사례 일반화 금지", "복제 표현 제외"],
        blocks_implementation=False),
    WorkPacket(packet_id="venture.design", discipline="기획",
        objective="대상별 문제, 캐릭터 세계관, 콘텐츠, 상품, 공익성과 수익 흐름을 하나의 사업 구조로 설계한다.",
        required_outputs=["대상 세그먼트", "가치제안", "IP 바이블 초안", "수익모델", "단계별 실험"],
        acceptance_checks=["골프 비이용자 가치 포함", "공익·상업 회계 구분", "중단 기준 명시"],
        blocks_implementation=False),
    WorkPacket(packet_id="rights.clearance", discipline="권리·평판",
        objective="실존 인물의 성명, 초상, 음성, 서명, 경기자료와 상표 사용 범위를 계약 증거로 확정한다.",
        required_outputs=["권리 매트릭스", "허락 주체", "지역·기간·매체 범위", "승인·철회 절차"],
        acceptance_checks=["서면 증거 digest", "2차 창작·AI 학습 범위", "미성년자 대상 안전 검토"],
        blocks_implementation=True),
    WorkPacket(packet_id="product.prototype", discipline="구현",
        objective="권리 미확정 표현을 배제한 저비용 프로토타입으로 핵심 가설을 시험한다.",
        required_outputs=["텍스트/와이어프레임 프로토타입", "측정계획", "접근성 점검", "삭제·롤백 계획"],
        acceptance_checks=["실제 이름·얼굴·목소리 미사용", "개인정보 최소화", "승인 전 공개·판매 금지"],
        blocks_implementation=True),
    WorkPacket(packet_id="operations.launch", discipline="운영",
        objective="제작, 검수, 유통, 정산, 고객보호, 위조대응과 위기대응을 운영 가능한 형태로 만든다.",
        required_outputs=["RACI", "상품 원장", "정산 흐름", "CS·리콜·위조 대응", "KPI 대시보드"],
        acceptance_checks=["소유자 승인 분리", "감사로그", "공급망·품질 책임자", "국가별 판매조건"],
        blocks_implementation=True),
)

def evidence_digest(evidence: list[EvidenceCandidate]) -> str:
    payload = [item.model_dump(mode="json") for item in sorted(evidence, key=lambda x: x.evidence_id)]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + sha256(encoded).hexdigest()

def build_preflight(intent: VentureIntent, rights: RightsEnvelope,
                    evidence: list[EvidenceCandidate], *,
                    specification_approved: bool = False,
                    sandbox_approved: bool = False) -> VenturePreflight:
    ids = [item.evidence_id for item in evidence]
    if len(ids) != len(set(ids)):
        raise VenturePreflightError("EVIDENCE_ID_DUPLICATE")
    unresolved: list[str] = []
    if len([item for item in evidence if item.verification_status == "VERIFIED"]) < 3:
        unresolved.append("EVIDENCE_DIVERSITY_AND_VERIFICATION")
    if intent.public_figure_inspired and not rights.commercially_ready:
        unresolved.append("PUBLIC_FIGURE_RIGHTS_CLEARANCE")
    if not specification_approved:
        unresolved.append("SPECIFICATION_APPROVAL")
    if not sandbox_approved:
        unresolved.append("SANDBOX_APPROVAL")
    prototype_allowed = (specification_approved and sandbox_approved and
                         "EVIDENCE_DIVERSITY_AND_VERIFICATION" not in unresolved)
    commercial_allowed = prototype_allowed and (
        not intent.public_figure_inspired or rights.commercially_ready)
    status = "READY_FOR_CONTROLLED_PROTOTYPE" if prototype_allowed else "RESEARCH_AND_PLANNING_ONLY"
    if commercial_allowed:
        status = "RIGHTS_CLEARED_SANDBOX_ONLY"
    return VenturePreflight(
        project_id=intent.project_id, status=status,
        evidence_digest=evidence_digest(evidence), work_packets=list(_DEFAULT_PACKETS),
        unresolved_gates=unresolved,
        next_action=("EXECUTE_RESEARCH_PACKETS" if
                     "EVIDENCE_DIVERSITY_AND_VERIFICATION" in unresolved
                     else "REQUEST_REQUIRED_APPROVALS"),
        prototype_allowed=prototype_allowed, commercial_use_allowed=commercial_allowed,
        deployment_allowed=False)
