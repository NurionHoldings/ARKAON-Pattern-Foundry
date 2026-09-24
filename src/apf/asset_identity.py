"""Stable, owner-bound intent/DNA identity for future artifact continuation."""

from __future__ import annotations

import json
from hashlib import sha256
from uuid import NAMESPACE_URL, UUID, uuid5


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + sha256(encoded).hexdigest()


def make_asset_identity(
    *, tenant_id: str, owner_principal_id: str, artifact_type: str,
    artifact_id: str, original_intent: object, dna: dict[str, object],
) -> dict[str, object]:
    """Keep original content out of reusable identity; bind DNA to one asset."""
    tenant = str(UUID(tenant_id))
    owner = str(UUID(owner_principal_id))
    asset = str(UUID(artifact_id))
    key = uuid5(NAMESPACE_URL, f"apf:asset:{tenant}:{owner}:{artifact_type}:{asset}")
    clean_dna = json.loads(json.dumps(dna, sort_keys=True, ensure_ascii=False))
    if not isinstance(clean_dna, dict):
        raise ValueError("asset DNA must be an object")
    return {
        "schema_version": "apf.asset-intent-dna/1.0",
        "asset_id": str(key),
        "artifact_type": artifact_type,
        "source_record_id": asset,
        "intent_digest": _digest(original_intent),
        "dna": clean_dna,
        "dna_digest": _digest(clean_dna),
        "source_revision": 1,
        "deployment_state": "NOT_CONNECTED",
    }
