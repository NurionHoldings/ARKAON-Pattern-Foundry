"""Observe public platform surfaces for improvement signals without copying competitor assets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from .experience_audit_bridge import (
    build_operational_manifest,
    collect_openapi_paths,
    collect_policy_route_refs,
    collect_visible_texts,
)
from .static_js_normalizer import NormalizedJsStructure, StaticJsRejected, normalize_minified_js

_JS_SUFFIXES = frozenset({".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"})
_FORBIDDEN = frozenset(
    {"member", "order", "location", "payment", "settlement", "identity", "pii", "credential", "secret"}
)


class PublicSurfaceRejected(ValueError):
    pass


@dataclass(frozen=True)
class PublicSurfaceObservationPolicy:
    copy_prohibited: bool = True
    verbatim_storage_allowed: bool = False
    dynamic_execution_allowed: bool = False
    network_access_allowed: bool = False
    max_js_file_bytes: int = 524_288
    max_js_files_per_platform: int = 32

    @classmethod
    def load(cls, path: Path) -> PublicSurfaceObservationPolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.arkaon-public-surface-observation/v1":
            raise PublicSurfaceRejected("unsupported public surface observation schema")
        if (
            not document.get("copy_prohibited", True)
            or document.get("verbatim_storage_allowed")
            or document.get("dynamic_execution_allowed")
            or document.get("network_access_allowed")
            or document.get("competitor_copy_allowed")
        ):
            raise PublicSurfaceRejected("public surface observation must remain non-copy structural only")
        return cls(
            copy_prohibited=bool(document.get("copy_prohibited", True)),
            verbatim_storage_allowed=bool(document.get("verbatim_storage_allowed")),
            dynamic_execution_allowed=bool(document.get("dynamic_execution_allowed")),
            network_access_allowed=bool(document.get("network_access_allowed")),
            max_js_file_bytes=int(document.get("max_js_file_bytes", 524_288)),
            max_js_files_per_platform=int(document.get("max_js_files_per_platform", 32)),
        )


@dataclass(frozen=True)
class SurfaceObservationReport:
    platform_id: str
    observed_at: datetime
    rights_posture: str
    openapi_paths: tuple[str, ...]
    policy_route_refs: tuple[str, ...]
    visible_text_samples: tuple[str, ...]
    js_structures: tuple[NormalizedJsStructure, ...]
    observation_digest: str
    copy_prohibited: bool = True
    verbatim_storage: bool = False

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.public-surface-observation/v1",
            "platform_id": self.platform_id,
            "observed_at": self.observed_at.isoformat(),
            "rights_posture": self.rights_posture,
            "openapi_paths": list(self.openapi_paths),
            "policy_route_refs": list(self.policy_route_refs),
            "visible_text_samples": list(self.visible_text_samples),
            "js_structures": [item.to_document() for item in self.js_structures],
            "observation_digest": self.observation_digest,
            "copy_prohibited": self.copy_prohibited,
            "verbatim_storage": self.verbatim_storage,
            "maximum_outcome": "STRUCTURAL_OBSERVATION",
        }


def _scan_forbidden(text: str) -> None:
    lowered = text.casefold()
    for token in _FORBIDDEN:
        if token in lowered:
            raise PublicSurfaceRejected("operational or identity data cannot enter public surface observation")


def collect_js_structures(
    platform_path: Path,
    *,
    policy: PublicSurfaceObservationPolicy,
) -> tuple[NormalizedJsStructure, ...]:
    structures: list[NormalizedJsStructure] = []
    for folder in ("frontend", "src", "public", "static"):
        root = platform_path / folder
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in _JS_SUFFIXES:
                continue
            if len(structures) >= policy.max_js_files_per_platform:
                break
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            relative = path.relative_to(platform_path).as_posix()
            try:
                structure = normalize_minified_js(
                    source_path=relative,
                    content=content,
                    max_bytes=policy.max_js_file_bytes,
                )
            except StaticJsRejected:
                continue
            if structure.dynamic_execution_detected and not policy.dynamic_execution_allowed:
                structures.append(structure)
                continue
            structures.append(structure)
    return tuple(structures)


def observe_public_surface(
    *,
    platform_id: str,
    platform_path: Path,
    foundry_root: Path,
    now: datetime,
) -> SurfaceObservationReport:
    policy = PublicSurfaceObservationPolicy.load(
        foundry_root / "config" / "arkaon-public-surface-observation.json"
    )
    if now.tzinfo is None:
        raise PublicSurfaceRejected("timezone-aware timestamp required")
    manifest = build_operational_manifest(platform_path)
    visible = collect_visible_texts(platform_path)
    for sample in visible:
        _scan_forbidden(sample)
    js_structures = collect_js_structures(platform_path, policy=policy)
    payload = {
        "platform_id": platform_id,
        "openapi_paths": sorted(collect_openapi_paths(platform_path)),
        "policy_route_refs": sorted(collect_policy_route_refs(platform_path)),
        "frontend_routes": sorted(manifest.frontend_routes),
        "visible_text_count": len(visible),
        "js_structure_digests": [item.structure_digest for item in js_structures],
    }
    observation_digest = sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return SurfaceObservationReport(
        platform_id=platform_id,
        observed_at=now,
        rights_posture="PUBLIC_OBSERVATION",
        openapi_paths=tuple(payload["openapi_paths"]),
        policy_route_refs=tuple(payload["policy_route_refs"]),
        visible_text_samples=visible,
        js_structures=js_structures,
        observation_digest=observation_digest,
        copy_prohibited=policy.copy_prohibited,
        verbatim_storage=False,
    )
