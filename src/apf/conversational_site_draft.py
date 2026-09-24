"""Tenant-bound deterministic static website drafts for the owner console.

This is intentionally a narrow product slice: Korean text becomes HTML/CSS only.  It
never accepts executable code, runs a build, publishes a site, or grants deployment.
"""

from __future__ import annotations

import html
import json
import os
import re
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .preview_design import FOUNDATION_CSS, LANDING_CSS


class SiteDraftError(RuntimeError):
    pass


_ID = re.compile(r"\A[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}\Z")
_DIGEST = re.compile(r"\Asha256:[0-9a-f]{64}\Z")


# This contract only describes the next safe step. It is never evidence that an
# external account, credential, repository, or deployment has been connected.
_LEGACY_EXTERNAL_CONNECTION_READINESS = {
    "schema_version": "apf.external-connection-readiness/1.0",
    "mode": "GUIDANCE_ONLY",
    "github": {
        "account": "SIGN_UP_REQUIRED",
        "app_installation": "NOT_CONNECTED",
        "repository": "NOT_SELECTED",
        "signup_url": "https://github.com/signup",
        "app_installation_guide_url": "https://docs.github.com/en/apps/using-github-apps/installing-a-github-app-from-a-third-party",
    },
    "meshy": {
        "account": "SIGN_UP_REQUIRED",
        "api_access": "NOT_CONFIGURED",
        "signup_url": "https://www.meshy.ai/",
        "api_authentication_guide_url": "https://docs.meshy.ai/en/api/authentication",
    },
    "netlify": {
        "account": "SIGN_UP_REQUIRED",
        "github_app": "NOT_CONNECTED",
        "site": "NOT_CREATED",
        "signup_url": "https://app.netlify.com/signup",
        "github_app_guide_url": "https://docs.netlify.com/build/git-workflows/repo-permissions-linking/",
        "deploy_guide_url": "https://docs.netlify.com/start/quickstarts/deploy-from-repository/",
    },
    "controls": {
        "external_login_performed": False,
        "credential_collection": False,
        "credential_storage": False,
        "meshy_job_created": False,
        "repository_write": False,
        "deployment_created": False,
    },
}


_EXTERNAL_CONNECTION_READINESS = {
    "schema_version": "apf.external-connection-readiness/1.0",
    "mode": "GUIDANCE_ONLY",
    "github": {
        "account": "SIGN_UP_REQUIRED",
        "connection_feature": "NOT_AVAILABLE",
        "repository": "NOT_SELECTED",
        "signup_url": "https://github.com/signup",
        "github_apps_reference_url": "https://docs.github.com/en/apps",
    },
    "meshy": {
        "account": "SIGN_UP_REQUIRED",
        "api_access": "NOT_CONFIGURED",
        "signup_url": "https://www.meshy.ai/",
        "api_authentication_guide_url": "https://docs.meshy.ai/en/api/authentication",
    },
    "netlify": {
        "account": "SIGN_UP_REQUIRED",
        "github_app": "NOT_CONNECTED",
        "site": "NOT_CREATED",
        "signup_url": "https://app.netlify.com/signup",
        "github_app_guide_url": "https://docs.netlify.com/build/git-workflows/repo-permissions-linking/",
        "deploy_guide_url": "https://docs.netlify.com/start/quickstarts/deploy-from-repository/",
    },
    "controls": {
        "external_login_performed": False,
        "credential_collection": False,
        "credential_storage": False,
        "meshy_job_created": False,
        "repository_write": False,
        "deployment_created": False,
    },
}


class SiteDraftRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    request: str = Field(min_length=3, max_length=4000)


class SiteDraftRevisionRequest(BaseModel):
    based_on_revision_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    change_note: str = Field(min_length=3, max_length=2000)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, min_length=3, max_length=4000)


