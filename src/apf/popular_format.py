"""Owner-bound, manually evidenced format proposals; never imports source media."""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

PLATFORMS = {"capcut", "youtube", "tiktok", "instagram"}
HOSTS = {
    "capcut": ("capcut.com",),
    "youtube": ("youtube.com", "youtu.be"),
    "tiktok": ("tiktok.com",),
    "instagram": ("instagram.com",),
}


class Evidence(BaseModel):
    platform: str
    url: str = Field(max_length=1000)
    observed_at: datetime
    region: str = Field(min_length=2, max_length=40)
    category: str = Field(min_length=2, max_length=80)
    metric_scope: str = Field(min_length=3, max_length=200)
    public_signal: str = Field(min_length=3, max_length=200)
    rights_status: str = Field(pattern="^(reference_only|commercial_use_verified)$")
    principle: str = Field(min_length=5, max_length=180)

    @field_validator("url")
    @classmethod
    def safe_url(cls, value: str, info):
        platform = info.data.get("platform")
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
        if (parsed.scheme != "https" or parsed.username or parsed.password
                or platform not in PLATFORMS
                or not any(host == d or host.endswith('.' + d) for d in HOSTS[platform])):
            raise ValueError("official platform HTTPS URL required")
        return value

    @field_validator("observed_at")
    @classmethod
    def observed_date(cls, value: datetime):
        if value.tzinfo is None or value > datetime.now(UTC) + timedelta(minutes=5):
            raise ValueError("timezone-aware past observation required")
        return value


class ProposalRequest(BaseModel):
    artifact_type: str = Field(pattern="^(site_draft|logo_draft|business_card|platform_dialogue)$")
    record_id: str = Field(min_length=1, max_length=128)
    asset_id: str
    source_revision_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    intent_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    dna_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    purpose: str = Field(min_length=3, max_length=120)
    audience: str = Field(min_length=3, max_length=120)
    brand_message: str = Field(min_length=3, max_length=120)
    evidence: list[Evidence] = Field(min_length=1, max_length=8)


class Decision(BaseModel):
    proposal_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    variant_id: str = Field(pattern="^[a-c]$")
    decision: str = Field(pattern="^(APPROVE|REJECT)$")


def digest(data):
    return "sha256:" + sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def build(payload: ProposalRequest, identity: dict, owner: str, tenant: str) -> dict:
    data = payload.model_dump(mode="json")
    if any(data[k] != identity[k] for k in ("asset_id", "intent_digest", "dna_digest")):
        raise ValueError("ASSET_IDENTITY_MISMATCH")
    recent = all(datetime.fromisoformat(item["observed_at"]) >= datetime.now(UTC) - timedelta(days=30) for item in data["evidence"])
    # A URL and human-reported signal are traceable references, not verified popularity.
    themes = [
        ("명확한 첫 화면", "핵심 메시지를 첫 화면에 크게 배치하고 바로 행동을 제안", "headline_first"),
        ("단계별 설명", "고객의 문제·해결 과정·선택 단계를 짧게 이어서 표현", "step_story"),
        ("결과 먼저 보기", "완성 결과를 먼저 보여주고 근거와 다음 행동을 연결", "result_first"),
    ]
    variants = []
    for idx, (title, method, layout) in enumerate(themes):
        variants.append({"id": "abc"[idx], "title": title, "layout": layout,
                         "preview": {"headline": data["brand_message"], "audience": data["audience"],
                                     "purpose": data["purpose"], "description": method,
                                     "aspect_ratio": "9:16" if idx != 1 else "16:9"},
                         "why": f"{data['audience']}에게 {data['purpose']}을 설명하는 독립 구성",
                         "changes": method})
    proposal = {"proposal_id": str(uuid4()), "state": "OWNER_REVIEW_REQUIRED",
                "owner_principal_id": owner, "tenant_id": tenant,
                "asset_id": data["asset_id"], "artifact_type": data["artifact_type"],
                "record_id": data["record_id"], "source_revision_digest": data["source_revision_digest"],
                "intent_digest": data["intent_digest"], "dna_digest": data["dna_digest"],
                "evidence": data["evidence"], "evidence_digest": digest(data["evidence"]),
                "popularity": "POPULARITY_NOT_VERIFIED", "recent_observation": recent,
                "rights": "REFERENCE_ONLY_NO_SOURCE_MEDIA_USED", "variants": variants,
                "automatic_publication": False, "deployment": False, "decision": None}
    proposal["proposal_digest"] = digest(proposal)
    return proposal


class ProposalStore:
    def __init__(self, root: Path):
        self.path = root / "state" / "popular-format-proposals.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS proposals (id TEXT PRIMARY KEY, tenant TEXT NOT NULL, owner TEXT NOT NULL, document TEXT NOT NULL)")

    def _connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def create(self, document: dict):
        with self._connect() as db:
            db.execute("INSERT INTO proposals VALUES (?, ?, ?, ?)",
                       (document["proposal_id"], document["tenant_id"], document["owner_principal_id"], json.dumps(document, ensure_ascii=False)))
        return document

    def get(self, proposal_id: str, tenant: str, owner: str):
        with self._connect() as db:
            row = db.execute("SELECT document FROM proposals WHERE id=? AND tenant=? AND owner=?", (proposal_id, tenant, owner)).fetchone()
        if row is None:
            raise KeyError("proposal not found")
        return json.loads(row[0])

    def decide(self, proposal_id: str, tenant: str, owner: str, choice: Decision, identity: dict, latest_digest: str):
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT document FROM proposals WHERE id=? AND tenant=? AND owner=?", (proposal_id, tenant, owner)).fetchone()
            if row is None:
                raise KeyError("proposal not found")
            doc = json.loads(row[0])
            if doc["state"] != "OWNER_REVIEW_REQUIRED" or doc["proposal_digest"] != choice.proposal_digest:
                raise ValueError("PROPOSAL_ALREADY_DECIDED_OR_STALE")
            if doc["source_revision_digest"] != latest_digest or any(doc[k] != identity[k] for k in ("asset_id", "intent_digest", "dna_digest")):
                raise ValueError("SOURCE_REVISION_CHANGED")
            doc["state"] = "PROPOSAL_APPROVED" if choice.decision == "APPROVE" else "PROPOSAL_REJECTED"
            doc["decision"] = {"variant_id": choice.variant_id, "decision": choice.decision,
                               "at": datetime.now(UTC).isoformat(), "owner": owner}
            doc["recommendation_revision_digest"] = digest(doc)
            db.execute("UPDATE proposals SET document=? WHERE id=?", (json.dumps(doc, ensure_ascii=False), proposal_id))
        return doc
