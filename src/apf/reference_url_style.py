"""Structural style profiles from user-supplied reference URLs — similar feel, no verbatim copy."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit

from .cross_platform_learning import build_surface_observation_document, fetch_public_payload

_HTTPS = re.compile(r"^https://", re.IGNORECASE)

_FEATURE_ALIASES: dict[str, tuple[str, ...]] = {
    "hero": ("hero", "landing", "home"),
    "process": ("process", "funnel", "step", "flow"),
    "checkout": ("checkout", "payment", "pay"),
    "mypage": ("mypage", "dashboard", "account"),
    "auth": ("auth", "login", "signup", "sign-up"),
    "comparison": ("comparison", "compare", "vs"),
    "faq": ("faq", "help"),
    "contract": ("contract", "esign", "e-contract", "전자"),
}


class ReferenceUrlRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ReferenceStyleProfile:
    source_url: str
    observation_digest: str
    policy_route_refs: tuple[str, ...]
    style_tags: tuple[str, ...]
    structural_signals: dict[str, object]

    def to_document(self) -> dict[str, object]:
        return {
            "source_url": self.source_url,
            "observation_digest": self.observation_digest,
            "policy_route_refs": list(self.policy_route_refs),
            "style_tags": list(self.style_tags),
            "structural_signals": self.structural_signals,
            "verbatim_storage": False,
            "copy_prohibited": True,
        }


@dataclass(frozen=True)
class FeatureReferenceStyle:
    feature_id: str
    source_url: str
    profile: ReferenceStyleProfile

    def to_document(self) -> dict[str, object]:
        return {
            "feature_id": self.feature_id,
            "source_url": self.source_url,
            "profile": self.profile.to_document(),
        }


def _validate_public_https(url: str) -> None:
    parsed = urlsplit(url.strip())
    if parsed.scheme != "https" or not parsed.netloc:
        raise ReferenceUrlRejected("URL_INVALID", "reference URL must be public HTTPS")


def _style_tags_from_observation(document: dict[str, object]) -> tuple[str, ...]:
    tags: set[str] = set()
    routes = document.get("policy_route_refs") or ()
    route_set = {str(item) for item in routes}
    if route_set & {"surface/hero-primary-cta"}:
        tags.add("hero-forward")
    if any(item.startswith("flow/step-") for item in route_set):
        tags.add("step-process-heavy")
    if "surface/comparison-matrix" in route_set:
        tags.add("comparison-led")
    if "surface/mypage-dashboard" in route_set:
        tags.add("lifecycle-dashboard")
    if "surface/faq-accordion" in route_set:
        tags.add("faq-objection-layer")
    if "flow/electronic-contract" in route_set:
        tags.add("e-contract-forward")
    signals = document.get("observation_signals") or {}
    if signals.get("heading_count_bin") in {"4-5", "6+"}:
        tags.add("section-rich")
    if signals.get("link_count_bin") in {"4-5", "6+"}:
        tags.add("navigation-dense")
    if not tags:
        tags.add("minimal-public-surface")
    return tuple(sorted(tags))


def observe_reference_style(
    *,
    url: str,
    now,
    fetch_payload=None,
) -> ReferenceStyleProfile:
    _validate_public_https(url)
    fetcher = fetch_payload or fetch_public_payload
    payload = fetcher(url.strip())
    document = build_surface_observation_document(
        platform_id="REFERENCE",
        source_url=url.strip(),
        payload=payload,
        now=now,
    )
    return ReferenceStyleProfile(
        source_url=url.strip(),
        observation_digest=str(document["observation_digest"]),
        policy_route_refs=tuple(str(item) for item in document.get("policy_route_refs") or ()),
        style_tags=_style_tags_from_observation(document),
        structural_signals=dict(document.get("observation_signals") or {}),
    )


def normalize_feature_id(raw: str) -> str:
    cleaned = raw.strip().casefold().replace(" ", "-")
    for feature_id, aliases in _FEATURE_ALIASES.items():
        if cleaned == feature_id or cleaned in aliases:
            return feature_id
    if cleaned:
        return cleaned
    raise ReferenceUrlRejected("FEATURE_ID_INVALID", "feature id required")


def observe_feature_references(
    *,
    feature_urls: dict[str, str],
    now,
    fetch_payload=None,
) -> tuple[FeatureReferenceStyle, ...]:
    observed: list[FeatureReferenceStyle] = []
    for raw_feature, url in sorted(feature_urls.items()):
        feature_id = normalize_feature_id(raw_feature)
        profile = observe_reference_style(url=url, now=now, fetch_payload=fetch_payload)
        observed.append(FeatureReferenceStyle(feature_id=feature_id, source_url=url.strip(), profile=profile))
    return tuple(observed)


def persist_reference_observations(
    *,
    foundry_root: Path,
    tenant_id: str,
    proposal_id: str,
    site_profile: ReferenceStyleProfile | None,
    feature_profiles: tuple[FeatureReferenceStyle, ...],
) -> str:
    store = foundry_root / "state" / "co-creation" / "reference-styles"
    store.mkdir(parents=True, exist_ok=True)
    document = {
        "schema_version": "apf.reference-style-bundle/v1",
        "tenant_id": tenant_id,
        "proposal_id": proposal_id,
        "site_profile": None if site_profile is None else site_profile.to_document(),
        "feature_profiles": [item.to_document() for item in feature_profiles],
    }
    digest = sha256(json.dumps(document, sort_keys=True).encode()).hexdigest()
    document["bundle_digest"] = digest
    path = store / f"{proposal_id}-{digest[:12]}.json"
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path.relative_to(foundry_root).as_posix()


def apply_reference_styles_to_sections(
    sections: tuple,
    *,
    site_profile: ReferenceStyleProfile | None,
    feature_profiles: tuple[FeatureReferenceStyle, ...],
) -> tuple:
    from .conversational_co_creation import TemplateSectionBlueprint

    feature_map = {item.feature_id: item for item in feature_profiles}
    updated: list[TemplateSectionBlueprint] = []
    for section in sections:
        ref = feature_map.get(section.section_id)
        if ref is None and site_profile is not None:
            ref_profile = site_profile
            ref_url = site_profile.source_url
        elif ref is not None:
            ref_profile = ref.profile
            ref_url = ref.source_url
        else:
            updated.append(section)
            continue
        purpose = (
            f"{section.purpose}; reference feel {', '.join(ref_profile.style_tags)} "
            f"from {ref_url} (structural only)"
        )
        updated.append(
            TemplateSectionBlueprint(
                section_id=section.section_id,
                purpose=purpose,
                pattern_token=section.pattern_token,
                cta_slot=section.cta_slot,
            )
        )
    return tuple(updated)
