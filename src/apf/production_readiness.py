"""Read-only operational checks for a deployed owner console.

This endpoint does not create schema, tenants, files or credentials. An operator
must run migrations and provision the tenant as separate reviewed actions.
"""

from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .github_owner_auth import GitHubOwnerAuth, OwnerAuthError
from .migrations import migration_versions
from .repository import PostgresRepository


def production_ready(repository: object) -> bool:
    if os.getenv("APF_ENV", "").lower() not in {"production", "prod"}:
        return True
    if not isinstance(repository, PostgresRepository):
        return False
    try:
        if GitHubOwnerAuth.from_environment() is None:
            return False
        tenant_id = UUID(os.environ["APF_TENANT_ID"])
        runtime = Path(os.environ["APF_RUNTIME_ROOT"]).resolve()
        foundry = Path(os.environ["APF_FOUNDRY_ROOT"]).resolve()
        # The app's private artifacts must share the mounted persistent volume.
        if not Path("/data").is_mount() or not all(
            path.is_relative_to(Path("/data")) for path in (runtime, foundry)
        ):
            return False
        if not runtime.is_dir() or not foundry.is_dir():
            return False
        with repository._engine.connect() as connection:
            versions = {row[0] for row in connection.execute(text("SELECT version FROM schema_migrations"))}
            if not set(migration_versions()).issubset(versions):
                return False
            owner = connection.execute(
                text("SELECT 1 FROM tenants WHERE id = :id"), {"id": str(tenant_id)}
            ).scalar_one_or_none()
            return owner == 1
    except (KeyError, OSError, ValueError, TypeError, OwnerAuthError, SQLAlchemyError):
        # This endpoint is public: no connection strings, paths or SQL errors.
        return False
