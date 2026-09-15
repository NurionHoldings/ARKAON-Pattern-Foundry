from apf.domain import Classification, RiskClass
from apf.governance import PublicationGateInput, can_publish


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