def _digest(value: object) -> str:
    return (
        "sha256:"
        + sha256(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )


def _static_page(
    title_text: str, description: str, revision: int, change_note: str | None = None
) -> str:
    """Render a fixed editorial landing template; input remains inert text."""
    title, summary = html.escape(title_text), html.escape(description)
    change = html.escape(change_note or "처음 요청을 바탕으로 만든 초안입니다.")
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{FOUNDATION_CSS}{LANDING_CSS}</style></head>
<body><header class="site-header"><div class="wrap">
<strong class="site-brand">{title}</strong><span class="site-tag">웹사이트 초안 · v{revision} · 검토 중</span>
</div></header>
<main class="wrap landing-main">
<section class="landing-hero" aria-label="첫 화면">
<div class="hero-copy"><span class="eyebrow">YOUR IDEA, MADE VISIBLE</span>
<h1>{title}</h1><p>{summary}</p>
<div class="actions"><a href="#contact">시작하기</a>
<a class="secondary" href="#about">자세히 보기</a></div></div>
<div class="hero-art" aria-hidden="true"><div class="art-orbit"></div>
<div class="art-spark"></div></div></section>
<div class="story-grid">
<section class="story-panel" id="about"><span class="eyebrow">WHAT CHANGED</span>
<h2>이번 반영</h2><p>{change}</p></section>
<section class="story-panel" id="contact"><span class="eyebrow">NEXT STEP</span>
<h2>다음 단계</h2><p>이 화면은 검토용 정적 초안입니다. 명시 승인 전에는 공개·배포되지 않습니다.</p>
<small>생성된 코드 실행, 외부 전송, 결제 기능은 포함하지 않습니다.</small></section>
</div></main></body></html>"""


class ConversationalSiteDraftStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def create(
        self, *, tenant_id: str, owner_principal_id: str, request: SiteDraftRequest
    ) -> dict[str, object]:
        draft_id = str(uuid4())
        self._bound_uuid(tenant_id, owner_principal_id)
        first = self._revision(1, None, request.name, request.request, None)
        document: dict[str, object] = {
            "schema_version": "apf.conversational-site-draft/1.0",
            "draft_id": draft_id,
            "tenant_id": tenant_id,
            "owner_principal_id": owner_principal_id,
            "name": request.name,
            "artifact_type": "static_landing_page",
            "original_request": request.request,
            "state": "OWNER_REVIEW_REQUIRED",
            "revisions": [first],
            "approval": None,
            "automatic_implementation": False,
            "automatic_deployment": False,
        }
        document["draft_digest"] = _digest(document)
        self._exclusive_json(self._path(draft_id), document)
        return self._public(document, detail=True)

    def list_for_owner(self, *, tenant_id: str, owner_principal_id: str) -> list[dict[str, object]]:
        result = []
        root = self.root / "state" / "conversational-site-drafts"
        for path in sorted(root.glob("*.json")) if root.is_dir() else ():
            try:
                document = self._load_bound(path, tenant_id)
            except SiteDraftError:
                continue
            if document["owner_principal_id"] == owner_principal_id:
                result.append(self._public(document))
        return result

    def get(self, draft_id: str, *, tenant_id: str, owner_principal_id: str) -> dict[str, object]:
        return self._public(self._owner_bound(draft_id, tenant_id, owner_principal_id), detail=True)

    def preview_revision(
        self,
        draft_id: str,
        *,
        tenant_id: str,
        owner_principal_id: str,
        request: SiteDraftRevisionRequest,
    ) -> str:
        """Render current edits without adding a revision or approving publication."""
        doc = self._owner_bound(draft_id, tenant_id, owner_principal_id)
        latest = doc["revisions"][-1]
        if (
            doc["state"] != "OWNER_REVIEW_REQUIRED"
            or request.based_on_revision_digest != latest["revision_digest"]
        ):
            raise SiteDraftError("SITE_DRAFT_STALE_REVISION")
        return _static_page(
            request.title or str(latest["title"]),
            request.description or str(latest["description"]),
            len(doc["revisions"]) + 1,
            request.change_note,
        )

    def revise(
        self,
        draft_id: str,
        *,
        tenant_id: str,
        owner_principal_id: str,
        request: SiteDraftRevisionRequest,
    ) -> dict[str, object]:
        doc = self._owner_bound(draft_id, tenant_id, owner_principal_id)
        if (
            doc["state"] != "OWNER_REVIEW_REQUIRED"
            or request.based_on_revision_digest != doc["revisions"][-1]["revision_digest"]
        ):
            raise SiteDraftError("SITE_DRAFT_STALE_REVISION")
        revision = self._revision(
            len(doc["revisions"]) + 1,
            request.based_on_revision_digest,
            request.title or doc["revisions"][-1]["title"],
            request.description or doc["revisions"][-1]["description"],
            request.change_note,
        )
        doc["revisions"] = [*doc["revisions"], revision]
        self._rewrite(doc)
        return revision

    def rollback(
        self, draft_id: str, *, tenant_id: str, owner_principal_id: str, revision_number: int
    ) -> dict[str, object]:
        doc = self._owner_bound(draft_id, tenant_id, owner_principal_id)
        if doc["state"] != "OWNER_REVIEW_REQUIRED" or not 1 <= revision_number <= len(
            doc["revisions"]
        ):
            raise SiteDraftError("SITE_DRAFT_ROLLBACK_NOT_ALLOWED")
        source = doc["revisions"][revision_number - 1]
        revision = self._revision(
            len(doc["revisions"]) + 1,
            doc["revisions"][-1]["revision_digest"],
            source["title"],
            source["description"],
            source["change_note"],
        )
        revision["change_summary"] = f"v{revision_number} 내용을 복원한 검토용 버전"
        revision["revision_digest"] = _digest(
            {key: value for key, value in revision.items() if key != "revision_digest"}
        )
        doc["revisions"] = [*doc["revisions"], revision]
        self._rewrite(doc)
        return revision

    def request_approval(
        self, draft_id: str, *, tenant_id: str, owner_principal_id: str
    ) -> dict[str, object]:
        doc = self._owner_bound(draft_id, tenant_id, owner_principal_id)
        if doc["state"] != "OWNER_REVIEW_REQUIRED":
            raise SiteDraftError("SITE_DRAFT_APPROVAL_NOT_ALLOWED")
        approval = {
            "revision_digest": doc["revisions"][-1]["revision_digest"],
            "requested_by": owner_principal_id,
            "requested_at": datetime.now(UTC).isoformat(),
            "implementation_allowed": False,
            "deployment_allowed": False,
        }
        approval["approval_digest"] = _digest(approval)
        doc.update(state="OWNER_APPROVAL_PENDING", approval=approval)
        self._rewrite(doc)
        return approval

    def preview(
        self, draft_id: str, number: int, *, tenant_id: str, owner_principal_id: str
    ) -> str:
        doc = self._owner_bound(draft_id, tenant_id, owner_principal_id)
        if not 1 <= number <= len(doc["revisions"]):
            raise SiteDraftError("SITE_DRAFT_PREVIEW_NOT_FOUND")
        return str(doc["revisions"][number - 1]["html"])

    def _revision(
        self, number: int, base: str | None, title: str, description: str, change_note: str | None
    ) -> dict[str, object]:
        page = _static_page(title, description, number, change_note)
        value = {
            "revision_number": number,
            "based_on_revision_digest": base,
            "title": title,
            "description": description,
            "change_note": change_note or "최초 한국어 요청으로 만든 정적 웹 초안",
            "change_summary": change_note or "최초 한국어 요청으로 만든 정적 웹 초안",
            "html": page,
            "html_digest": "sha256:" + sha256(page.encode()).hexdigest(),
        }
        value["revision_digest"] = _digest(value)
        return value

    def _bound_uuid(self, tenant_id: str, owner: str) -> None:
        UUID(tenant_id)
        UUID(owner)

    def _path(self, draft_id: str) -> Path:
        return self.root / "state" / "conversational-site-drafts" / f"{draft_id}.json"

    def _bound(self, draft_id: str, tenant_id: str) -> dict[str, object]:
        if not _ID.fullmatch(draft_id):
            raise SiteDraftError("SITE_DRAFT_NOT_FOUND")
        doc = self._load_bound(self._path(draft_id), tenant_id)
        if doc["tenant_id"] != tenant_id:
            raise SiteDraftError("SITE_DRAFT_NOT_FOUND")
        return doc

    def _owner_bound(self, draft_id: str, tenant_id: str, owner: str) -> dict[str, object]:
        doc = self._bound(draft_id, tenant_id)
        if doc["owner_principal_id"] != owner:
            raise SiteDraftError("SITE_DRAFT_NOT_FOUND")
        return doc

    def _load_bound(self, path: Path, tenant_id: str) -> dict[str, object]:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SiteDraftError("SITE_DRAFT_NOT_FOUND") from exc
        unsigned = {k: v for k, v in doc.items() if k != "draft_digest"}
        if (
            not isinstance(doc, dict)
            or doc.get("schema_version") != "apf.conversational-site-draft/1.0"
            or doc.get("draft_digest") != _digest(unsigned)
            or doc.get("automatic_implementation") is not False
            or doc.get("automatic_deployment") is not False
            or (
                "external_connection_readiness" in doc
                and doc["external_connection_readiness"]
                not in (_EXTERNAL_CONNECTION_READINESS, _LEGACY_EXTERNAL_CONNECTION_READINESS)
            )
        ):
            raise SiteDraftError("SITE_DRAFT_TAMPERED")
        return doc

    def _rewrite(self, doc: dict[str, object]) -> None:
        path = self._path(str(doc["draft_id"]))
        expected = doc["draft_digest"]
        lock = path.with_suffix(".lock")
        try:
            fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise SiteDraftError("SITE_DRAFT_BUSY") from exc
        try:
            if json.loads(path.read_text(encoding="utf-8")).get("draft_digest") != expected:
                raise SiteDraftError("SITE_DRAFT_CONCURRENT_UPDATE")
            doc.pop("draft_digest")
            doc["draft_digest"] = _digest(doc)
            self._atomic_json(path, doc)
        finally:
            os.close(fd)
            lock.unlink(missing_ok=True)

    @staticmethod
    def _exclusive_json(path: Path, document: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise SiteDraftError("SITE_DRAFT_CONFLICT") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(document, stream, ensure_ascii=False, sort_keys=True)
            stream.write("\n")

    def _atomic_json(self, path: Path, document: dict[str, object]) -> None:
        tmp = path.with_suffix(f".{uuid4().hex}.tmp")
        try:
            self._exclusive_json(tmp, document)
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)

    @staticmethod
    def _public(doc: dict[str, object], detail: bool = False) -> dict[str, object]:
        value = {
            "draft_id": doc["draft_id"],
            "name": doc["name"],
            "artifact_type": doc["artifact_type"],
            "state": doc["state"],
            "revision_count": len(doc["revisions"]),
            "automatic_implementation": False,
            "automatic_deployment": False,
            "external_connection_readiness": _EXTERNAL_CONNECTION_READINESS,
        }
        if detail:
            value.update(
                original_request=doc["original_request"],
                revisions=[{k: v for k, v in r.items() if k != "html"} for r in doc["revisions"]],
                approval=doc["approval"],
            )
        return value
