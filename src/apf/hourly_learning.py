"""Hourly themed self-learning schedule for ARKAON collection."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .continuous_collection import CollectionCandidate


class HourlyLearningRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class HourlyTopic:
    local_hour: int
    domain_id: str
    topic_title: str
    collect_all_domains: bool
    timezone: str
    observed_at: datetime

    def to_document(self) -> dict[str, object]:
        return {
            "local_hour": self.local_hour,
            "domain_id": self.domain_id,
            "topic_title": self.topic_title,
            "collect_all_domains": self.collect_all_domains,
            "timezone": self.timezone,
            "observed_at": self.observed_at.isoformat(),
        }


@dataclass(frozen=True)
class HourlyLearningSchedule:
    enabled: bool
    timezone: str
    automatic_implement_allowed: bool
    production_change_allowed: bool
    topics_by_hour: dict[int, HourlyTopic]
    config_path: Path

    @classmethod
    def load(cls, path: str | Path) -> HourlyLearningSchedule:
        config = Path(path).expanduser().resolve()
        if not config.is_file():
            raise HourlyLearningRejected("CONFIG_MISSING", f"hourly schedule not found: {config}")
        document = json.loads(config.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.hourly-learning-schedule/v1":
            raise HourlyLearningRejected("CONFIG_SCHEMA", "unsupported hourly learning schema")
        if document.get("automatic_implement_allowed") or document.get("production_change_allowed"):
            raise HourlyLearningRejected("CONFIG_FORBIDDEN", "hourly learning must remain learning-only")
        timezone = str(document.get("timezone", "UTC"))
        topics_by_hour: dict[int, HourlyTopic] = {}
        for raw in document.get("hours") or ():
            if not isinstance(raw, dict):
                continue
            hour = int(raw["hour"])
            if not 0 <= hour <= 23:
                raise HourlyLearningRejected("HOUR_INVALID", f"hour must be 0-23, got {hour}")
            domain_id = str(raw.get("domain_id", "UNKNOWN"))
            topics_by_hour[hour] = HourlyTopic(
                local_hour=hour,
                domain_id=domain_id,
                topic_title=str(raw.get("topic_title", domain_id)),
                collect_all_domains=bool(raw.get("collect_all_domains", domain_id == "INTEGRATION_REVIEW")),
                timezone=timezone,
                observed_at=datetime.now(UTC),
            )
        if len(topics_by_hour) != 24:
            raise HourlyLearningRejected("HOUR_INCOMPLETE", "schedule must define all 24 local hours")
        return cls(
            enabled=bool(document.get("enabled", True)),
            timezone=timezone,
            automatic_implement_allowed=bool(document.get("automatic_implement_allowed")),
            production_change_allowed=bool(document.get("production_change_allowed")),
            topics_by_hour=topics_by_hour,
            config_path=config,
        )


def resolve_active_topic(
    schedule: HourlyLearningSchedule,
    *,
    now: datetime | None = None,
) -> HourlyTopic:
    if not schedule.enabled:
        raise HourlyLearningRejected("SCHEDULE_DISABLED", "hourly learning schedule is disabled")
    observed = now or datetime.now(UTC)
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=UTC)
    local = observed.astimezone(ZoneInfo(schedule.timezone))
    template = schedule.topics_by_hour[local.hour]
    return HourlyTopic(
        local_hour=template.local_hour,
        domain_id=template.domain_id,
        topic_title=template.topic_title,
        collect_all_domains=template.collect_all_domains,
        timezone=schedule.timezone,
        observed_at=observed,
    )


def candidate_matches_topic(candidate: CollectionCandidate, topic: HourlyTopic) -> bool:
    if topic.collect_all_domains:
        return bool(candidate.learning_domain_ids)
    if not candidate.learning_domain_ids:
        return True
    return topic.domain_id in candidate.learning_domain_ids


def write_hourly_learning_state(
    *,
    foundry_root: Path,
    topic: HourlyTopic,
    cycle_result: dict[str, int],
) -> Path:
    state_root = foundry_root / "state" / "hourly-learning"
    state_root.mkdir(parents=True, exist_ok=True)
    target = state_root / f"{topic.observed_at.astimezone(ZoneInfo(topic.timezone)).strftime('%Y-%m-%d')}.jsonl"
    record = {
        "schema_version": "apf.hourly-learning-cycle/v1",
        "topic": topic.to_document(),
        "cycle": cycle_result,
    }
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
        handle.write("\n")
    current = foundry_root / "state" / "hourly-learning-current.json"
    current.write_text(
        json.dumps(
            {
                "schema_version": "apf.hourly-learning-current/v1",
                **record,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return current


def default_schedule(foundry_root: str | Path) -> HourlyLearningSchedule:
    return HourlyLearningSchedule.load(Path(foundry_root) / "config" / "arkaon-hourly-learning-schedule.json")
