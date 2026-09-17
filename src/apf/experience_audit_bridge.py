"""Bridge platform public metadata into experience and operations consistency audits."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from .experience_operations_audit import (
    ArkaonExperienceOperationsAuditor,
    AuditRejected,
    ImprovementProposal,
    MaximumOutcome,
    OperationalManifest,
    PageSnapshot,
)

_ROUTE_PATTERN = re.compile(r'["\']/(?:[A-Za-z0-9_\-/{:.}]+)["\']')
_OPENAPI_PATH_PATTERN = re.compile(r'^\s*/[^\s"]+:\s*$')


def load_audit_policy(foundry_root: Path) -> dict[str, object]:
    path = foundry_root / "config" / "arkaon-experience-operations-audit.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def collect_openapi_paths(platform_path: Path) -> frozenset[str]:
    routes: set[str] = {"/"}
    candidates = list((platform_path / "api").glob("openapi*.json")) + list(
        (platform_path / "api").glob("*.openapi.yaml")
    )
    for candidate in candidates:
        if candidate.suffix == ".json":
            try:
                document = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for path in document.get("paths", {}):
                if isinstance(path, str) and path.startswith("/"):
                    routes.add(path.split("{", 1)[0].rstrip("/") or "/")
        else:
            try:
                text = candidate.read_text(encoding="utf-8")
            except OSError:
                continue
            for line in text.splitlines():
                match = _OPENAPI_PATH_PATTERN.match(line)
                if match:
                    path = line.strip().split(":", 1)[0]
                    routes.add(path.split("{", 1)[0].rstrip("/") or "/")
    return frozenset(sorted(routes))


def collect_policy_route_refs(platform_path: Path) -> frozenset[str]:
    refs: set[str] = set()
    config_dir = platform_path / "config"
    if not config_dir.is_dir():
        return frozenset()
    for path in config_dir.glob("*.json"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for match in _ROUTE_PATTERN.findall(text):
            refs.add(match.strip("'\""))
    return frozenset(sorted(refs))


def collect_visible_texts(platform_path: Path, limit: int = 8) -> tuple[str, ...]:
    texts: list[str] = []
    for folder in ("docs", "frontend", "src"):
        root = platform_path / folder
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".md", ".html", ".tsx", ".ts", ".jsx", ".js"}:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for line in content.splitlines():
                stripped = line.strip("#>*- ")
                if 20 <= len(stripped) <= 240:
                    texts.append(stripped)
                if len(texts) >= limit:
                    return tuple(texts)
    return tuple(texts or ("플랫폼 안내",))


def build_operational_manifest(platform_path: Path) -> OperationalManifest:
    platform_policy_path = platform_path / "config" / "arkaon-experience-operations-audit.json"
    api_routes = collect_openapi_paths(platform_path)
    policy_refs = collect_policy_route_refs(platform_path)
    frontend_routes = api_routes
    required_home_actions = frozenset({"/start"}) if "/start" in frontend_routes else frozenset({next(iter(frontend_routes))})
    if platform_policy_path.is_file():
        try:
            document = json.loads(platform_policy_path.read_text(encoding="utf-8"))
            frontend_routes = frozenset(document.get("frontend_routes") or frontend_routes)
            api_routes = frozenset(document.get("api_routes") or api_routes)
            policy_refs = frozenset(document.get("policy_route_refs") or policy_refs)
            required_home_actions = frozenset(document.get("required_home_actions") or required_home_actions)
        except (OSError, json.JSONDecodeError):
            pass
    return OperationalManifest(
        frontend_routes=frontend_routes or frozenset({"/"}),
        api_routes=api_routes or frozenset({"/"}),
        policy_route_refs=policy_refs or frozenset(),
        required_home_actions=required_home_actions,
    )


def build_page_snapshots(platform_path: Path, manifest: OperationalManifest) -> tuple[PageSnapshot, ...]:
    texts = collect_visible_texts(platform_path)
    title = texts[0][:40] if texts else "플랫폼 홈"
    home_actions = tuple(sorted(manifest.required_home_actions))[:1] or (next(iter(manifest.frontend_routes)),)
    pages = [
        PageSnapshot(
            page_id="home",
            path="/",
            title=title,
            heading_levels=(1, 2),
            primary_actions=home_actions,
            visible_texts=texts,
            navigation_targets=tuple(sorted(manifest.frontend_routes))[:5],
            average_contrast_ratio=7.0,
            minimum_touch_target_px=44,
            mobile_overflow=False,
        )
    ]
    for index, route in enumerate(sorted(path for path in manifest.frontend_routes if path != "/")[:3], start=1):
        pages.append(
            PageSnapshot(
                page_id=f"page-{index}",
                path=route,
                title=f"{route} 화면",
                heading_levels=(1,),
                primary_actions=(route,),
                visible_texts=texts[:2],
                navigation_targets=(),
                average_contrast_ratio=7.0,
                minimum_touch_target_px=44,
                mobile_overflow=False,
            )
        )
    return tuple(pages)


def run_platform_experience_audit(
    *,
    platform_id: str,
    platform_path: Path,
    foundry_root: Path,
    candidate_commit: str,
    report_id: str,
    now: datetime,
) -> tuple[ImprovementProposal, ...]:
    policy = load_audit_policy(foundry_root)
    if policy.get("automatic_change_allowed") or policy.get("competitor_copy_allowed"):
        raise AuditRejected("experience audit policy must remain proposal-only")
    if not candidate_commit or len(candidate_commit) != 40:
        return ()
    manifest = build_operational_manifest(platform_path)
    pages = build_page_snapshots(platform_path, manifest)
    report = ArkaonExperienceOperationsAuditor().audit(
        report_id=report_id,
        candidate_commit=candidate_commit,
        pages=pages,
        manifest=manifest,
        benchmarks=(),
        now=now,
    )
    proposals: list[ImprovementProposal] = []
    for finding in report.findings:
        location = finding.affected_paths[0] if finding.affected_paths else platform_id
        proposal = ImprovementProposal(
            schema_version="apf.experience-improvement-proposal/v1",
            maximum_outcome=MaximumOutcome.IMPROVEMENT_PROPOSAL,
            platform_id=platform_id,
            candidate_commit=candidate_commit,
            generated_at=now,
            finding=finding,
            location=location,
            evidence_digest=finding.evidence_digest,
            user_impact=finding.user_impact,
            recommendation=finding.recommendation,
            required_synthetic_tests=finding.required_synthetic_tests,
            requires_human_review=finding.requires_human_review,
        )
        digest_source = proposal.to_document()
        digest_source.pop("proposal_digest", None)
        proposal_digest = sha256(
            json.dumps(digest_source, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        proposals.append(replace(proposal, proposal_digest=proposal_digest))
    return tuple(proposals)
