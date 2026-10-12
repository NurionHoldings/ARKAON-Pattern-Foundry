"""Console durable review store wiring from environment and foundry config."""

from __future__ import annotations

import base64
import binascii
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy import create_engine

from .console import ConsoleReviewStore
from .durable_review import DurableReviewRepository
from .migrations import upgrade
from .postgres_durable_review import PostgresDurableReviewRepository


def is_production_environment(environment: str | None = None) -> bool:
    value = (environment or os.getenv("APF_ENV", "development")).lower()
    return value in {"production", "prod"}


def _foundry_root() -> Path:
    return Path(os.getenv("APF_FOUNDRY_ROOT", Path(__file__).parents[2]))


def normalize_postgres_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def load_ethernian_review_public_key(*, foundry_root: Path | None = None) -> Ed25519PublicKey | None:
    env_value = os.getenv("APF_ETERNIAN_REVIEW_PUBLIC_KEY_B64", "").strip()
    if env_value:
        return _decode_ed25519_public_key(env_value)
    root = foundry_root or _foundry_root()
    policy_path = root / "config" / "arkaon-pattern-promotion.json"
    if not policy_path.is_file():
        return None
    document = json.loads(policy_path.read_text(encoding="utf-8"))
    encoded = document.get("ethernian_public_key_b64")
    if not isinstance(encoded, str) or not encoded.strip():
        return None
    return _decode_ed25519_public_key(encoded.strip())


def _decode_ed25519_public_key(encoded: str) -> Ed25519PublicKey:
    try:
        padding = "=" * (-len(encoded) % 4)
        raw = base64.urlsafe_b64decode(encoded + padding)
        return Ed25519PublicKey.from_public_bytes(raw)
    except (binascii.Error, ValueError) as exc:
        raise RuntimeError("APF eternian review public key is invalid") from exc


def console_review_store_from_config(
    *,
    environment: str | None = None,
    database_url: str | None = None,
    foundry_root: Path | None = None,
) -> ConsoleReviewStore | None:
    """Return PostgreSQL or SQLite durable review store, or None when optional in development."""
    environment = (environment or os.getenv("APF_ENV", "development")).lower()
    database_url = database_url or os.getenv("DATABASE_URL")
    root = foundry_root or _foundry_root()
    public_key = load_ethernian_review_public_key(foundry_root=root)

    if database_url:
        if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
            raise RuntimeError("DATABASE_URL must use PostgreSQL for durable review")
        if public_key is None:
            if is_production_environment(environment):
                raise RuntimeError(
                    "APF_ETERNIAN_REVIEW_PUBLIC_KEY_B64 or config/arkaon-pattern-promotion.json "
                    "ethernian_public_key_b64 is required in production"
                )
            return None
        engine = create_engine(normalize_postgres_database_url(database_url), pool_pre_ping=True)
        upgrade(engine)
        return PostgresDurableReviewRepository(engine, ethernian_public_key=public_key)

    if is_production_environment(environment):
        raise RuntimeError("DATABASE_URL is required for durable review in production")

    if public_key is None:
        return None

    sqlite_path = root / "state" / "console-durable.sqlite"
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    return DurableReviewRepository(sqlite_path, ethernian_public_key=public_key)
