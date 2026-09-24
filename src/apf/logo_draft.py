"""Tenant-bound, deterministic SVG logo studies. No image model or external API is used."""

from __future__ import annotations

import html
import json
import os
import re
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .asset_identity import make_asset_identity
from .logo_motion import Motion, animate_generated_logo


class LogoDraftError(RuntimeError):
    pass


_ID = re.compile(r"\A[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}\Z")
_HEX = re.compile(r"\A#[0-9a-fA-F]{6}\Z")


class LogoDraftRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    tagline: str = Field(min_length=1, max_length=100)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    shape: str = Field(pattern=r"^(orbit|arch|spark)$")


class LogoRollbackRequest(BaseModel):
    based_on_revision_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class LogoRevisionRequest(LogoDraftRequest):
    based_on_revision_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    selected_variant: int = Field(ge=1, le=3)
    change_note: str = Field(min_length=3, max_length=500)


def _digest(value: object) -> str:
    return (
        "sha256:"
        + sha256(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )


def _svg_text(value: str) -> str:
    # XML 1.0 permits a narrow set of code points; text stays inert after escaping.
    def xml_allowed(ch: str) -> bool:
        point = ord(ch)
        return (
            point in {0x9, 0xA, 0xD}
            or 0x20 <= point <= 0xD7FF
            or 0xE000 <= point <= 0xFFFD
            or 0x10000 <= point <= 0x10FFFF
        )

    return html.escape("".join(ch for ch in value if xml_allowed(ch)), quote=True)


def _svg(name: str, tagline: str, color: str, shape: str, variant: int) -> str:
    if not _HEX.fullmatch(color):
        raise LogoDraftError("LOGO_DRAFT_INVALID_COLOR")
    title, line = _svg_text(name), _svg_text(tagline)
    mark = {
        "orbit": (
            f'<circle cx="86" cy="86" r="48" fill="none" stroke="{color}" stroke-width="14"/>'
            f'<circle cx="124" cy="48" r="15" fill="{color}"/>'
        ),
        "arch": f'<path d="M38 132V86a48 48 0 0 1 96 0v46H108V88a22 22 0 0 0-44 0v44Z" fill="{color}"/>',
        "spark": f'<path d="m86 25 14 47 47 14-47 14-14 47-14-47-47-14 47-14Z" fill="{color}"/>',
    }[shape]
    if variant == 2:
        mark = f'<g transform="rotate(18 86 86)">{mark}</g>'
    elif variant == 3:
        mark = f'<g transform="scale(.82) translate(19 19)">{mark}</g><circle cx="132" cy="132" r="13" fill="{color}"/>'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 180" role="img" aria-labelledby="title desc"><title id="title">{title} logo study {variant}</title><desc id="desc">Deterministic shape and text based SVG logo study.</desc><rect width="720" height="180" rx="28" fill="#ffffff"/><g>{mark}</g><text x="188" y="85" fill="#182235" font-family="Arial, sans-serif" font-size="42" font-weight="700">{title}</text><text x="190" y="117" fill="#5b677a" font-family="Arial, sans-serif" font-size="17">{line}</text><text x="190" y="146" fill="{color}" font-family="Arial, sans-serif" font-size="12" letter-spacing="2">STUDY 0{variant}</text></svg>'''


class LogoDraftStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def create(
        self, *, tenant_id: str, owner_principal_id: str, request: LogoDraftRequest
    ) -> dict[str, object]:
        UUID(tenant_id)
        UUID(owner_principal_id)
        draft_id = str(uuid4())
        revision = self._revision(1, None, request, 1, "첫 도형·텍스트 기반 시안")
        doc: dict[str, object] = {
            "schema_version": "apf.logo-draft/1.0",
            "draft_id": draft_id,
            "tenant_id": tenant_id,
            "owner_principal_id": owner_principal_id,
            "artifact_type": "logo_svg",
            "state": "OWNER_REVIEW_REQUIRED",
            "revisions": [revision],
            "generation": "DETERMINISTIC_VECTOR_ONLY",
            "approval": None,
            "intent_dna": make_asset_identity(
                tenant_id=tenant_id, owner_principal_id=owner_principal_id,
                artifact_type="logo_svg", artifact_id=draft_id,
                original_intent=request.model_dump(mode="json"),
                dna={"shape": request.shape, "color": request.color.lower(),
                     "variants": 3, "generation": "DETERMINISTIC_VECTOR_ONLY"},
            ),
        }
        doc["draft_digest"] = _digest(doc)
        self._exclusive_json(self._path(draft_id), doc)
        return self._public(doc, True)

    def list_for_owner(self, *, tenant_id: str, owner_principal_id: str) -> list[dict[str, object]]:
        root = self.root / "state" / "logo-drafts"
        return [
            self._public(doc)
            for path in sorted(root.glob("*.json"))
            for doc in [self._load(path)]
            if doc.get("tenant_id") == tenant_id
            and doc.get("owner_principal_id") == owner_principal_id
        ]

    def get(self, draft_id: str, *, tenant_id: str, owner_principal_id: str) -> dict[str, object]:
        return self._public(self._owner_bound(draft_id, tenant_id, owner_principal_id), True)

    def revise(
        self,
        draft_id: str,
        *,
        tenant_id: str,
        owner_principal_id: str,
        request: LogoRevisionRequest,
    ) -> dict[str, object]:
        doc = self._owner_bound(draft_id, tenant_id, owner_principal_id)
        if (
            doc["state"] != "OWNER_REVIEW_REQUIRED"
            or request.based_on_revision_digest != doc["revisions"][-1]["revision_digest"]
        ):
            raise LogoDraftError("LOGO_DRAFT_STALE_REVISION")
        revision = self._revision(
            len(doc["revisions"]) + 1,
            request.based_on_revision_digest,
            request,
            request.selected_variant,
            request.change_note,
        )
        doc["revisions"] = [*doc["revisions"], revision]
        self._rewrite(doc)
        return self._public_revision(revision)

    def rollback(
        self,
        draft_id: str,
        number: int,
        *,
        tenant_id: str,
        owner_principal_id: str,
        based_on_revision_digest: str,
    ) -> dict[str, object]:
        doc = self._owner_bound(draft_id, tenant_id, owner_principal_id)
        if doc["state"] != "OWNER_REVIEW_REQUIRED" or not 1 <= number <= len(doc["revisions"]):
            raise LogoDraftError("LOGO_DRAFT_ROLLBACK_NOT_ALLOWED")
        if based_on_revision_digest != doc["revisions"][-1]["revision_digest"]:
            raise LogoDraftError("LOGO_DRAFT_STALE_REVISION")
        source, current = doc["revisions"][number - 1], doc["revisions"][-1]
        request = LogoDraftRequest(
            name=source["name"],
            tagline=source["tagline"],
            color=source["color"],
            shape=source["shape"],
        )
        revision = self._revision(
            len(doc["revisions"]) + 1,
            current["revision_digest"],
            request,
            source["selected_variant"],
            f"v{number} 시안을 복원",
        )
        doc["revisions"] = [*doc["revisions"], revision]
        self._rewrite(doc)
        return self._public_revision(revision)

    def download(
        self, draft_id: str, *, tenant_id: str, owner_principal_id: str
    ) -> tuple[str, str]:
        doc = self._owner_bound(draft_id, tenant_id, owner_principal_id)
        revision = doc["revisions"][-1]
        return revision["variants"][revision["selected_variant"] - 1][
            "svg"
        ], f"{doc['draft_id']}-logo.svg"

    def animated_download(
        self, draft_id: str, *, tenant_id: str, owner_principal_id: str, motion: Motion
    ) -> tuple[str, str]:
        svg, filename = self.download(
            draft_id, tenant_id=tenant_id, owner_principal_id=owner_principal_id
        )
        return animate_generated_logo(svg, motion), filename.replace(".svg", f"-{motion}.svg")

    def _revision(
        self, number: int, base: str | None, request: LogoDraftRequest, selected: int, note: str
    ) -> dict[str, object]:
        variants = [
            {
                "variant": item,
                "svg": _svg(request.name, request.tagline, request.color, request.shape, item),
            }
            for item in range(1, 4)
        ]
        value = {
            "revision_number": number,
            "based_on_revision_digest": base,
            "name": request.name,
            "tagline": request.tagline,
            "color": request.color.lower(),
            "shape": request.shape,
            "selected_variant": selected,
            "change_note": note,
            "variants": variants,
        }
        value["revision_digest"] = _digest(value)
        return value

    def _path(self, draft_id: str) -> Path:
        return self.root / "state" / "logo-drafts" / f"{draft_id}.json"

    def _owner_bound(self, draft_id: str, tenant: str, owner: str) -> dict[str, object]:
        if not _ID.fullmatch(draft_id):
            raise LogoDraftError("LOGO_DRAFT_NOT_FOUND")
        doc = self._load(self._path(draft_id))
        if doc["tenant_id"] != tenant or doc["owner_principal_id"] != owner:
            raise LogoDraftError("LOGO_DRAFT_NOT_FOUND")
        return doc

    def _load(self, path: Path) -> dict[str, object]:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LogoDraftError("LOGO_DRAFT_NOT_FOUND") from exc
        unsigned = {key: value for key, value in doc.items() if key != "draft_digest"}
        if (
            not isinstance(doc, dict)
            or doc.get("schema_version") != "apf.logo-draft/1.0"
            or doc.get("draft_digest") != _digest(unsigned)
            or doc.get("generation") != "DETERMINISTIC_VECTOR_ONLY"
        ):
            raise LogoDraftError("LOGO_DRAFT_TAMPERED")
        return doc

    def _rewrite(self, doc: dict[str, object]) -> None:
        path = self._path(str(doc["draft_id"]))
        expected = doc["draft_digest"]
        lock = path.with_suffix(".lock")
        try:
            fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise LogoDraftError("LOGO_DRAFT_BUSY") from exc
        try:
            if json.loads(path.read_text(encoding="utf-8")).get("draft_digest") != expected:
                raise LogoDraftError("LOGO_DRAFT_CONCURRENT_UPDATE")
            doc.pop("draft_digest")
            doc["draft_digest"] = _digest(doc)
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
            raise LogoDraftError("LOGO_DRAFT_CONFLICT") from exc
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
        return {
            **revision,
            "variants": [
                {"variant": item["variant"], "svg": item["svg"]} for item in revision["variants"]
            ],
        }

    @classmethod
    def _public(cls, doc: dict[str, object], detail: bool = False) -> dict[str, object]:
        result = {
            "draft_id": doc["draft_id"],
            "artifact_type": "logo_svg",
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
