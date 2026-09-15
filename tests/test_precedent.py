from apf.precedent import (
    Precedent,
    assess_precedent,
    build_benchmark_plan,
    independent_groups_for_feature,
)


def precedent(source_id: str, feature: str, group: str = "standard", **changes) -> Precedent:
    values = {
        "source_id": source_id,
        "feature": feature,
        "authority": 0.9,
        "production_maturity": 0.9,
        "failure_coverage": 0.9,
        "interoperability": 0.9,
        "intent_relevance": 0.9,
        "provenance_recorded": True,
        "independent_source_group": group,
    }
    values.update(changes)
    return Precedent(**values)


def test_good_precedent_extracts_function_and_failure_structure():
    result = assess_precedent(precedent("temporal", "durable-workflow"))
    assert result.qualified
    assert "FUNCTION" in result.extract
    assert "FAILURE_MODE" in result.extract
    assert "RECOVERY" in result.extract


def test_popular_but_irrelevant_precedent_is_not_followed():
    result = assess_precedent(
        precedent("popular", "unrelated", intent_relevance=0.2, production_maturity=1)
    )
    assert not result.qualified


def test_every_required_feature_needs_a_qualified_precedent_before_design():
    plan = build_benchmark_plan(
        {"identity", "workflow"},
        [precedent("openid", "identity")],
    )
    assert not plan.ready_for_independent_design
    assert plan.uncovered_features == ("workflow",)


def test_complete_benchmark_plan_unlocks_independent_design():
    plan = build_benchmark_plan(
        {"identity", "workflow"},
        [precedent("openid", "identity"), precedent("temporal", "workflow")],
    )
    assert plan.ready_for_independent_design
    assert plan.uncovered_features == ()


def test_independent_sources_are_counted_without_duplicate_inflation():
    items = [
        precedent("standard-a", "workflow", "standards"),
        precedent("standard-b", "workflow", "standards"),
        precedent("production", "workflow", "implementations"),
    ]
    assert independent_groups_for_feature("workflow", items) == 2
