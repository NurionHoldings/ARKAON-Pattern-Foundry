import base64
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from apf.durable_review import DurableReviewRepository
from apf.review_store_config import (
    console_review_store_from_config,
    is_production_environment,
    load_ethernian_review_public_key,
)


def _public_key_b64(private: Ed25519PrivateKey) -> str:
    return base64.urlsafe_b64encode(private.public_key().public_bytes_raw()).decode().rstrip("=")


def test_load_ethernian_review_public_key_prefers_environment(monkeypatch, tmp_path: Path):
    private = Ed25519PrivateKey.generate()
    monkeypatch.setenv("APF_ETERNIAN_REVIEW_PUBLIC_KEY_B64", _public_key_b64(private))
    policy = tmp_path / "config" / "arkaon-pattern-promotion.json"
    policy.parent.mkdir(parents=True)
    policy.write_text(json.dumps({"ethernian_public_key_b64": "invalid"}), encoding="utf-8")
    loaded = load_ethernian_review_public_key(foundry_root=tmp_path)
    assert loaded is not None
    assert loaded.public_bytes_raw() == private.public_key().public_bytes_raw()


def test_console_review_store_dev_sqlite_without_database_url(tmp_path: Path, monkeypatch):
    private = Ed25519PrivateKey.generate()
    policy = tmp_path / "config" / "arkaon-pattern-promotion.json"
    policy.parent.mkdir(parents=True)
    policy.write_text(json.dumps({"ethernian_public_key_b64": _public_key_b64(private)}), encoding="utf-8")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("APF_ENV", "development")
    store = console_review_store_from_config(foundry_root=tmp_path, database_url=None)
    assert isinstance(store, DurableReviewRepository)


def test_console_review_store_production_requires_database_url(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APF_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        console_review_store_from_config(foundry_root=tmp_path, database_url=None)


def test_create_app_production_requires_review_store(monkeypatch):
    monkeypatch.setenv("APF_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    monkeypatch.delenv("APF_ETERNIAN_REVIEW_PUBLIC_KEY_B64", raising=False)
    from apf import api

    with pytest.raises(RuntimeError, match="ethernian"):
        api.create_app()


def test_is_production_environment():
    assert is_production_environment("production")
    assert is_production_environment("prod")
    assert not is_production_environment("development")
