from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine

_PACKAGED_MIGRATIONS = Path(__file__).resolve().parent / "sql_migrations"
MIGRATION_DIR = (
    _PACKAGED_MIGRATIONS
    if _PACKAGED_MIGRATIONS.exists()
    else Path(__file__).resolve().parents[2] / "db" / "migrations"
)


def migration_versions(directory: Path = MIGRATION_DIR) -> tuple[str, ...]:
    return tuple(sorted(path.name.removesuffix(".sql") for path in directory.glob("[0-9]*.sql")
                        if not path.name.endswith(".down.sql")))


def _execute_script(engine: Engine, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cursor:
            cursor.execute(sql)
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


def _ensure_ledger(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version varchar(200) PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )


def _applied(engine: Engine) -> set[str]:
    _ensure_ledger(engine)
    with engine.connect() as connection:
        return {row[0] for row in connection.exec_driver_sql("SELECT version FROM schema_migrations")}


def upgrade(engine: Engine, directory: Path = MIGRATION_DIR) -> tuple[str, ...]:
    applied: list[str] = []
    existing = _applied(engine)
    for version in migration_versions(directory):
        if version in existing:
            continue
        _execute_script(engine, directory / f"{version}.sql")
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO schema_migrations (version) VALUES (%s)", (version,)
            )
        applied.append(version)
    return tuple(applied)


def downgrade(engine: Engine, directory: Path = MIGRATION_DIR) -> tuple[str, ...]:
    reverted: list[str] = []
    versions = migration_versions(directory)
    for version in versions:
        if not (directory / f"{version}.down.sql").exists():
            raise RuntimeError(f"missing downgrade migration: {version}.down.sql")
    existing = _applied(engine)
    for version in reversed(versions):
        if version not in existing:
            continue
        path = directory / f"{version}.down.sql"
        _execute_script(engine, path)
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "DELETE FROM schema_migrations WHERE version=%s", (version,)
            )
        reverted.append(version)
    return tuple(reverted)
