import pytest

from apf.api import repository_from_config
from apf.repository import MemoryRepository


def test_development_uses_memory_only_without_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert isinstance(repository_from_config(environment="development", database_url=None), MemoryRepository)


def test_production_fails_closed_without_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="required in production"):
        repository_from_config(environment="production", database_url=None)


def test_non_postgres_database_is_rejected():
    with pytest.raises(RuntimeError, match="must use PostgreSQL"):
        repository_from_config(environment="production", database_url="sqlite:///unsafe.db")
