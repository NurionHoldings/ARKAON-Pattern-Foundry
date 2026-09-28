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
    assert "요청 미리보기" in page.text and "결과물 미리보기" in page.text
    preview = client.get("/inspection/preview")
    assert preview.status_code == 200
    assert all(item in preview.text for item in ("로고 시안", "모바일 명함", "소개 페이지 화면"))
    assert "파일 다운로드·인쇄·배포는 제공하지 않습니다" in preview.text
    notice = client.get("/inspection/participate")
    assert "회원가입 또는 로그인 후 결제 절차가 필요합니다" in notice.text
    assert "회원가입·결제 연동이 준비되면" in notice.text
    assert client.get("/console").status_code == 401
    assert client.get("/v1/console/business-cards").status_code == 401
    visitor = TestClient(client.app, base_url="https://testserver")
    assert visitor.get("/inspection/preview").status_code == 401
    assert visitor.get("/inspection/participate").status_code == 401


def test_inspection_disabled_without_separate_configuration(monkeypatch):
    monkeypatch.delenv("APF_DEMO_INSPECTION_ID", raising=False)
    monkeypatch.delenv("APF_DEMO_SESSION_SECRET", raising=False)
    client = TestClient(create_app(repository=MemoryRepository()))
    assert client.get("/inspection").status_code == 404
