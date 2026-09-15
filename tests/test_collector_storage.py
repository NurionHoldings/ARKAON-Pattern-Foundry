from datetime import UTC, datetime

import pytest

from apf.collector_runtime import CollectionAuditEvent
from apf.collector_storage import (
    AuditIntegrityError,
    HashChainedJsonLinesAuditSink,
    SQLiteContentHashStore,
    verify_audit_log,
)


def event(source_id: str) -> CollectionAuditEvent:
    return CollectionAuditEvent(
        source_id=source_id,
        locator="https://example.org",
        decision="COLLECT_REUSABLE",
        collected=True,
        reusable=True,
        content_hash="a" * 64,
        content_bytes=10,
        occurred_at=datetime.now(UTC),
    )


def test_content_hash_survives_store_recreation(tmp_path):
    path = tmp_path / "state.sqlite3"
    assert SQLiteContentHashStore(path).claim("digest")
    assert not SQLiteContentHashStore(path).claim("digest")
    assert SQLiteContentHashStore(path).contains("digest")


def test_audit_chain_survives_sink_recreation(tmp_path):
    path = tmp_path / "audit.jsonl"
    HashChainedJsonLinesAuditSink(path).record(event("first"))
    HashChainedJsonLinesAuditSink(path).record(event("second"))
    assert verify_audit_log(path) is not None
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


def test_modified_audit_record_is_detected(tmp_path):
    path = tmp_path / "audit.jsonl"
    HashChainedJsonLinesAuditSink(path).record(event("original"))
    path.write_text(
        path.read_text(encoding="utf-8").replace("original", "tampered"), encoding="utf-8"
    )
    with pytest.raises(AuditIntegrityError, match="broken audit chain"):
        verify_audit_log(path)
