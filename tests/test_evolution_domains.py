import json
from pathlib import Path

import pytest

from apf.evolution_domains import (
    EvolutionDomainRejected,
    default_catalog,
    load_evolution_domain_catalog,
)


def test_evolution_domain_catalog_loads_nine_domains():
    catalog = default_catalog(Path("."))
    assert len(catalog.domains) == 10
    assert catalog.phase == "EXTERNAL_LEARNING_ONLY"
    assert catalog.automatic_implement_allowed is False
    assert len(catalog.all_capability_tokens) >= 36


def test_evolution_domains_reject_auto_implement():
    config = Path("config/arkaon-evolution-domains.json")
    raw = json.loads(config.read_text(encoding="utf-8"))
    raw["automatic_implement_allowed"] = True
    bad = config.parent / "evolution-domains.bad.json"
    bad.write_text(json.dumps(raw), encoding="utf-8")
    try:
        with pytest.raises(EvolutionDomainRejected, match="learning-only"):
            load_evolution_domain_catalog(bad)
    finally:
        bad.unlink(missing_ok=True)


def test_domain_ids_cover_user_curriculum():
    catalog = default_catalog(Path("."))
    ids = {item.domain_id for item in catalog.domains}
    assert "TYPOGRAPHY_MOTION" in ids
    assert "VIDEO_TEMPLATE_EFFECTS" in ids
    assert "LIFECYCLE_STEWARDSHIP" in ids
    assert "EMERGING_MARKET_SIGNALS" in ids
