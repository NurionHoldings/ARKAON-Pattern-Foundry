"""Owner-bound URL batches for design references, without outbound website requests."""

from __future__ import annotations

import ipaddress
import json
import os
import re
from hashlib import sha256
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

SubjectType = Literal["site_draft", "platform_dialogue"]
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class DesignReferenceError(ValueError):
    pass


class DesignReferenceInput(BaseModel):
    url: str = Field(min_length=12, max_length=2048)
    focus: str = Field(default="", max_length=200)


class DesignReferenceBatch(BaseModel):
    urls: list[DesignReferenceInput] = Field(min_length=1, max_length=4)
    based_on_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")


def canonical_public_url(value: str) -> str:
    if any(ch.isspace() or ord(ch) < 32 for ch in value) or "\\" in value:
        raise DesignReferenceError("DESIGN_URL_INVALID")
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
        if (
            parsed.scheme.lower() != "https"
            or not host
            or parsed.username is not None
            or parsed.password is not None
            or port not in (None, 443)
            or parsed.query
        ):
            raise DesignReferenceError("DESIGN_URL_PUBLIC_HTTPS_REQUIRED")
        host = host.encode("idna").decode("ascii").lower().rstrip(".")
    except (ValueError, UnicodeError) as exc:
        raise DesignReferenceError("DESIGN_URL_INVALID") from exc
    if (
        host in {"localhost", "localhost.localdomain"}
        or host.endswith((".localhost", ".local", ".internal", ".test"))
        or "." not in host
        or any(not part or part.startswith("-") or part.endswith("-") for part in host.split("."))
    ):
        raise DesignReferenceError("DESIGN_URL_PUBLIC_HOST_REQUIRED")
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        pass
    else:
        raise DesignReferenceError("DESIGN_URL_IP_LITERAL_BLOCKED")
    if "%" in host or parsed.path.startswith("//"):
        raise DesignReferenceError("DESIGN_URL_INVALID")
    return urlunsplit(("https", host, parsed.path or "/", "", ""))


def _digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return "sha256:" + sha256(raw).hexdigest()


class DesignReferenceStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def append(
        self, subject_type: SubjectType, subject_id: str, *,
        tenant_id: str, owner_principal_id: str, batch: DesignReferenceBatch,
    ) -> dict[str, object]:
        UUID(subject_id)
        UUID(tenant_id)
        UUID(owner_principal_id)
        path = self._path(subject_type, subject_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = path.with_suffix(".lock")
        try:
            fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise DesignReferenceError("DESIGN_REFERENCES_BUSY") from exc
        try:
            if path.exists():
                doc = self._read(path, subject_type, subject_id, tenant_id, owner_principal_id)
                if batch.based_on_digest != doc["set_digest"]:
                    raise DesignReferenceError("DESIGN_REFERENCES_STALE")
            else:
                if batch.based_on_digest is not None:
                    raise DesignReferenceError("DESIGN_REFERENCES_STALE")
                doc = {
                    "schema_version": "apf.design-reference-set/1.0",
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                    "tenant_id": tenant_id,
                    "owner_principal_id": owner_principal_id,
                    "references": [],
                    "status": "WAITING_FOR_CAPTURE",
                }
            seen = {item["url"] for item in doc["references"]}
            additions = []
            for item in batch.urls:
                url = canonical_public_url(item.url)
                if url in seen:
                    raise DesignReferenceError("DESIGN_URL_DUPLICATE")
                seen.add(url)
                additions.append({
                    "reference_id": str(uuid4()),
                    "url": url,
                    "focus": item.focus.strip(),
                    "status": "WAITING_FOR_CAPTURE",
                })
            if len(seen) > 12:
                raise DesignReferenceError("DESIGN_URL_LIMIT")
            doc["references"] = [*doc["references"], *additions]
            doc.pop("set_digest", None)
            doc["set_digest"] = _digest(doc)
            tmp = path.with_suffix(f".{uuid4().hex}.tmp")
            try:
                with open(tmp, "x", encoding="utf-8") as file:
                    json.dump(doc, file, ensure_ascii=False, sort_keys=True)
                    file.write("\n")
                os.replace(tmp, path)
            finally:
                tmp.unlink(missing_ok=True)
            return self._public(doc)
        finally:
            os.close(fd)
            lock.unlink(missing_ok=True)

    def get(
        self, subject_type: SubjectType, subject_id: str, *,
        tenant_id: str, owner_principal_id: str,
    ) -> dict[str, object]:
        UUID(subject_id)
        return self._public(
            self._read(self._path(subject_type, subject_id), subject_type, subject_id,
                       tenant_id, owner_principal_id)
        )

    def _read(
        self, path: Path, subject_type: SubjectType, subject_id: str,
        tenant_id: str, owner_principal_id: str,
    ) -> dict[str, object]:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DesignReferenceError("DESIGN_REFERENCES_NOT_FOUND") from exc
        unsigned = {key: value for key, value in doc.items() if key != "set_digest"}
        if (
            not isinstance(doc, dict)
            or doc.get("schema_version") != "apf.design-reference-set/1.0"
            or not _DIGEST.fullmatch(str(doc.get("set_digest", "")))
            or doc["set_digest"] != _digest(unsigned)
        ):
            raise DesignReferenceError("DESIGN_REFERENCES_TAMPERED")
        if (
            doc["subject_type"] != subject_type
            or doc["subject_id"] != subject_id
            or doc["tenant_id"] != tenant_id
            or doc["owner_principal_id"] != owner_principal_id
        ):
            raise DesignReferenceError("DESIGN_REFERENCES_NOT_FOUND")
        return doc

    @staticmethod
    def _public(doc: dict[str, object]) -> dict[str, object]:
        return {
            "subject_type": doc["subject_type"],
            "subject_id": doc["subject_id"],
            "references": doc["references"],
            "set_digest": doc["set_digest"],
            "status": doc["status"],
            "capture_performed": False,
            "style_applied": False,
        }

    def _path(self, subject_type: SubjectType, subject_id: str) -> Path:
        return self.root / "state" / "design-reference-sets" / subject_type / f"{subject_id}.json"
