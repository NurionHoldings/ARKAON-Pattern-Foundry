from apf.domain import Classification, RiskClass
from apf.governance import (
    FOUNDRY_REPOSITORY,
    AutonomousGrant,
    PublicationGateInput,
    can_execute_autonomously,
    can_publish,
)


def base(**changes):
    values = {
        "classification": Classification.INTERNAL,
        "derivation_allowed": True,
        "evidence_coverage": 1,
        "personal_data_findings": 0,
        "secret_findings": 0,
        "customer_identifier_findings": 0,
        "license_conflicts": 0,
        "critical_security_findings": 0,
        "approval_roles": frozenset({"domain-owner"}),
        "risk_class": RiskClass.MODERATE,
        "domains": frozenset({"WORKFLOW"}),
    }
    values.update(changes)
    return PublicationGateInput(**values)


def test_clean_candidate_can_publish():
    assert can_publish(base()) == (True, ())


def test_contamination_blocks_publication():
    ok, failures = can_publish(base(personal_data_findings=1))
    assert not ok and "PERSONAL_DATA_FOUND" in failures


def test_high_risk_requires_two_roles():
    ok, failures = can_publish(base(domains=frozenset({"PAYMENT"})))
    assert not ok and "INSUFFICIENT_INDEPENDENT_APPROVALS" in failures


def test_owner_standing_command_authorizes_foundry_work():
    grant = AutonomousGrant(
        granted_by="최인석",
        repository=FOUNDRY_REPOSITORY,
        allowed_actions=frozenset({"analyze", "design", "edit", "test", "commit", "open_pull_request"}),
    )
    assert can_execute_autonomously(
        grant, repository=FOUNDRY_REPOSITORY, action="open_pull_request"
    ) == (True, "AUTHORIZED_STANDING_COMMAND")


def test_standing_command_cannot_escape_repository():
    grant = AutonomousGrant(
        granted_by="최인석",
        repository=FOUNDRY_REPOSITORY,
        allowed_actions=frozenset({"edit"}),
    )
    assert can_execute_autonomously(
        grant, repository="NurionHoldings/mjn", action="edit"
    ) == (False, "REPOSITORY_OUT_OF_SCOPE")


def test_standing_command_does_not_cover_unlisted_or_unsafe_actions():
    grant = AutonomousGrant(
        granted_by="최인석",
        repository=FOUNDRY_REPOSITORY,
        allowed_actions=frozenset({"edit", "delete_repository"}),
    )
    assert can_execute_autonomously(
        grant, repository=FOUNDRY_REPOSITORY, action="delete_repository"
    ) == (False, "ACTION_OUT_OF_SCOPE")
