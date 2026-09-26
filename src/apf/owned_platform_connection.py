"""Read-only owned-platform repository connection for authorized structural analysis."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path

from .owned_platform_metadata import MetadataPilotError, validate_metadata_pilot

_FORBIDDEN_NAMES = frozenset({".env", ".pem", "credentials", "secrets", "id_rsa", "id_ed25519"})
_SAFE_EXTENSIONS = frozenset(
    {
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".go",
        ".rs",
        ".java",
        ".kt",
        ".sql",
        ".md",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".html",
        ".css",
        ".scss",
    }
)
_MAX_FILES = 5000
_MAX_DEPTH = 4


class OwnedPlatformConnectionRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ConnectionStatus(str, Enum):
    SKIP = "SKIP"
    CONNECTED_READONLY_STRUCTURAL = "CONNECTED_READONLY_STRUCTURAL"
    FAIL = "FAIL"


@dataclass(frozen=True)
class OwnedPlatformConnectionPolicy:
    read_only: bool = True
    copy_source_material: bool = False
    actual_code_analysis: bool = False
    max_files_scanned: int = _MAX_FILES
    max_depth: int = _MAX_DEPTH

    @classmethod
    def load(cls, path: Path) -> OwnedPlatformConnectionPolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.arkaon-owned-platform-connection/v1":
            raise OwnedPlatformConnectionRejected("POLICY_SCHEMA", "unsupported owned platform connection schema")
        if (
            not document.get("read_only", True)
            or document.get("copy_source_material")
            or document.get("actual_code_analysis")
            or document.get("mutate_intent_dna")
            or document.get("promote_owned_asset")
        ):
            raise OwnedPlatformConnectionRejected("POLICY_FORBIDDEN", "owned platform connection must remain read-only structural")
        return cls(
            read_only=bool(document.get("read_only", True)),
            copy_source_material=bool(document.get("copy_source_material")),
            actual_code_analysis=bool(document.get("actual_code_analysis")),
            max_files_scanned=int(document.get("max_files_scanned", _MAX_FILES)),
            max_depth=int(document.get("max_depth", _MAX_DEPTH)),
        )


@dataclass(frozen=True)
class StructuralDigest:
    platform_id: str
    repository_path: str
    top_level_entries: tuple[str, ...]
    extension_counts: tuple[tuple[str, int], ...]
    scanned_files: int
    git_head: str | None
    digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "platform_id": self.platform_id,
            "repository_path": self.repository_path,
            "top_level_entries": list(self.top_level_entries),
            "extension_counts": [{"extension": ext, "count": count} for ext, count in self.extension_counts],
            "scanned_files": self.scanned_files,
            "git_head": self.git_head,
            "digest": self.digest,
            "actual_code_analysis": False,
            "copy_prohibited": True,
        }


@dataclass(frozen=True)
class OwnedPlatformConnectionResult:
    platform_id: str
    pilot_id: str
    status: ConnectionStatus
    message: str
    structural_digest: StructuralDigest | None = None

    def to_document(self) -> dict[str, object]:
        return {
            "platform_id": self.platform_id,
            "pilot_id": self.pilot_id,
            "status": self.status.value,
            "message": self.message,
            "structural_digest": None if self.structural_digest is None else self.structural_digest.to_document(),
        }


def resolve_repository_path(platform_id: str) -> Path | None:
    env_key = f"OWNED_PLATFORM_{platform_id}_REPO_PATH"
    raw = os.getenv(env_key)
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_dir():
        raise OwnedPlatformConnectionRejected("INVALID_REPO_PATH", f"{env_key} is not a directory")
    return path.resolve()


def _git_head(repository: Path) -> str | None:
    head = repository / ".git" / "HEAD"
    if not head.is_file():
        return None
    value = head.read_text(encoding="utf-8").strip()
    if value.startswith("ref: "):
        ref = repository / ".git" / value.removeprefix("ref: ")
        if ref.is_file():
            return ref.read_text(encoding="utf-8").strip()[:40]
    if re.fullmatch(r"[0-9a-f]{40}", value):
        return value
    return None


def _forbidden_name(name: str) -> bool:
    lowered = name.casefold()
    return lowered in _FORBIDDEN_NAMES or any(token in lowered for token in ("secret", "credential", "password"))


def build_structural_digest(
    *,
    platform_id: str,
    repository: Path,
    policy: OwnedPlatformConnectionPolicy,
) -> StructuralDigest:
    if not repository.is_dir():
        raise OwnedPlatformConnectionRejected("INVALID_REPO_PATH", "repository path missing")
    top_level = tuple(sorted(item.name for item in repository.iterdir() if not _forbidden_name(item.name)))
    counts: dict[str, int] = {}
    scanned = 0
    for root, dirs, files in os.walk(repository):
        depth = len(Path(root).relative_to(repository).parts)
        dirs[:] = sorted(
            directory
            for directory in dirs
            if not directory.startswith(".") and not _forbidden_name(directory)
        )[: max(0, policy.max_depth - depth)]
        if depth >= policy.max_depth:
            dirs.clear()
        for filename in files:
            if scanned >= policy.max_files_scanned:
                break
            if filename.startswith(".") or _forbidden_name(filename):
                continue
            suffix = Path(filename).suffix.casefold()
            if suffix and suffix not in _SAFE_EXTENSIONS:
                continue
            counts[suffix or "(none)"] = counts.get(suffix or "(none)", 0) + 1
            scanned += 1
        if scanned >= policy.max_files_scanned:
            break
    extension_counts = tuple(sorted(counts.items(), key=lambda item: (-item[1], item[0])))
    payload = {
        "extension_counts": extension_counts,
        "platform_id": platform_id,
        "repository_path": repository.as_posix(),
        "scanned_files": scanned,
        "top_level_entries": top_level,
    }
    digest = "sha256:" + sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return StructuralDigest(
        platform_id=platform_id,
        repository_path=repository.as_posix(),
        top_level_entries=top_level,
        extension_counts=extension_counts,
        scanned_files=scanned,
        git_head=_git_head(repository),
        digest=digest,
    )


def connect_owned_platform(
    *,
    foundry_root: Path,
    platform_id: str,
    policy: OwnedPlatformConnectionPolicy | None = None,
) -> OwnedPlatformConnectionResult:
    pilot_path = foundry_root / "knowledge" / "pilots" / {
        "NOGADA_NEWS": "nogada-news-041.json",
        "SIDEJOB_MARKET": "sidejob-market-041.json",
    }.get(platform_id, "")
    if not pilot_path.is_file():
        raise OwnedPlatformConnectionRejected("UNKNOWN_PLATFORM", f"unsupported platform {platform_id}")
    try:
        pilot = validate_metadata_pilot(pilot_path.read_bytes())
    except MetadataPilotError as error:
        raise OwnedPlatformConnectionRejected("PILOT_INVALID", str(error)) from error
    if pilot.platform_id != platform_id:
        raise OwnedPlatformConnectionRejected("PILOT_MISMATCH", "platform id mismatch")
    config = foundry_root / "config" / "arkaon-owned-platform-connection.json"
    active_policy = policy or OwnedPlatformConnectionPolicy.load(config)
    repository = resolve_repository_path(platform_id)
    if repository is None:
        return OwnedPlatformConnectionResult(
            platform_id=platform_id,
            pilot_id=pilot_path.stem,
            status=ConnectionStatus.SKIP,
            message=f"OWNED_PLATFORM_{platform_id}_REPO_PATH not configured",
        )
    try:
        digest = build_structural_digest(
            platform_id=platform_id, repository=repository, policy=active_policy
        )
    except OwnedPlatformConnectionRejected as error:
        return OwnedPlatformConnectionResult(
            platform_id=platform_id,
            pilot_id=pilot_path.stem,
            status=ConnectionStatus.FAIL,
            message=str(error),
        )
    return OwnedPlatformConnectionResult(
        platform_id=platform_id,
        pilot_id=pilot_path.stem,
        status=ConnectionStatus.CONNECTED_READONLY_STRUCTURAL,
        message="read-only structural digest captured; no source material copied",
        structural_digest=digest,
    )


def connect_all_owned_platforms(
    *,
    foundry_root: Path,
    policy: OwnedPlatformConnectionPolicy | None = None,
) -> tuple[OwnedPlatformConnectionResult, ...]:
    return tuple(
        connect_owned_platform(foundry_root=foundry_root, platform_id=platform_id, policy=policy)
        for platform_id in ("NOGADA_NEWS", "SIDEJOB_MARKET")
    )
