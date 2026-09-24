"""Owner-bound deterministic SVG business-card drafts; no external calls or image generation."""

from __future__ import annotations

import html
import json
import os
import re
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4
from xml.etree import ElementTree

from pydantic import BaseModel, Field

from .asset_identity import make_asset_identity
from .logo_draft import LogoDraftError, LogoDraftStore


class BusinessCardError(RuntimeError):
    pass


_ID = re.compile(r"\A[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}\Z")


class BusinessCardRequest(BaseModel):
    logo_draft_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=1, max_length=160)
    brand_text: str = Field(min_length=1, max_length=100)


class BusinessCardRevisionRequest(BusinessCardRequest):
    based_on_revision_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    change_note: str = Field(min_length=3, max_length=500)


class BusinessCardRollbackRequest(BaseModel):
    based_on_revision_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


def _digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + sha256(encoded).hexdigest()


def _text(value: str) -> str:
    def allowed(ch: str) -> bool:
        p = ord(ch)
        return (
            p in {9, 10, 13}
            or 0x20 <= p <= 0xD7FF
            or 0xE000 <= p <= 0xFFFD
            or 0x10000 <= p <= 0x10FFFF
        )

    return html.escape("".join(ch for ch in value if allowed(ch)), quote=True)


def _logo_fragment(logo_svg: str) -> str:
    """Parse the digest-validated SVG and retain the complete mark group, including nested variants."""
    try:
        root = ElementTree.fromstring(logo_svg)
    except ElementTree.ParseError as exc:
        raise BusinessCardError("BUSINESS_CARD_LOGO_INVALID") from exc
    namespace = "{http://www.w3.org/2000/svg}"
    if root.tag != f"{namespace}svg":
        raise BusinessCardError("BUSINESS_CARD_LOGO_INVALID")
    mark = next((item for item in root if item.tag == f"{namespace}g"), None)
    if mark is None:
        raise BusinessCardError("BUSINESS_CARD_LOGO_INVALID")
    return ElementTree.tostring(mark, encoding="unicode")


def _front(logo_svg: str, name: str, title: str, phone: str, email: str, brand: str) -> str:
    mark = _logo_fragment(logo_svg)
    n, t, p, e, b = map(_text, (name, title, phone, email, brand))
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1050 600" role="img" aria-labelledby="title desc"><title id="title">{n} business card front</title><desc id="desc">Deterministic vector business card front.</desc><rect width="1050" height="600" rx="36" fill="#fffdf8"/><rect x="0" width="28" height="600" fill="#182235"/><g transform="translate(68 66) scale(.82)">{mark}</g><text x="72" y="238" fill="#182235" font-family="Arial, sans-serif" font-size="50" font-weight="700">{n}</text><text x="75" y="278" fill="#5b677a" font-family="Arial, sans-serif" font-size="22">{t}</text><line x1="74" y1="330" x2="506" y2="330" stroke="#d8dde7"/><text x="75" y="385" fill="#26364e" font-family="Arial, sans-serif" font-size="22">{p}</text><text x="75" y="425" fill="#26364e" font-family="Arial, sans-serif" font-size="22">{e}</text><text x="75" y="515" fill="#182235" font-family="Arial, sans-serif" font-size="18" letter-spacing="3">{b}</text></svg>"""


def _back(logo_svg: str, brand: str) -> str:
    mark = _logo_fragment(logo_svg)
    b = _text(brand)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1050 600" role="img" aria-labelledby="title desc"><title id="title">{b} business card back</title><desc id="desc">Deterministic vector business card back.</desc><rect width="1050" height="600" rx="36" fill="#182235"/><path d="M0 0H1050V136C775 212 347 198 0 85Z" fill="#243b63"/><g transform="translate(420 160) scale(1.25)">{mark}</g><text x="525" y="482" fill="#ffffff" text-anchor="middle" font-family="Arial, sans-serif" font-size="34" font-weight="700" letter-spacing="4">{b}</text><text x="525" y="523" fill="#c7d6fa" text-anchor="middle" font-family="Arial, sans-serif" font-size="16" letter-spacing="3">DESIGNED AS VECTOR</text></svg>"""


