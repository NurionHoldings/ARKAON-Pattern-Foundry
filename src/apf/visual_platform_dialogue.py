"""Versioned visual dialogue that seals an owner-understood platform specification."""

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

from .platform_page_preview import PageKind, render_page_mockup


class VisualDialogueError(RuntimeError):
    pass


_ID = re.compile(r"\A[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}\Z")
_DIGEST = re.compile(r"\Asha256:[0-9a-f]{64}\Z")
_CONFIRMATIONS = frozenset(
    {"purpose", "audience", "screen_flow", "data_permissions", "cost_and_payment"}
)


class PlatformBrief(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    purpose: str = Field(min_length=1, max_length=2000)
    audience: list[str] = Field(min_length=1, max_length=20)
    required_capabilities: list[str] = Field(min_length=1, max_length=50)
    constraints: list[str] = Field(default_factory=list, max_length=50)


class ScreenSpec(BaseModel):
    screen_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")
    title: str = Field(min_length=1, max_length=100)
    purpose: str = Field(min_length=1, max_length=500)
    components: list[str] = Field(min_length=1, max_length=20)


class RevisionSubmission(BaseModel):
    based_on_revision_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    change_summary: str = Field(min_length=1, max_length=2000)
    screens: list[ScreenSpec] = Field(min_length=1, max_length=12)


class RevisionFeedback(BaseModel):
    revision_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    instruction: str = Field(min_length=1, max_length=2000)


class UnderstandingConfirmation(BaseModel):
    revision_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    confirmed_items: set[str]


def _digest(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return "sha256:" + sha256(encoded).hexdigest()


class VisualPlatformDialogueStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def create(
        self, *, tenant_id: str, owner_principal_id: str, brief: PlatformBrief,
    ) -> dict[str, object]:
        dialogue_id = str(uuid4())
        brief_document = brief.model_dump(mode="json")
        document: dict[str, object] = {
            "schema_version": "apf.visual-platform-dialogue/1.0",
            "dialogue_id": dialogue_id,
            "tenant_id": str(UUID(tenant_id)),
            "owner_principal_id": str(UUID(owner_principal_id)),
            "state": "AWAITING_ARKAON_REVISION",
            "brief": brief_document,
            "brief_digest": _digest(brief_document),
            "revisions": [],
            "feedback": [],
            "confirmations": [],
            "automatic_implementation": False,
            "automatic_deployment": False,
        }
        document["dialogue_digest"] = _digest(document)
        _exclusive_json(self._path(dialogue_id), document)
        return _public(document)

    def list_for_owner(self, *, tenant_id: str, owner_principal_id: str) -> list[dict[str, object]]:
        result = []
        root = self.root / "state" / "visual-platform-dialogues"
        for path in sorted(root.glob("*.json")) if root.is_dir() else ():
            try:
                document = _load(path)
                _validate_document(document)
            except VisualDialogueError:
                continue
            if (
                document["tenant_id"] == tenant_id
                and document["owner_principal_id"] == owner_principal_id
            ):
                result.append(_public(document))
        return result

    def get(self, dialogue_id: str, *, tenant_id: str) -> dict[str, object]:
        document = self._bound(dialogue_id, tenant_id)
        return _public(document, detail=True)

    def submit_revision(
        self, dialogue_id: str, *, tenant_id: str, submission: RevisionSubmission,
    ) -> dict[str, object]:
        document = self._bound(dialogue_id, tenant_id)
        if document["state"] not in {"AWAITING_ARKAON_REVISION", "REVISION_REQUESTED"}:
            raise VisualDialogueError("VISUAL_REVISION_NOT_EXPECTED")
        revisions = list(document["revisions"])
        latest = revisions[-1]["revision_digest"] if revisions else None
        if submission.based_on_revision_digest != latest:
            raise VisualDialogueError("VISUAL_REVISION_STALE_BASE")
        number = len(revisions) + 1
        screens = [item.model_dump(mode="json") for item in submission.screens]
        screen_ids = [item["screen_id"] for item in screens]
        if len(screen_ids) != len(set(screen_ids)):
            raise VisualDialogueError("VISUAL_SCREEN_ID_DUPLICATE")
        unsigned = {
            "revision_number": number,
            "based_on_revision_digest": latest,
            "change_summary": submission.change_summary,
            "screens": screens,
            "spec_digest": _digest(screens),
        }
        svg = _render_svg(document["brief"], screens, number)
        unsigned["image_digest"] = "sha256:" + sha256(svg.encode()).hexdigest()
        unsigned["revision_digest"] = _digest(unsigned)
        image_path = self._image_path(dialogue_id, number)
        _exclusive_bytes(image_path, svg.encode())
        revisions.append(unsigned)
        document.update(
            state="OWNER_REVIEW_REQUIRED", revisions=revisions, confirmations=[]
        )
        try:
            self._rewrite(document)
        except BaseException:
            image_path.unlink(missing_ok=True)
            raise
        return unsigned

    def add_feedback(
        self, dialogue_id: str, *, tenant_id: str, owner_principal_id: str,
        feedback: RevisionFeedback,
    ) -> dict[str, object]:
        document = self._owner_bound(dialogue_id, tenant_id, owner_principal_id)
        latest = _latest(document)
        if document["state"] != "OWNER_REVIEW_REQUIRED" or feedback.revision_digest != latest["revision_digest"]:
            raise VisualDialogueError("VISUAL_FEEDBACK_STALE_REVISION")
        entry = {
            "revision_digest": feedback.revision_digest,
            "instruction": feedback.instruction,
            "owner_principal_id": owner_principal_id,
            "submitted_at": datetime.now(UTC).isoformat(),
        }
        entry["feedback_digest"] = _digest(entry)
        document["feedback"] = [*document["feedback"], entry]
        document.update(state="REVISION_REQUESTED", confirmations=[])
        self._rewrite(document)
        return entry

    def confirm(
        self, dialogue_id: str, *, tenant_id: str, owner_principal_id: str,
        confirmation: UnderstandingConfirmation,
    ) -> dict[str, object]:
        document = self._owner_bound(dialogue_id, tenant_id, owner_principal_id)
        latest = _latest(document)
        if (
            document["state"] != "OWNER_REVIEW_REQUIRED"
            or confirmation.revision_digest != latest["revision_digest"]
            or confirmation.confirmed_items != _CONFIRMATIONS
        ):
            raise VisualDialogueError("VISUAL_UNDERSTANDING_INCOMPLETE")
        entry = {
            "revision_digest": confirmation.revision_digest,
            "confirmed_items": sorted(confirmation.confirmed_items),
            "owner_principal_id": owner_principal_id,
            "confirmed_at": datetime.now(UTC).isoformat(),
        }
        entry["confirmation_digest"] = _digest(entry)
        document.update(state="UNDERSTANDING_CONFIRMED", confirmations=[entry])
        self._rewrite(document)
        return entry

    def seal(self, dialogue_id: str, *, tenant_id: str, owner_principal_id: str) -> dict[str, object]:
        document = self._owner_bound(dialogue_id, tenant_id, owner_principal_id)
        if document["state"] != "UNDERSTANDING_CONFIRMED" or len(document["confirmations"]) != 1:
            raise VisualDialogueError("VISUAL_SPEC_NOT_CONFIRMABLE")
        latest = _latest(document)
        manifest = {
            "schema_version": "apf.visual-platform-spec/1.0",
            "dialogue_id": dialogue_id,
            "brief_digest": document["brief_digest"],
            "revision_digest": latest["revision_digest"],
            "spec_digest": latest["spec_digest"],
            "image_digest": latest["image_digest"],
            "confirmation_digest": document["confirmations"][0]["confirmation_digest"],
            "sealed_by": owner_principal_id,
            "sealed_at": datetime.now(UTC).isoformat(),
            "implementation_allowed": False,
            "deployment_allowed": False,
        }
        manifest["manifest_digest"] = _digest(manifest)
        manifest_path = self._manifest_path(dialogue_id)
        _exclusive_json(manifest_path, manifest)
        document.update(state="SPEC_SEALED", sealed_manifest_digest=manifest["manifest_digest"])
        try:
            self._rewrite(document)
        except BaseException:
            manifest_path.unlink(missing_ok=True)
            raise
        return manifest

    def page_preview(
        self, dialogue_id: str, revision_number: int, kind: PageKind, *,
        tenant_id: str, owner_principal_id: str,
    ) -> str:
        document = self._owner_bound(dialogue_id, tenant_id, owner_principal_id)
        revisions = document["revisions"]
        if not 1 <= revision_number <= len(revisions):
            raise VisualDialogueError("VISUAL_IMAGE_NOT_FOUND")
        revision = revisions[revision_number - 1]
        return render_page_mockup(document["brief"], revision["screens"], kind)

    def image(self, dialogue_id: str, revision_number: int, *, tenant_id: str) -> bytes:
        document = self._bound(dialogue_id, tenant_id)
        revisions = document["revisions"]
        if revision_number < 1 or revision_number > len(revisions):
            raise VisualDialogueError("VISUAL_IMAGE_NOT_FOUND")
        data = self._image_path(dialogue_id, revision_number).read_bytes()
        if "sha256:" + sha256(data).hexdigest() != revisions[revision_number - 1]["image_digest"]:
            raise VisualDialogueError("VISUAL_IMAGE_TAMPERED")
        return data

    def _bound(self, dialogue_id: str, tenant_id: str) -> dict[str, object]:
        if _ID.fullmatch(dialogue_id) is None:
            raise VisualDialogueError("VISUAL_DIALOGUE_ID_INVALID")
        document = _load(self._path(dialogue_id))
        _validate_document(document)
        if document["tenant_id"] != tenant_id:
            raise VisualDialogueError("VISUAL_DIALOGUE_NOT_FOUND")
        return document

    def _owner_bound(self, dialogue_id: str, tenant_id: str, owner: str) -> dict[str, object]:
        document = self._bound(dialogue_id, tenant_id)
        if document["owner_principal_id"] != owner:
            raise VisualDialogueError("VISUAL_DIALOGUE_OWNER_MISMATCH")
        return document

    def _rewrite(self, document: dict[str, object]) -> None:
        path = self._path(str(document["dialogue_id"]))
        expected = document.get("dialogue_digest")
        lock = path.with_suffix(path.suffix + ".lock")
        try:
            descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise VisualDialogueError("VISUAL_DIALOGUE_BUSY") from exc
        try:
            current = _load(path)
            if current.get("dialogue_digest") != expected:
                raise VisualDialogueError("VISUAL_DIALOGUE_CONCURRENT_UPDATE")
            document.pop("dialogue_digest", None)
            document["dialogue_digest"] = _digest(document)
            _atomic_json(path, document)
        finally:
            os.close(descriptor)
            lock.unlink(missing_ok=True)

    def _path(self, dialogue_id: str) -> Path:
        return self.root / "state" / "visual-platform-dialogues" / f"{dialogue_id}.json"

    def _image_path(self, dialogue_id: str, number: int) -> Path:
        return self.root / "state" / "visual-platform-images" / dialogue_id / f"v{number}.svg"

    def _manifest_path(self, dialogue_id: str) -> Path:
        return self.root / "state" / "visual-platform-specs" / f"{dialogue_id}.json"


def _render_svg(brief: object, screens: list[dict[str, object]], number: int) -> str:
    if not isinstance(brief, dict):
        raise VisualDialogueError("VISUAL_BRIEF_INVALID")
    width, card_width, gap = 1200, 330, 45
    rows = (len(screens) + 2) // 3
    height = 150 + rows * 520
    chunks = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#07111f"/>',
        f'<text x="40" y="55" fill="#edf4ff" font-size="30" font-family="sans-serif">{html.escape(str(brief.get("name")))} · 화면안 v{number}</text>',
        f'<text x="40" y="90" fill="#adbed2" font-size="17" font-family="sans-serif">{html.escape(str(brief.get("purpose")))}</text>',
    ]
    for index, screen in enumerate(screens):
        col, row = index % 3, index // 3
        x, y = 40 + col * (card_width + gap), 125 + row * 520
        chunks.extend([
            f'<rect x="{x}" y="{y}" width="{card_width}" height="470" rx="24" fill="#101d2e" stroke="#53adff" stroke-width="2"/>',
            f'<text x="{x+22}" y="{y+45}" fill="#edf4ff" font-size="22" font-family="sans-serif">{html.escape(str(screen["title"]))}</text>',
            f'<text x="{x+22}" y="{y+75}" fill="#adbed2" font-size="14" font-family="sans-serif">{html.escape(str(screen["purpose"]))}</text>',
        ])
        for offset, component in enumerate(screen["components"]):
            cy = y + 105 + offset * 48
            if cy > y + 440:
                break
            chunks.extend([
                f'<rect x="{x+20}" y="{cy}" width="{card_width-40}" height="36" rx="8" fill="#172b42"/>',
                f'<text x="{x+32}" y="{cy+24}" fill="#dcecff" font-size="14" font-family="sans-serif">{html.escape(str(component))}</text>',
            ])
    chunks.append("</svg>")
    return "".join(chunks)


def _latest(document: dict[str, object]) -> dict[str, object]:
    revisions = document.get("revisions")
    if not isinstance(revisions, list) or not revisions:
        raise VisualDialogueError("VISUAL_REVISION_REQUIRED")
    return revisions[-1]


def _validate_document(document: dict[str, object]) -> None:
    supplied = document.get("dialogue_digest")
    unsigned = {key: value for key, value in document.items() if key != "dialogue_digest"}
    if (
        document.get("schema_version") != "apf.visual-platform-dialogue/1.0"
        or not isinstance(supplied, str)
        or not _DIGEST.fullmatch(supplied)
        or supplied != _digest(unsigned)
        or document.get("automatic_implementation") is not False
        or document.get("automatic_deployment") is not False
    ):
        raise VisualDialogueError("VISUAL_DIALOGUE_TAMPERED")


def _public(document: dict[str, object], *, detail: bool = False) -> dict[str, object]:
    brief = document["brief"]
    assert isinstance(brief, dict)
    value = {
        "dialogue_id": document["dialogue_id"], "name": brief["name"],
        "state": document["state"], "revision_count": len(document["revisions"]),
        "automatic_implementation": False, "automatic_deployment": False,
    }
    if detail:
        value.update(
            brief=brief, brief_digest=document["brief_digest"], revisions=document["revisions"],
            feedback=document["feedback"], confirmations=document["confirmations"],
            sealed_manifest_digest=document.get("sealed_manifest_digest"),
        )
    return value


def _load(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VisualDialogueError("VISUAL_DIALOGUE_NOT_FOUND") from exc
    if not isinstance(value, dict):
        raise VisualDialogueError("VISUAL_DIALOGUE_INVALID")
    return value


def _exclusive_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise VisualDialogueError("VISUAL_ARTIFACT_CONFLICT") from exc
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _exclusive_json(path: Path, document: dict[str, object]) -> None:
    _exclusive_bytes(
        path, (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    )


def _atomic_json(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{uuid4().hex}.tmp")
    try:
        _exclusive_json(temporary, document)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
