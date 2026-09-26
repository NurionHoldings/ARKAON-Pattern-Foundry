from pathlib import Path

import pytest

from apf.migrations import migration_versions


def test_every_upgrade_has_a_downgrade():
    directory = Path("db/migrations")
    versions = migration_versions(directory)
    assert versions == ("0001_core", "0002_target_repository", "0003_durable_review")
    assert all((directory / f"{version}.down.sql").exists() for version in versions)


def test_missing_downgrade_is_rejected(tmp_path):
    (tmp_path / "0001_example.sql").write_text("SELECT 1", encoding="utf-8")
    from apf.migrations import downgrade

    with pytest.raises(RuntimeError, match="missing downgrade"):
        downgrade(object(), tmp_path)
