import hashlib
import sqlite3
from dataclasses import asdict

import pytest

from apf.evidence_vault import (
    EvidenceConflictError,
    EvidenceIntegrityError,
    EvidenceNotFoundError,
    EvidenceVault,
    EvidenceVaultError,
)
from apf.learning_safety import LearningSafetyViolation


def metadata() -> tuple[dict[str, object], dict[str, object]]:
    return (
        {"source_uri": "https://example.org/spec", "source_kind": "official"},
        {"spdx": "Apache-2.0", "derivation_allowed": True},
    )


def test_store_returns_opaque_content_addressed_metadata_without_raw_content(tmp_path) -> None:
    vault = EvidenceVault(tmp_path / "vault.sqlite3")
    provenance, license_data = metadata()

    result = vault.store(
        tenant_id="tenant-a",
        intent_id="intent-a",
        content="safe specification",
        provenance=provenance,
        license=license_data,
    )

    assert result.evidence_ref == "evidence://sha256/" + hashlib.sha256(
        b"safe specification"
    ).hexdigest()
    assert result.byte_length == len(b"safe specification")
    assert "content" not in asdict(result)
    assert vault.get_metadata(
        tenant_id="tenant-a", intent_id="intent-a", evidence_ref=result.evidence_ref
    ) == result


def test_duplicate_is_idempotent_but_metadata_change_is_immutable_conflict(tmp_path) -> None:
    vault = EvidenceVault(tmp_path / "vault.sqlite3")
    provenance, license_data = metadata()
    arguments = {
        "tenant_id": "tenant-a",
        "intent_id": "intent-a",
        "content": "safe evidence",
        "provenance": provenance,
        "license": license_data,
    }

    first = vault.store(**arguments)
    assert vault.store(**arguments) == first

    with pytest.raises(EvidenceConflictError, match="EVIDENCE_IMMUTABLE_CONFLICT"):
        vault.store(**{**arguments, "license": {"spdx": "MIT"}})


def test_safety_scan_happens_before_persistence(tmp_path) -> None:
    database = tmp_path / "vault.sqlite3"
    vault = EvidenceVault(database)
    provenance, license_data = metadata()

    with pytest.raises(LearningSafetyViolation) as caught:
        vault.store(
            tenant_id="tenant-a",
            intent_id="intent-a",
            content="api_key=dummyValue123456789",
            provenance=provenance,
            license=license_data,
        )

    assert caught.value.codes == ("SECRET_API_KEY",)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 0


def test_lookup_is_tenant_and_intent_scoped(tmp_path) -> None:
    vault = EvidenceVault(tmp_path / "vault.sqlite3")
    provenance, license_data = metadata()
    stored = vault.store(
        tenant_id="tenant-a",
        intent_id="intent-a",
        content="safe evidence",
        provenance=provenance,
        license=license_data,
    )

    with pytest.raises(EvidenceNotFoundError):
        vault.get_metadata(
            tenant_id="tenant-b", intent_id="intent-a", evidence_ref=stored.evidence_ref
        )


def test_integrity_verification_detects_tampering(tmp_path) -> None:
    database = tmp_path / "vault.sqlite3"
    vault = EvidenceVault(database)
    provenance, license_data = metadata()
    stored = vault.store(
        tenant_id="tenant-a",
        intent_id="intent-a",
        content="safe evidence",
        provenance=provenance,
        license=license_data,
    )
    assert vault.verify_integrity(
        tenant_id="tenant-a", intent_id="intent-a", evidence_ref=stored.evidence_ref
    )

    with sqlite3.connect(database) as connection:
        connection.execute("DROP TRIGGER evidence_no_update")
        connection.execute("UPDATE evidence SET content = ?", (b"tampered",))

    with pytest.raises(EvidenceIntegrityError, match="EVIDENCE_INTEGRITY_FAILED"):
        vault.verify_integrity(
            tenant_id="tenant-a", intent_id="intent-a", evidence_ref=stored.evidence_ref
        )


def test_database_enforces_append_only_and_binary_content_fails_closed(tmp_path) -> None:
    database = tmp_path / "vault.sqlite3"
    vault = EvidenceVault(database)
    provenance, license_data = metadata()
    vault.store(
        tenant_id="tenant-a",
        intent_id="intent-a",
        content="safe evidence",
        provenance=provenance,
        license=license_data,
    )

    with sqlite3.connect(database) as connection, pytest.raises(
        sqlite3.IntegrityError, match="EVIDENCE_APPEND_ONLY"
    ):
        connection.execute("DELETE FROM evidence")

    with pytest.raises(EvidenceVaultError, match="EVIDENCE_CONTENT_NOT_UTF8"):
        vault.store(
            tenant_id="tenant-a",
            intent_id="intent-a",
            content=b"\xff\xfe",
            provenance=provenance,
            license=license_data,
        )
