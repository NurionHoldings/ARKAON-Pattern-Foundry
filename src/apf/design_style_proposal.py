"""Owner-bound clean-room style proposals from explicitly recorded public observations."""

from __future__ import annotations

import json
import os
import re
from hashlib import sha256
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .design_reference_urls import SubjectType

_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class StyleProposalError(ValueError):
    pass


class PublicObservation(BaseModel):
    reference_id: UUID
    background: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    text: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    accent: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    layout: Literal["editorial", "split", "cards"] = "split"
    density: Literal["compact", "balanced", "airy"] = "balanced"
    note: str = Field(default="", max_length=300)


class StyleProposalRequest(BaseModel):
    based_on_set_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    observations: list[PublicObservation] = Field(min_length=1, max_length=12)


class StyleDecision(BaseModel):
    proposal_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    decision: Literal["APPLY", "REJECT"]


def _digest(value: object) -> str:
    return "sha256:" + sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                         separators=(",", ":")).encode()).hexdigest()


def _rgb(color: str) -> tuple[float, float, float]:
    values = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple(v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in values)


def _contrast(a: str, b: str) -> float:
    def lum(color: str) -> float:
        return sum(x * y for x, y in zip(_rgb(color), (.2126, .7152, .0722), strict=True))
    left, right = sorted((lum(a), lum(b)))
    return (right + .05) / (left + .05)


