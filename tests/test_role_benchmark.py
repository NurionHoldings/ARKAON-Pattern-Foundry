import pytest

from apf.role_benchmark import (
    BenchmarkRole,
    BenchmarkThresholds,
    RoleTrial,
    evaluate_benchmark,
    summarize_trials,
)


def trials(*, prefix: str, interventions: int, duration: float = 10.0):
    return tuple(
        RoleTrial(
            trial_id=f"{prefix}-{role.value.lower()}",
            role=role,
            passed=True,
            duration_seconds=duration,
            rework_count=0,
            ethernian_interventions=interventions,
            intent_alignment=0.97,
        )
        for role in BenchmarkRole
    )


def test_complete_role_benchmark_passes_all_025_gates() -> None:
    report = evaluate_benchmark(
        trials(prefix="baseline", interventions=4, duration=20),
        trials(prefix="current", interventions=2, duration=10),
    )

    assert report.passed
    assert report.intervention_reduction == 0.5
    assert report.duration_reduction == 0.5
    assert report.current.success_rate == 1.0
    assert report.current.average_intent_alignment == 0.97
    assert report.current.safety_violations == 0


def test_each_role_is_scored_independently() -> None:
    snapshot = summarize_trials(trials(prefix="run", interventions=1))

    assert tuple(score.role for score in snapshot.scores) == tuple(BenchmarkRole)
    assert all(score.trials == 1 for score in snapshot.scores)
    assert all(score.success_rate == 1.0 for score in snapshot.scores)


def test_missing_role_and_low_quality_are_blocking() -> None:
    baseline = trials(prefix="baseline", interventions=4)
    current = list(trials(prefix="current", interventions=3))
    current.pop()
    current[0] = RoleTrial(
        trial_id=current[0].trial_id,
        role=current[0].role,
        passed=False,
        duration_seconds=30,
        rework_count=2,
        ethernian_interventions=3,
        intent_alignment=0.7,
        safety_violations=1,
    )

    report = evaluate_benchmark(baseline, tuple(current))

    assert not report.passed
    assert "REQUIRED_ROLE_COVERAGE_MISSING" in report.blocking_reasons
    assert "INTENT_ALIGNMENT_LOW" in report.blocking_reasons
    assert "ETHERNIAN_WORK_REDUCTION_LOW" in report.blocking_reasons
    assert "SAFETY_VIOLATION_DETECTED" in report.blocking_reasons
    assert "ROLE_SUCCESS_RATE_LOW:RESEARCH" in report.blocking_reasons


def test_zero_baseline_cannot_claim_artificial_reduction() -> None:
    report = evaluate_benchmark(
        trials(prefix="baseline", interventions=0),
        trials(prefix="current", interventions=0),
    )

    assert report.intervention_reduction == 0
    assert "ETHERNIAN_WORK_REDUCTION_LOW" in report.blocking_reasons


@pytest.mark.parametrize(
    "changes,error",
    [
        ({"duration_seconds": -1}, "DURATION"),
        ({"rework_count": -1}, "COUNTS"),
        ({"intent_alignment": 1.1}, "ALIGNMENT"),
        ({"trial_id": " "}, "TRIAL_ID"),
    ],
)
def test_invalid_measurements_fail_closed(changes, error) -> None:
    values = {
        "trial_id": "trial",
        "role": BenchmarkRole.TEST,
        "passed": True,
        "duration_seconds": 1,
        "rework_count": 0,
        "ethernian_interventions": 0,
        "intent_alignment": 1,
    }
    values.update(changes)
    with pytest.raises(ValueError, match=error):
        RoleTrial(**values)


def test_untyped_trial_collection_and_fields_fail_closed() -> None:
    sample = trials(prefix="typed", interventions=1)
    with pytest.raises(ValueError, match="TYPED_ROLE_TRIAL_TUPLE_REQUIRED"):
        summarize_trials(list(sample))
    with pytest.raises(ValueError, match="TYPED_ROLE_TRIAL_TUPLE_REQUIRED"):
        summarize_trials((object(),))
    with pytest.raises(ValueError, match="TYPED_ROLE_AND_BOOLEAN_RESULT_REQUIRED"):
        RoleTrial("bad-role", "TEST", True, 1, 0, 0, 1)
    with pytest.raises(ValueError, match="TYPED_ROLE_AND_BOOLEAN_RESULT_REQUIRED"):
        RoleTrial("bad-pass", BenchmarkRole.TEST, 1, 1, 0, 0, 1)


def test_duplicate_trial_identity_is_rejected() -> None:
    sample = trials(prefix="same", interventions=1)
    with pytest.raises(ValueError, match="DUPLICATE_TRIAL_ID"):
        summarize_trials((sample[0], sample[0]))


def test_thresholds_are_policy_configurable_without_weak_defaults() -> None:
    strict = BenchmarkThresholds(
        minimum_role_trials=2,
        minimum_success_rate=1,
        minimum_intent_alignment=0.99,
        minimum_intervention_reduction=0.75,
    )
    report = evaluate_benchmark(
        trials(prefix="baseline", interventions=4),
        trials(prefix="current", interventions=1),
        thresholds=strict,
    )

    assert not report.passed
    assert any(reason.startswith("ROLE_SAMPLE_TOO_SMALL:") for reason in report.blocking_reasons)
    assert "INTENT_ALIGNMENT_LOW" in report.blocking_reasons
