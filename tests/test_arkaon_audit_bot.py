import json
from dataclasses import replace

import pytest

from apf.arkaon_audit_bot import (
    AuditBotError,
    AuditDecision,
    ChangeReport,
    GitRevisionReader,
    run_audit,
)

BASE = "a" * 40
CANDIDATE = "b" * 40
SCOPE = "c" * 64

POLICY = {
    "schema_version": "apf.arkaon-audit-policy/1.0",
    "protected_paths": ["src/apf/self_improvement_relay.py"],
    "bounded_keys": ["max_runtime_seconds"],
    "portable_path_keys": ["foundry_root"],
    "intent_sensitive_prefixes": ["src/apf/", "config/"],
}


class MemoryReader:
    def __init__(self, changed, before=None, after=None):
        self.changed = tuple(changed)
        self.before = before or {}
        self.after = after or {}

    def changed_paths(self, base_sha, candidate_sha):
        assert (base_sha, candidate_sha) == (BASE, CANDIDATE)
        return self.changed

    def read(self, revision, path):
        return (self.before if revision == BASE else self.after).get(path)


def report(paths, *, intents=("knowledge/feature-intents/a.json",), tests=("sha256:" + "d" * 64,)):
    return ChangeReport("audit-001", SCOPE, tuple(paths), tuple(intents), tuple(tests))


def test_clean_report_passes_but_never_authorizes_merge_or_deployment():
    reader = MemoryReader(["docs/a.md"], after={"docs/a.md": b"safe"})
    result = audit(reader, report(["docs/a.md"]), approved_paths=("docs",))

    assert result.decision == AuditDecision.PASS
    assert result.merge_allowed is result.deployment_allowed is False
    assert result.evidence_digest.startswith("sha256:")


def test_protected_control_deletion_and_unbounded_resource_are_blocked():
    paths = ["src/apf/self_improvement_relay.py", "config/resource-limits.json"]
    reader = MemoryReader(
        paths,
        before={"src/apf/self_improvement_relay.py": b"control"},
        after={"config/resource-limits.json": json.dumps({"max_runtime_seconds": None}).encode()},
    )
    result = audit(reader, report(paths), approved_paths=("src", "config"))

    assert result.decision == AuditDecision.BLOCKED
    assert {finding.code for finding in result.findings} >= {"PROTECTED_CONTROL_DELETED", "UNBOUNDED_RESOURCE_LIMIT"}


def test_report_diff_mismatch_machine_path_and_missing_evidence_hold():
    reader = MemoryReader(
        ["config/platforms.json"],
        after={"config/platforms.json": json.dumps({"foundry_root": "D:\\ARKAON"}).encode()},
    )
    value = report(["phantom.json"], intents=(), tests=())
    result = audit(reader, value, approved_paths=("config",))

    assert result.decision == AuditDecision.HOLD
    assert {finding.code for finding in result.findings} >= {
        "UNREPORTED_CHANGE",
        "PHANTOM_REPORTED_CHANGE",
        "MACHINE_SPECIFIC_ABSOLUTE_PATH",
        "INTENT_DNA_EVIDENCE_MISSING",
        "TEST_EVIDENCE_MISSING",
    }


def test_manifest_digest_changes_when_audited_facts_change():
    reader = MemoryReader(["docs/a.md"], after={"docs/a.md": b"safe"})
    first = audit(reader, report(["docs/a.md"]), approved_paths=("docs",))
    second = audit(reader, replace(report(["docs/a.md"]), request_id="audit-002"), approved_paths=("docs",))
    assert first.evidence_digest != second.evidence_digest


def test_git_reader_rejects_revision_and_path_injection(tmp_path):
    reader = GitRevisionReader(tmp_path)
    with pytest.raises(AuditBotError, match="GIT_OBJECT_ID_INVALID"):
        reader.changed_paths("HEAD;rm", CANDIDATE)
    with pytest.raises(AuditBotError, match="UNSAFE_REPOSITORY_PATH"):
        reader.read(BASE, "../secret")


def test_scope_digest_or_path_escape_is_blocked():
    reader = MemoryReader(["src/apf/new.py"], after={"src/apf/new.py": b"safe"})
    wrong_scope = replace(report(["src/apf/new.py"]), scope_digest="e" * 64)
    result = audit(reader, wrong_scope, approved_paths=("docs",))
    assert result.decision == AuditDecision.BLOCKED
    assert {finding.code for finding in result.findings} >= {
        "SCOPE_DIGEST_MISMATCH",
        "CHANGE_OUTSIDE_APPROVED_SCOPE",
    }


def audit(reader, change_report, *, approved_paths):
    return run_audit(
        reader=reader,
        base_sha=BASE,
        candidate_sha=CANDIDATE,
        report=change_report,
        policy_document=POLICY,
        approved_scope_digest=SCOPE,
        approved_paths=approved_paths,
    )
