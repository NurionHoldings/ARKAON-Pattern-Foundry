"""Evolution learning domains — cross-cutting curriculum for ARKAON growth."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class EvolutionDomainRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class EvolutionDomain:
    domain_id: str
    title: str
    priority: int
    capability_tokens: tuple[str, ...]
    observation_signals: tuple[str, ...]
    abstract_patterns: tuple[str, ...]
    constraints: tuple[str, ...]


@dataclass(frozen=True)
class EvolutionDomainCatalog:
    phase: str
    external_budget_share: float
    automatic_implement_allowed: bool
    production_change_allowed: bool
    domains: tuple[EvolutionDomain, ...]
    config_path: Path

    @property
    def all_capability_tokens(self) -> frozenset[str]:
        values: set[str] = set()
        for domain in self.domains:
            values.update(domain.capability_tokens)
        return frozenset(values)

    def tokens_for_domains(self, domain_ids: frozenset[str]) -> frozenset[str]:
        if not domain_ids:
            return self.all_capability_tokens
        values: set[str] = set()
        for domain in self.domains:
            if domain.domain_id in domain_ids:
                values.update(domain.capability_tokens)
        return frozenset(values)

    def to_summary(self) -> dict[str, object]:
        return {
            "schema_version": "apf.evolution-domains-summary/v1",
            "phase": self.phase,
            "domain_count": len(self.domains),
            "capability_token_count": len(self.all_capability_tokens),
            "domains": [
                {
                    "domain_id": item.domain_id,
                    "title": item.title,
                    "priority": item.priority,
                    "token_count": len(item.capability_tokens),
                }
                for item in self.domains
            ],
        }


def load_evolution_domain_catalog(path: str | Path) -> EvolutionDomainCatalog:
    config = Path(path).expanduser().resolve()
    if not config.is_file():
        raise EvolutionDomainRejected("CONFIG_MISSING", f"evolution domain config not found: {config}")
    document = json.loads(config.read_text(encoding="utf-8"))
    if document.get("schema_version") != "apf.evolution-domains/v1":
        raise EvolutionDomainRejected("CONFIG_SCHEMA", "unsupported evolution domain schema")
    if document.get("automatic_implement_allowed") or document.get("production_change_allowed"):
        raise EvolutionDomainRejected("CONFIG_FORBIDDEN", "evolution domains must remain learning-only")
    domains: list[EvolutionDomain] = []
    for raw in document.get("domains") or ():
        if not isinstance(raw, dict):
            continue
        domain_id = str(raw.get("domain_id", "")).strip()
        if not domain_id:
            continue
        tokens = tuple(
            str(item).strip()
            for item in (raw.get("capability_tokens") or ())
            if isinstance(item, str) and str(item).strip()
        )
        if not tokens:
            raise EvolutionDomainRejected("DOMAIN_EMPTY", f"domain {domain_id} requires capability_tokens")
        domains.append(
            EvolutionDomain(
                domain_id=domain_id,
                title=str(raw.get("title", domain_id)),
                priority=max(1, int(raw.get("priority", 1))),
                capability_tokens=tokens,
                observation_signals=tuple(
                    str(item)
                    for item in (raw.get("observation_signals") or ())
                    if isinstance(item, str)
                ),
                abstract_patterns=tuple(
                    str(item)
                    for item in (raw.get("abstract_patterns") or ())
                    if isinstance(item, str)
                ),
                constraints=tuple(str(item) for item in (raw.get("constraints") or ()) if isinstance(item, str)),
            )
        )
    if not domains:
        raise EvolutionDomainRejected("DOMAIN_MISSING", "at least one evolution domain is required")
    return EvolutionDomainCatalog(
        phase=str(document.get("phase", "EXTERNAL_LEARNING_ONLY")),
        external_budget_share=float(document.get("external_budget_share", 0.65)),
        automatic_implement_allowed=bool(document.get("automatic_implement_allowed")),
        production_change_allowed=bool(document.get("production_change_allowed")),
        domains=tuple(sorted(domains, key=lambda item: (item.priority, item.domain_id))),
        config_path=config,
    )


def default_catalog(foundry_root: str | Path) -> EvolutionDomainCatalog:
    return load_evolution_domain_catalog(Path(foundry_root) / "config" / "arkaon-evolution-domains.json")
