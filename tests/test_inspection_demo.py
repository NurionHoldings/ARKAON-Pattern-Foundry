from fastapi.testclient import TestClient

from apf.api import create_app
from apf.repository import MemoryRepository


def test_inspection_is_an_isolated_synthetic_session(monkeypatch):
    monkeypatch.setenv("APF_DEMO_INSPECTION_ID", "01000000000")
    monkeypatch.setenv("APF_DEMO_SESSION_SECRET", "a" * 40)
    client = TestClient(create_app(repository=MemoryRepository()), base_url="https://testserver")
    assert client.get("/inspection/workflow").status_code == 401
    assert client.post("/inspection/sign-in", data={
        "username": "01000000000", "pin": "12ab",
    }).status_code == 401
    assert client.post("/inspection/sign-in", data={
        "username": "01000000000", "pin": "0000",
    }, follow_redirects=False).status_code == 303
    page = client.get("/inspection/workflow")
    assert page.status_code == 200
    assert 'name="viewport"' in page.text
    assert all(step in page.text for step in ("요청", "시안 검토", "승인", "수령"))
    assert "예시 작업 흐름" in page.text
    assert client.get("/console").status_code == 401
    assert client.get("/v1/console/business-cards").status_code == 401


def test_inspection_disabled_without_separate_configuration(monkeypatch):
    monkeypatch.delenv("APF_DEMO_INSPECTION_ID", raising=False)
    monkeypatch.delenv("APF_DEMO_SESSION_SECRET", raising=False)
    client = TestClient(create_app(repository=MemoryRepository()))
    assert client.get("/inspection").status_code == 404
