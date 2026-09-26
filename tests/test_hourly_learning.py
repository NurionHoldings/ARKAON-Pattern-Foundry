import json
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from apf.collector_runtime import CollectorRuntime, MemoryAuditSink, MemoryContentHashStore
from apf.collector_service import JsonCandidateProvider
from apf.continuous_collection import CollectionCandidate, ContinuousCollectionPolicy
from apf.external_learning import SourceKind
from apf.hourly_learning import (
    HourlyLearningRejected,
    HourlyLearningSchedule,
    candidate_matches_topic,
    resolve_active_topic,
    write_hourly_learning_state,
)


def test_hourly_schedule_loads_all_24_hours():
    schedule = HourlyLearningSchedule.load(Path("config/arkaon-hourly-learning-schedule.json"))
    assert schedule.enabled
    assert schedule.timezone == "Asia/Seoul"
    assert len(schedule.topics_by_hour) == 24


def test_resolve_active_topic_for_seoul_hour():
    schedule = HourlyLearningSchedule.load(Path("config/arkaon-hourly-learning-schedule.json"))
    # 2026-09-17 08:00 KST = hour 8 = TYPOGRAPHY_MOTION
    now = datetime(2026, 9, 17, 8, 0, tzinfo=ZoneInfo("Asia/Seoul")).astimezone(UTC)
    topic = resolve_active_topic(schedule, now=now)
    assert topic.local_hour == 8
    assert topic.domain_id == "TYPOGRAPHY_MOTION"


def test_candidate_matches_topic_by_domain_ids():
    schedule = HourlyLearningSchedule.load(Path("config/arkaon-hourly-learning-schedule.json"))
    now = datetime(2026, 9, 17, 16, 0, tzinfo=ZoneInfo("Asia/Seoul")).astimezone(UTC)
    topic = resolve_active_topic(schedule, now=now)
    payment = CollectionCandidate(
        source_id="pay",
        kind=SourceKind.OFFICIAL_STANDARD,
        locator="https://example.org/pay",
        intent_relevance=0.9,
        learning_domain_ids=("PAYMENT_CHECKOUT_FLOW",),
    )
    typography = CollectionCandidate(
        source_id="type",
        kind=SourceKind.OFFICIAL_STANDARD,
        locator="https://example.org/type",
        intent_relevance=0.9,
        learning_domain_ids=("TYPOGRAPHY_MOTION",),
    )
    assert candidate_matches_topic(payment, topic)
    assert not candidate_matches_topic(typography, topic)


def test_integration_hour_collects_only_matching_sources(tmp_path):
    config = tmp_path / "collector.json"
    config.write_text(
        json.dumps(
            {
                "enabled": True,
                "startup_trigger": "OS_BOOT",
                "collect_immediately": True,
                "interval_seconds": 900,
                "external_target_ratio": 0.65,
                "internal_target_ratio": 0.35,
                "minimum_intent_relevance": 0.30,
                "max_response_bytes": 5000,
                "sources": [
                    {
                        "source_id": "pay",
                        "kind": "OFFICIAL_STANDARD",
                        "locator": "https://example.org/pay",
                        "intent_relevance": 0.9,
                        "license_clarity": 0.9,
                        "domain_ids": ["PAYMENT_CHECKOUT_FLOW"],
                    },
                    {
                        "source_id": "type",
                        "kind": "OFFICIAL_STANDARD",
                        "locator": "https://example.org/type",
                        "intent_relevance": 0.9,
                        "license_clarity": 0.9,
                        "domain_ids": ["TYPOGRAPHY_MOTION"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    schedule_path = tmp_path / "schedule.json"
    schedule_path.write_text(
        Path("config/arkaon-hourly-learning-schedule.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    schedule = HourlyLearningSchedule.load(schedule_path)
    now = datetime(2026, 9, 17, 16, 0, tzinfo=ZoneInfo("Asia/Seoul")).astimezone(UTC)
    topic = resolve_active_topic(schedule, now=now)

    class Fetcher:
        def fetch(self, candidate, max_bytes):
            return b"payload"

    runtime = CollectorRuntime(
        ContinuousCollectionPolicy(),
        JsonCandidateProvider(config),
        Fetcher(),
        MemoryAuditSink(),
        content_hashes=MemoryContentHashStore(),
        topic_filter=lambda candidate: candidate_matches_topic(candidate, topic),
    )
    result = runtime.run_once()
    assert result.considered == 1
    assert result.skipped_out_of_topic == 1


def test_write_hourly_learning_state(tmp_path):
    schedule = HourlyLearningSchedule.load(Path("config/arkaon-hourly-learning-schedule.json"))
    now = datetime(2026, 9, 17, 10, 0, tzinfo=ZoneInfo("Asia/Seoul")).astimezone(UTC)
    topic = resolve_active_topic(schedule, now=now)
    current = write_hourly_learning_state(
        foundry_root=tmp_path,
        topic=topic,
        cycle_result={"considered": 2, "collected": 1, "denied": 0, "duplicate": 1, "failed": 0, "skipped_out_of_topic": 3},
    )
    assert current.exists()
    payload = json.loads(current.read_text(encoding="utf-8"))
    assert payload["topic"]["domain_id"] == "SIGNATURE_MOTION"


def test_incomplete_schedule_rejected(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {
                "schema_version": "apf.hourly-learning-schedule/v1",
                "timezone": "UTC",
                "hours": [{"hour": 0, "domain_id": "X", "topic_title": "x"}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(HourlyLearningRejected, match="24 local hours"):
        HourlyLearningSchedule.load(bad)
