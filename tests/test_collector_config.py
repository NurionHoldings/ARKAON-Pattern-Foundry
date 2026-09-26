import json
from pathlib import Path

from apf.collector_runtime import load_policy
from apf.collector_service import JsonCandidateProvider


def test_collector_default_config_loads_policy_and_sources():
    config_path = Path("config/collector.default.json")
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    assert raw["enabled"] is True
    assert raw["interval_seconds"] >= 60
    assert raw.get("sources"), "continuous collector requires at least one source"

    policy = load_policy(config_path)
    assert policy.enabled
    assert policy.collect_immediately
    assert policy.interval_seconds == 900

    sources = list(JsonCandidateProvider(config_path).candidates())
    assert len(sources) >= 1
    tagged = [source for source in sources if source.learning_domain_ids]
    assert tagged, "hourly learning requires domain_ids on collector sources"
    for source in sources:
        assert source.locator.startswith("https://")
        assert source.intent_relevance >= 0.30
