"""Malformed feedback must be visible without blocking later valid packets."""

import json
from datetime import UTC, datetime

import pytest

from apf.fundamental_learning_gates import FundamentalLearningGateAssessor, GateStatus


@pytest.mark.parametrize('bad_bytes', [
    b'\xff', b'{invalid', b'[]', b'null', b'"text"', b'42', b'true',
])
def test_bad_packet_is_reported_and_later_valid_feedback_is_evaluated(tmp_path, bad_bytes):
    policy = tmp_path / 'config' / 'arkaon-fundamental-learning-gates.json'
    policy.parent.mkdir()
    policy.write_text(json.dumps({
        'schema_version': 'apf.fundamental-learning-gates/v1', 'stages': {},
    }), encoding='utf-8')
    inbox = tmp_path / 'inbox' / 'eternian-review'
    inbox.mkdir(parents=True)
    bad = inbox / '00-bad.json'
    bad.write_bytes(bad_bytes)
    valid = inbox / '99-valid.json'
    valid.write_text(json.dumps({
        'schema_version': 'apf.failure-learning-feedback/v1',
        'failure_source_ref': 'state/failure.json', 'root_cause_code': 'COPY',
        'derived_learning_task_id': 'task-1', 'independent_review_ref': 'inbox/eternian-review/task-1.json',
    }), encoding='utf-8')
    expected_valid = valid.read_bytes()
    assessor = FundamentalLearningGateAssessor(foundry_root=tmp_path)
    report = assessor.assess(now=datetime(2026, 11, 5, tzinfo=UTC))
    assert len(report.stages) == 5
    stage = report.stages[-1]
    assert stage.status is GateStatus.PARTIAL
    assert 'complete failure→learning→review chains: 1' in stage.evidence
    assert 'invalid feedback packets: 1' in stage.evidence
    assert any('invalid feedback packet' in blocker for blocker in stage.blockers)
    assert bad.read_bytes() == bad_bytes
    assert valid.read_bytes() == expected_valid
    assert not assessor.store_root.exists()
    assert report.operational_apply_complete is False


def test_valid_feedback_keeps_existing_review_candidate_status(tmp_path):
    inbox = tmp_path / 'inbox' / 'research'
    inbox.mkdir(parents=True)
    (inbox / 'candidate.json').write_text(
        json.dumps({'summary': 'learning failure'}), encoding='utf-8',
    )
    stage = FundamentalLearningGateAssessor(foundry_root=tmp_path)._assess_failure_feedback({})
    assert stage.status is GateStatus.CANDIDATE_EVIDENCE
    assert 'invalid feedback packets: 0' in stage.evidence


def test_unreadable_file_does_not_hide_later_candidate(tmp_path, monkeypatch):
    from pathlib import Path

    inbox = tmp_path / 'inbox' / 'research'
    inbox.mkdir(parents=True)
    bad = inbox / '00-unreadable.json'
    bad.write_text('{}', encoding='utf-8')
    (inbox / '99-valid.json').write_text(
        json.dumps({'summary': 'learning failure'}), encoding='utf-8',
    )
    original = Path.read_text

    def read(path, *args, **kwargs):
        if path == bad:
            raise PermissionError('sensitive absolute path must not reach report')
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', read)
    stage = FundamentalLearningGateAssessor(foundry_root=tmp_path)._assess_failure_feedback({})
    assert stage.status is GateStatus.PARTIAL
    assert 'keyword-only candidate packets: 1' in stage.evidence
    assert 'UNREADABLE_FILE=1' in stage.blockers[0]
    assert 'sensitive absolute path' not in repr(stage)