class BusinessCardStore:
    def __init__(self, root: Path, logo_store: LogoDraftStore) -> None:
        self.root, self.logo_store = root.resolve(), logo_store

    def preview(
        self, *, tenant_id: str, owner_principal_id: str, request: BusinessCardRequest
    ) -> dict[str, str]:
        """Render an owner-bound SVG pair without persisting a card or contact details."""
        UUID(tenant_id)
        UUID(owner_principal_id)
        try:
            logo_svg, _ = self.logo_store.download(
                request.logo_draft_id, tenant_id=tenant_id, owner_principal_id=owner_principal_id
            )
        except LogoDraftError as exc:
            raise BusinessCardError("BUSINESS_CARD_LOGO_NOT_FOUND") from exc
        return {
            "front_svg": _front(
                logo_svg, request.name, request.title, request.phone, request.email, request.brand_text
            ),
            "back_svg": _back(logo_svg, request.brand_text),
        }

    def create(
        self, *, tenant_id: str, owner_principal_id: str, request: BusinessCardRequest
    ) -> dict[str, object]:
        UUID(tenant_id)
        UUID(owner_principal_id)
        card_id = str(uuid4())
        revision = self._revision(
            1, None, tenant_id, owner_principal_id, request, "명함 앞·뒤 SVG 시안 생성"
        )
        doc: dict[str, object] = {
            "schema_version": "apf.business-card/1.0",
            "card_id": card_id,
            "tenant_id": tenant_id,
            "owner_principal_id": owner_principal_id,
            "artifact_type": "business_card_svg",
            "state": "OWNER_REVIEW_REQUIRED",
            "generation": "DETERMINISTIC_VECTOR_ONLY",
            "revisions": [revision],
            "intent_dna": make_asset_identity(
                tenant_id=tenant_id, owner_principal_id=owner_principal_id,
                artifact_type="business_card_svg", artifact_id=card_id,
                original_intent={"logo_draft_id": request.logo_draft_id,
                                 "purpose": "business_card_front_back"},
                dna={"logo_draft_id": request.logo_draft_id,
                     "faces": ["front", "back"], "layout": "SVG",
                     "contact_content": "NOT_STORED_IN_DNA"},
            ),
        }
        doc["card_digest"] = _digest(doc)
        self._exclusive_json(self._path(card_id), doc)
        return self._public(doc, True)

    def list_for_owner(self, *, tenant_id: str, owner_principal_id: str) -> list[dict[str, object]]:
        root = self.root / "state" / "business-cards"
        return [
            self._public(doc)
            for path in sorted(root.glob("*.json"))
            for doc in [self._load(path)]
            if doc.get("tenant_id") == tenant_id
            and doc.get("owner_principal_id") == owner_principal_id
        ]

    def get(self, card_id: str, *, tenant_id: str, owner_principal_id: str) -> dict[str, object]:
        return self._public(self._owner_bound(card_id, tenant_id, owner_principal_id), True)

    def revise(
        self,
        card_id: str,
        *,
        tenant_id: str,
        owner_principal_id: str,
        request: BusinessCardRevisionRequest,
    ) -> dict[str, object]:
        doc = self._owner_bound(card_id, tenant_id, owner_principal_id)
        if (
            doc["state"] != "OWNER_REVIEW_REQUIRED"
            or request.based_on_revision_digest != doc["revisions"][-1]["revision_digest"]
        ):
            raise BusinessCardError("BUSINESS_CARD_STALE_REVISION")
        revision = self._revision(
            len(doc["revisions"]) + 1,
            request.based_on_revision_digest,
            tenant_id,
            owner_principal_id,
            request,
            request.change_note,
        )
        doc["revisions"] = [*doc["revisions"], revision]
        self._rewrite(doc)
        return self._public_revision(revision)

    def rollback(
        self,
        card_id: str,
        number: int,
        *,
        tenant_id: str,
        owner_principal_id: str,
        based_on_revision_digest: str,
    ) -> dict[str, object]:
        doc = self._owner_bound(card_id, tenant_id, owner_principal_id)
        if doc["state"] != "OWNER_REVIEW_REQUIRED" or not 1 <= number <= len(doc["revisions"]):
            raise BusinessCardError("BUSINESS_CARD_ROLLBACK_NOT_ALLOWED")
        current = doc["revisions"][-1]
        if based_on_revision_digest != current["revision_digest"]:
            raise BusinessCardError("BUSINESS_CARD_STALE_REVISION")
        source = doc["revisions"][number - 1]
        revision = self._revision_from_snapshot(
            len(doc["revisions"]) + 1,
            current["revision_digest"],
            source,
            f"v{number} 명함 내용 복원",
        )
        doc["revisions"] = [*doc["revisions"], revision]
        self._rewrite(doc)
        return self._public_revision(revision)

    def download(
        self, card_id: str, side: str, *, tenant_id: str, owner_principal_id: str
    ) -> tuple[str, str]:
        if side not in {"front", "back"}:
            raise BusinessCardError("BUSINESS_CARD_INVALID_SIDE")
        doc = self._owner_bound(card_id, tenant_id, owner_principal_id)
        return doc["revisions"][-1][f"{side}_svg"], f"{doc['card_id']}-{side}.svg"

    def _revision(
        self,
        number: int,
        base: str | None,
        tenant: str,
        owner: str,
        request: BusinessCardRequest,
        note: str,
    ) -> dict[str, object]:
        try:
            logo_svg, _ = self.logo_store.download(
                request.logo_draft_id, tenant_id=tenant, owner_principal_id=owner
            )
        except LogoDraftError as exc:
            raise BusinessCardError("BUSINESS_CARD_LOGO_NOT_FOUND") from exc
        value = {
            "revision_number": number,
            "based_on_revision_digest": base,
            **request.model_dump(),
            "change_note": note,
            "front_svg": _front(
                logo_svg,
                request.name,
                request.title,
                request.phone,
                request.email,
                request.brand_text,
            ),
            "back_svg": _back(logo_svg, request.brand_text),
        }
        value["revision_digest"] = _digest(value)
        return value

    @staticmethod
    def _revision_from_snapshot(
        number: int, base: str, source: dict[str, object], note: str
    ) -> dict[str, object]:
        """Restore the stored SVG pair without reading a logo that may since have changed."""
        value = {
            "revision_number": number,
            "based_on_revision_digest": base,
            **{key: source[key] for key in BusinessCardRequest.model_fields},
            "change_note": note,
            "front_svg": source["front_svg"],
            "back_svg": source["back_svg"],
        }
        value["revision_digest"] = _digest(value)
        return value

    def _path(self, card_id: str) -> Path:
        return self.root / "state" / "business-cards" / f"{card_id}.json"

    def _owner_bound(self, card_id: str, tenant: str, owner: str) -> dict[str, object]:
        if not _ID.fullmatch(card_id):
            raise BusinessCardError("BUSINESS_CARD_NOT_FOUND")
        doc = self._load(self._path(card_id))
        if doc["tenant_id"] != tenant or doc["owner_principal_id"] != owner:
            raise BusinessCardError("BUSINESS_CARD_NOT_FOUND")
        return doc

    def _load(self, path: Path) -> dict[str, object]:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BusinessCardError("BUSINESS_CARD_NOT_FOUND") from exc
        if not isinstance(doc, dict):
            raise BusinessCardError("BUSINESS_CARD_TAMPERED")
        unsigned = {k: v for k, v in doc.items() if k != "card_digest"}
        if (
            doc.get("schema_version") != "apf.business-card/1.0"
            or doc.get("generation") != "DETERMINISTIC_VECTOR_ONLY"
            or doc.get("card_digest") != _digest(unsigned)
        ):
            raise BusinessCardError("BUSINESS_CARD_TAMPERED")
        return doc

    def _rewrite(self, doc: dict[str, object]) -> None:
        path = self._path(str(doc["card_id"]))
        expected = doc["card_digest"]
        lock = path.with_suffix(".lock")
        try:
            fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise BusinessCardError("BUSINESS_CARD_BUSY") from exc
        try:
            if json.loads(path.read_text(encoding="utf-8")).get("card_digest") != expected:
                raise BusinessCardError("BUSINESS_CARD_CONCURRENT_UPDATE")
            doc.pop("card_digest")
            doc["card_digest"] = _digest(doc)
            self._atomic_json(path, doc)
        finally:
            os.close(fd)
            lock.unlink(missing_ok=True)

    @staticmethod
    def _exclusive_json(path: Path, doc: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise BusinessCardError("BUSINESS_CARD_CONFLICT") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(doc, out, ensure_ascii=False, sort_keys=True)
            out.write("\n")

    def _atomic_json(self, path: Path, doc: dict[str, object]) -> None:
        tmp = path.with_suffix(f".{uuid4().hex}.tmp")
        try:
            self._exclusive_json(tmp, doc)
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)

    @staticmethod
    def _public_revision(revision: dict[str, object]) -> dict[str, object]:
        return {**revision}

    @classmethod
    def _public(cls, doc: dict[str, object], detail: bool = False) -> dict[str, object]:
        result = {
            "card_id": doc["card_id"],
            "artifact_type": "business_card_svg",
            "state": doc["state"],
            "revision_count": len(doc["revisions"]),
            "generation": "DETERMINISTIC_VECTOR_ONLY",
            "credit_cap": 500,
            "credit_meter": "UNAVAILABLE",
            "intent_dna": doc.get("intent_dna"),
        }
        if detail:
            result["revisions"] = [cls._public_revision(item) for item in doc["revisions"]]
        return result