def _tokens(observations: list[PublicObservation]) -> dict[str, str]:
    # The submitted colors are measurements, not externally supplied CSS or selectors.
    # The median per channel avoids making the proposal an exact reproduction of one page.
    def median_color(field: str) -> str:
        result = []
        for i in (1, 3, 5):
            values = sorted(int(getattr(item, field)[i:i + 2], 16) for item in observations)
            result.append(values[len(values) // 2])
        return "#" + "".join(f"{x:02x}" for x in result)
    background = median_color("background")
    ink = median_color("text")
    accent = median_color("accent")
    if _contrast(background, ink) < 4.5:
        ink = "#142337" if _contrast(background, "#142337") >= 4.5 else "#ffffff"
    if _contrast(background, accent) < 3:
        accent = "#087f70" if _contrast(background, "#087f70") >= 3 else ink
    layouts = [item.layout for item in observations]
    densities = [item.density for item in observations]
    layout = max(("editorial", "split", "cards"), key=lambda x: (layouts.count(x), -layouts.index(x) if x in layouts else -100))
    density = max(("compact", "balanced", "airy"), key=lambda x: (densities.count(x), -densities.index(x) if x in densities else -100))
    return {"background": background, "ink": ink, "accent": accent,
            "layout": layout, "density": density}


def render_style_css(tokens: dict[str, str]) -> str:
    """Generate only owned CSS from validated tokens; never insert source CSS."""
    if any(not _COLOR.fullmatch(tokens[key]) for key in ("background", "ink", "accent")):
        raise StyleProposalError("STYLE_TOKENS_INVALID")
    if tokens["layout"] not in {"editorial", "split", "cards"} or tokens["density"] not in {"compact", "balanced", "airy"}:
        raise StyleProposalError("STYLE_TOKENS_INVALID")
    gap = {"compact": "12px", "balanced": "20px", "airy": "32px"}[tokens["density"]]
    layout = {"editorial": "1fr", "split": "1.15fr .85fr", "cards": "1fr 1fr"}[tokens["layout"]]
    return (
        ":root{--paper:" + tokens["background"] + ";--ink:" + tokens["ink"]
        + ";--mint:" + tokens["accent"] + ";--line:" + tokens["accent"]
        + ";--apf-gap:" + gap + "}"
        + "body{background:var(--paper);color:var(--ink)}"
        + ".story-grid,.features{gap:var(--apf-gap)}"
        + ".landing-hero,.preview-hero{grid-template-columns:" + layout + "}"
        + ".story-panel,.feature{border-color:var(--mint)}"
        + ".eyebrow,.feature .number{color:var(--mint)}"
        + "@media(max-width:760px){.landing-hero,.preview-hero,.story-grid,.features{grid-template-columns:1fr}}"
    )


def inject_preview_style(page: str, css: str) -> str:
    if "</head>" not in page:
        raise StyleProposalError("STYLE_PREVIEW_INVALID")
    return page.replace("</head>", "<style>" + css + "</style></head>", 1)


class StyleProposalStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def propose(
        self, subject_type: SubjectType, subject_id: str, *, tenant_id: str,
        owner_principal_id: str, references: dict[str, object], request: StyleProposalRequest,
    ) -> dict[str, object]:
        self._identity(subject_id, tenant_id, owner_principal_id)
        if request.based_on_set_digest != references["set_digest"]:
            raise StyleProposalError("STYLE_REFERENCES_STALE")
        registered = {item["reference_id"] for item in references["references"]}
        observed = [str(item.reference_id) for item in request.observations]
        if len(set(observed)) != len(observed) or not set(observed) <= registered:
            raise StyleProposalError("STYLE_REFERENCE_UNKNOWN")
        tokens = _tokens(request.observations)
        proposal = {
            "schema_version": "apf.style-proposal/1.0",
            "subject_type": subject_type, "subject_id": subject_id,
            "tenant_id": tenant_id, "owner_principal_id": owner_principal_id,
            "reference_set_digest": request.based_on_set_digest,
            "observations": [item.model_dump(mode="json") for item in request.observations],
            "tokens": tokens, "status": "PREVIEW_REQUIRED",
        }
        proposal["proposal_digest"] = _digest(proposal)
        self._write(self._path(subject_type, subject_id), proposal)
        return self._public(proposal)

    def get(
        self, subject_type: SubjectType, subject_id: str, *, tenant_id: str,
        owner_principal_id: str, reference_set_digest: str,
    ) -> dict[str, object]:
        return self._public(self._read(subject_type, subject_id, tenant_id,
                                       owner_principal_id, reference_set_digest))

    def decide(
        self, subject_type: SubjectType, subject_id: str, *, tenant_id: str,
        owner_principal_id: str, reference_set_digest: str, decision: StyleDecision,
    ) -> dict[str, object]:
        self._identity(subject_id, tenant_id, owner_principal_id)
        path = self._path(subject_type, subject_id)
        lock = path.with_suffix(".lock")
        try:
            fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise StyleProposalError("STYLE_BUSY") from exc
        try:
            doc = self._read(subject_type, subject_id, tenant_id, owner_principal_id,
                             reference_set_digest)
            if doc["status"] != "PREVIEW_REQUIRED" or doc["proposal_digest"] != decision.proposal_digest:
                raise StyleProposalError("STYLE_DECISION_STALE")
            doc["status"] = "APPLIED" if decision.decision == "APPLY" else "REJECTED"
            doc["proposal_digest"] = _digest({key: value for key, value in doc.items() if key != "proposal_digest"})
            self._write(path, doc)
            return self._public(doc)
        finally:
            os.close(fd)
            lock.unlink(missing_ok=True)

    def _read(self, subject_type: SubjectType, subject_id: str, tenant_id: str,
              owner_principal_id: str, reference_set_digest: str) -> dict[str, object]:
        self._identity(subject_id, tenant_id, owner_principal_id)
        try:
            doc = json.loads(self._path(subject_type, subject_id).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StyleProposalError("STYLE_NOT_FOUND") from exc
        if not isinstance(doc, dict) or not _DIGEST.fullmatch(str(doc.get("proposal_digest", ""))):
            raise StyleProposalError("STYLE_TAMPERED")
        unsigned = {key: value for key, value in doc.items() if key != "proposal_digest"}
        if (doc.get("schema_version") != "apf.style-proposal/1.0"
                or doc["proposal_digest"] != _digest(unsigned)
                or doc.get("tokens") != _tokens([PublicObservation.model_validate(item) for item in doc["observations"]])
                or doc.get("status") not in {"PREVIEW_REQUIRED", "APPLIED", "REJECTED"}):
            raise StyleProposalError("STYLE_TAMPERED")
        if (doc.get("subject_type"), doc.get("subject_id"), doc.get("tenant_id"),
            doc.get("owner_principal_id")) != (subject_type, subject_id, tenant_id, owner_principal_id):
            raise StyleProposalError("STYLE_NOT_FOUND")
        if doc["reference_set_digest"] != reference_set_digest:
            raise StyleProposalError("STYLE_REFERENCES_STALE")
        return doc

    @staticmethod
    def _public(doc: dict[str, object]) -> dict[str, object]:
        return {key: doc[key] for key in ("subject_type", "subject_id", "reference_set_digest",
                                         "observations", "tokens", "status", "proposal_digest")}

    def _path(self, subject_type: SubjectType, subject_id: str) -> Path:
        return self.root / "state" / "style-proposals" / subject_type / f"{subject_id}.json"

    @staticmethod
    def _identity(subject_id: str, tenant_id: str, owner_principal_id: str) -> None:
        UUID(subject_id)
        UUID(tenant_id)
        UUID(owner_principal_id)

    @staticmethod
    def _write(path: Path, doc: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{uuid4().hex}.tmp")
        try:
            with open(tmp, "x", encoding="utf-8") as stream:
                json.dump(doc, stream, ensure_ascii=False, sort_keys=True)
                stream.write("\n")
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
