"""Resolve ambiguous analysis targets via last user site intent and non-duplicate cross-platform routing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from .capability_gap import collect_external_inventories


class AnalysisTargetResolutionRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AnalysisTargetResolutionPolicy:
    enabled: bool = True
    emit_research_packet: bool = True
    scan_operator_inbox: bool = True
    max_targets_per_run: int = 3
    automatic_implement_allowed: bool = False
    production_change_allowed: bool = False

    @classmethod
    def load(cls, path: Path) -> AnalysisTargetResolutionPolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.analysis-target-resolution/v1":
            raise AnalysisTargetResolutionRejected("POLICY_SCHEMA", "unsupported analysis target resolution schema")
        if document.get("automatic_implement_allowed") or document.get("production_change_allowed"):
            raise AnalysisTargetResolutionRejected(
                "POLICY_FORBIDDEN", "analysis target resolution must remain request-only"
            )
        return cls(
            enabled=bool(document.get("enabled", True)),
            emit_research_packet=bool(document.get("emit_research_packet", True)),
            scan_operator_inbox=bool(document.get("scan_operator_inbox", True)),
            max_targets_per_run=max(1, int(document.get("max_targets_per_run", 3))),
            automatic_implement_allowed=bool(document.get("automatic_implement_allowed")),
            production_change_allowed=bool(document.get("production_change_allowed")),
        )


@dataclass(frozen=True)
class LastUserSiteRequest:
    platform_id: str
    sought_capability_tokens: tuple[str, ...]
    recorded_at: datetime
    evidence_ref: str

    def to_document(self) -> dict[str, object]:
        return {
            "platform_id": self.platform_id,
            "sought_capability_tokens": list(self.sought_capability_tokens),
            "recorded_at": self.recorded_at.isoformat(),
            "evidence_ref": self.evidence_ref,
        }

    @classmethod
    def from_document(cls, document: dict[str, object]) -> LastUserSiteRequest:
        recorded_at = datetime.fromisoformat(str(document["recorded_at"]))
        tokens = document.get("sought_capability_tokens") or ()
        return cls(
            platform_id=str(document["platform_id"]),
            sought_capability_tokens=tuple(str(item) for item in tokens),
            recorded_at=recorded_at,
            evidence_ref=str(document.get("evidence_ref", "")),
        )


@dataclass(frozen=True)
class CrossPlatformTarget:
    platform_id: str
    capability_tokens: tuple[str, ...]
    rationale: str

    def to_document(self) -> dict[str, object]:
        return {
            "platform_id": self.platform_id,
            "capability_tokens": list(self.capability_tokens),
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class AnalysisTargetResolutionReport:
    foundry_root: Path
    evaluated_at: datetime
    ambiguous: bool
    ambiguity_reason: str
    last_user_site: LastUserSiteRequest | None
    targets: tuple[CrossPlatformTarget, ...]
    report_digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.analysis-target-resolution-report/v1",
            "foundry_root": self.foundry_root.as_posix(),
            "evaluated_at": self.evaluated_at.isoformat(),
            "ambiguous": self.ambiguous,
            "ambiguity_reason": self.ambiguity_reason,
            "last_user_site": self.last_user_site.to_document() if self.last_user_site else None,
            "targets": [item.to_document() for item in self.targets],
            "report_digest": self.report_digest,
        }


def _landing_intent_path(foundry_root: Path, platform_id: str) -> Path | None:
    directory = foundry_root / "knowledge" / "landing-intents"
    if not directory.is_dir():
        return None
    for path in directory.glob("*.json"):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        platform = document.get("platform") or {}
        if platform.get("id") == platform_id:
            return path
    return None


def load_sought_capability_tokens(foundry_root: Path, platform_id: str) -> frozenset[str]:
    path = _landing_intent_path(foundry_root, platform_id)
    if path is None:
        return frozenset()
    document = json.loads(path.read_text(encoding="utf-8"))
    tokens: set[str] = set()
    focus = document.get("learning_focus") or {}
    for item in focus.get("priority_patterns") or ():
        if isinstance(item, str):
            tokens.add(f"landing-pattern:{item}")
    for item in focus.get("copy_angle_tags") or ():
        if isinstance(item, str):
            tokens.add(f"copy-angle:{item}")
    landing = document.get("landing_intent") or {}
    for item in landing.get("signal") or ():
        if isinstance(item, str):
            tokens.add(f"landing-signal:{item}")
    for item in document.get("evolution_domain_refs") or ():
        if isinstance(item, str):
            tokens.add(f"evolution-domain:{item}")
    return frozenset(tokens)


_WAVE1_PLATFORM_ORDER = ("MAEJINNAM", "DOSIRAK_STORE", "WITHER", "ZAKSIMSPACE")


def _platform_sort_key(platform_id: str) -> tuple[int, str]:
    try:
        return (_WAVE1_PLATFORM_ORDER.index(platform_id), platform_id)
    except ValueError:
        return (len(_WAVE1_PLATFORM_ORDER), platform_id)


def list_landing_intent_platform_ids(foundry_root: Path) -> tuple[str, ...]:
    directory = foundry_root / "knowledge" / "landing-intents"
    if not directory.is_dir():
        return ()
    platform_ids: list[str] = []
    for path in sorted(directory.glob("*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        platform_id = str((document.get("platform") or {}).get("id", ""))
        if platform_id:
            platform_ids.append(platform_id)
    return tuple(sorted(set(platform_ids)))


def _load_last_user_site_request(store_root: Path) -> LastUserSiteRequest | None:
    path = store_root / "last-user-site-request.json"
    if not path.is_file():
        return None
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != "apf.last-user-site-request/v1":
        return None
    return LastUserSiteRequest.from_document(document)


def _write_last_user_site_request(store_root: Path, request: LastUserSiteRequest) -> None:
    store_root.mkdir(parents=True, exist_ok=True)
    document = {
        "schema_version": "apf.last-user-site-request/v1",
        **request.to_document(),
    }
    (store_root / "last-user-site-request.json").write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _scan_operator_inbox_for_site_request(foundry_root: Path, now: datetime) -> LastUserSiteRequest | None:
    inbox = foundry_root / "inbox" / "operator-decision"
    if not inbox.is_dir():
        return None
    known_platforms = set(list_landing_intent_platform_ids(foundry_root))
    if not known_platforms:
        return None
    candidates: list[tuple[datetime, LastUserSiteRequest]] = []
    for path in sorted(inbox.glob("*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        platform_id = str(document.get("platform_id", ""))
        if platform_id not in known_platforms:
            continue
        created_raw = document.get("created_at")
        try:
            created_at = datetime.fromisoformat(str(created_raw)) if created_raw else now
        except ValueError:
            created_at = now
        tokens = load_sought_capability_tokens(foundry_root, platform_id)
        candidates.append(
            (
                created_at,
                LastUserSiteRequest(
                    platform_id=platform_id,
                    sought_capability_tokens=tuple(sorted(tokens)),
                    recorded_at=created_at,
                    evidence_ref=path.relative_to(foundry_root).as_posix(),
                ),
            )
        )
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def refresh_last_user_site_request(
    *,
    foundry_root: Path,
    store_root: Path,
    scan_operator_inbox: bool,
    now: datetime,
    dry_run: bool,
) -> LastUserSiteRequest | None:
    current = _load_last_user_site_request(store_root)
    scanned: LastUserSiteRequest | None = None
    if scan_operator_inbox:
        scanned = _scan_operator_inbox_for_site_request(foundry_root, now)
    chosen = current
    if scanned is not None and (current is None or scanned.recorded_at >= current.recorded_at):
        chosen = scanned
    if chosen is not None and not dry_run and chosen != current:
        _write_last_user_site_request(store_root, chosen)
    return chosen


def _load_analysis_ledger(store_root: Path) -> set[tuple[str, str]]:
    path = store_root / "analysis-ledger.jsonl"
    if not path.is_file():
        return set()
    entries: set[tuple[str, str]] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            document = json.loads(line)
        except json.JSONDecodeError:
            continue
        platform_id = str(document.get("platform_id", ""))
        token = str(document.get("capability_token", ""))
        if platform_id and token:
            entries.add((platform_id, token))
    return entries


def _append_analysis_ledger(
    store_root: Path,
    *,
    platform_id: str,
    capability_token: str,
    run_id: str,
    recorded_at: datetime,
) -> None:
    store_root.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        {
            "platform_id": platform_id,
            "capability_token": capability_token,
            "run_id": run_id,
            "recorded_at": recorded_at.isoformat(),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    with (store_root / "analysis-ledger.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def detect_ambiguity(
    *,
    enabled_registration_count: int,
    enabled_paths_missing: bool,
    last_request_not_in_registry: bool,
    all_platforms_blocked: bool,
) -> tuple[bool, str]:
    if enabled_registration_count == 0:
        return True, "NO_ENABLED_PLATFORMS"
    if last_request_not_in_registry:
        return True, "LAST_REQUEST_NOT_IN_REGISTRY"
    if enabled_paths_missing:
        return True, "ALL_ENABLED_PATHS_MISSING"
    if all_platforms_blocked:
        return True, "ALL_PLATFORMS_BLOCKED"
    return False, ""


def plan_cross_platform_targets(
    *,
    foundry_root: Path,
    last_request: LastUserSiteRequest,
    registered_platform_ids: frozenset[str],
    ledger: set[tuple[str, str]],
    max_targets: int,
) -> tuple[CrossPlatformTarget, ...]:
    sought = frozenset(last_request.sought_capability_tokens) or load_sought_capability_tokens(
        foundry_root, last_request.platform_id
    )
    if not sought:
        return ()
    externals = collect_external_inventories(foundry_root, exclude_platform_id=last_request.platform_id)
    candidate_platforms = sorted(
        [
            platform_id
            for platform_id in list_landing_intent_platform_ids(foundry_root)
            if platform_id != last_request.platform_id and platform_id not in registered_platform_ids
        ],
        key=_platform_sort_key,
    )
    targets: list[CrossPlatformTarget] = []
    for platform_id in candidate_platforms:
        inventory = externals.get(platform_id)
        platform_tokens = inventory.tokens if inventory is not None else frozenset()
        pending_tokens = tuple(
            sorted(
                token
                for token in sought
                if (platform_id, token) not in ledger and token not in platform_tokens
            )
        )
        if not pending_tokens:
            continue
        label = ", ".join(pending_tokens[:3])
        if len(pending_tokens) > 3:
            label += ", ..."
        targets.append(
            CrossPlatformTarget(
                platform_id=platform_id,
                capability_tokens=pending_tokens,
                rationale=(
                    f"{last_request.platform_id} 분석에서 찾던 기능({label})을 "
                    f"{platform_id}에서 아직 관측·기록되지 않았습니다. "
                    "중복 없이 structural cross-platform 학습을 계속합니다."
                ),
            )
        )
        if len(targets) >= max_targets:
            break
    return tuple(targets)


class AnalysisTargetResolutionEngine:
    def __init__(self, *, foundry_root: Path, policy: AnalysisTargetResolutionPolicy | None = None) -> None:
        self.foundry_root = foundry_root.resolve()
        config = self.foundry_root / "config" / "arkaon-analysis-target-resolution.json"
        self.policy = policy or AnalysisTargetResolutionPolicy.load(config)
        self.store_root = self.foundry_root / "state" / "analysis-target-resolution"
        self.store_root.mkdir(parents=True, exist_ok=True)

    def analyze(
        self,
        *,
        now: datetime,
        run_id: str,
        dry_run: bool,
        enabled_registration_count: int,
        enabled_paths_missing: bool,
        registered_platform_ids: frozenset[str],
        all_platforms_blocked: bool,
    ) -> AnalysisTargetResolutionReport:
        if now.tzinfo is None:
            raise AnalysisTargetResolutionRejected("TIMESTAMP", "timezone-aware timestamp required")
        if not self.policy.enabled:
            digest = sha256(b"disabled").hexdigest()
            return AnalysisTargetResolutionReport(
                foundry_root=self.foundry_root,
                evaluated_at=now,
                ambiguous=False,
                ambiguity_reason="DISABLED",
                last_user_site=None,
                targets=(),
                report_digest=digest,
            )
        last_request = refresh_last_user_site_request(
            foundry_root=self.foundry_root,
            store_root=self.store_root,
            scan_operator_inbox=self.policy.scan_operator_inbox,
            now=now,
            dry_run=dry_run,
        )
        last_request_not_in_registry = bool(
            last_request is not None and last_request.platform_id not in registered_platform_ids
        )
        ambiguous, reason = detect_ambiguity(
            enabled_registration_count=enabled_registration_count,
            enabled_paths_missing=enabled_paths_missing,
            last_request_not_in_registry=last_request_not_in_registry,
            all_platforms_blocked=all_platforms_blocked,
        )
        targets: tuple[CrossPlatformTarget, ...] = ()
        if ambiguous and last_request is not None:
            ledger = _load_analysis_ledger(self.store_root)
            targets = plan_cross_platform_targets(
                foundry_root=self.foundry_root,
                last_request=last_request,
                registered_platform_ids=registered_platform_ids,
                ledger=ledger,
                max_targets=self.policy.max_targets_per_run,
            )
            if not dry_run:
                for target in targets:
                    for token in target.capability_tokens:
                        if (target.platform_id, token) not in ledger:
                            _append_analysis_ledger(
                                self.store_root,
                                platform_id=target.platform_id,
                                capability_token=token,
                                run_id=run_id,
                                recorded_at=now,
                            )
        digest_payload = {
            "evaluated_at": now.isoformat(),
            "ambiguous": ambiguous,
            "ambiguity_reason": reason,
            "last_platform": last_request.platform_id if last_request else None,
            "target_platforms": [item.platform_id for item in targets],
        }
        digest = sha256(json.dumps(digest_payload, sort_keys=True).encode()).hexdigest()
        report = AnalysisTargetResolutionReport(
            foundry_root=self.foundry_root,
            evaluated_at=now,
            ambiguous=ambiguous,
            ambiguity_reason=reason,
            last_user_site=last_request,
            targets=targets,
            report_digest=digest,
        )
        if not dry_run:
            dated = self.store_root / f"{now.strftime('%Y-%m-%d')}-{digest[:12]}.json"
            dated.write_text(
                json.dumps(report.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            (self.store_root / "latest.json").write_text(
                json.dumps(report.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        return report
