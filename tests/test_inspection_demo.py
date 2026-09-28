from html.parser import HTMLParser

from fastapi.testclient import TestClient

from apf.api import create_app
from apf.repository import MemoryRepository


class TicketParser(HTMLParser):
    ticket = ""

    def handle_starttag(self, tag, attrs):
        if tag == "input" and dict(attrs).get("name") == "ticket":
            self.ticket = dict(attrs).get("value", "")


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
    assert "회원가입 또는 로그인이 필요합니다" in notice.text
    assert "회원가입·결제 연동이 준비되면" in notice.text
    assert client.get("/console").status_code == 401
    assert client.get("/v1/console/business-cards").status_code == 401
    visitor = TestClient(client.app, base_url="https://testserver")
    assert visitor.get("/inspection/preview").status_code == 401
    assert visitor.get("/inspection/participate").status_code == 401


def test_simple_logo_card_is_generated_but_release_requires_account_and_payment(monkeypatch):
    monkeypatch.setenv("APF_DEMO_INSPECTION_ID", "01000000000")
    monkeypatch.setenv("APF_DEMO_SESSION_SECRET", "b" * 40)
    client = TestClient(create_app(repository=MemoryRepository()), base_url="https://testserver")
    client.post("/inspection/sign-in", data={"username": "01000000000", "pin": "1234"})
    assert client.get("/inspection/make").status_code == 200
    preview = client.post("/inspection/make", data={
        "product": "both",
        "brand": "테스트", "tagline": "간단 소개", "color": "#2563eb", "shape": "orbit",
        "name": "홍길동", "title": "대표", "phone": "01000000000", "email": "a@example.com",
    })
    assert preview.status_code == 200
    assert preview.text.count("data:image/svg+xml;base64,") == 3
    assert "다운로드" in preview.text and "/download/" not in preview.text
    ticket = TicketParser()
    ticket.feed(preview.text)
    invoice = client.post("/inspection/invoice", data={"ticket": ticket.ticket,
                                                       "requested": "download"})
    assert invoice.status_code == 200
    assert "결제청구서 초안" in invoice.text
    assert "요청한 기능: 다운로드" in invoice.text
    assert "회원가입 또는 로그인 후 결제가 필요합니다" in invoice.text
    assert "로고: 50,000원" in invoice.text
    assert "명함: 10,000원" in invoice.text
    assert "표시 합계: 60,000원" in invoice.text
    assert client.post("/inspection/invoice", data={"ticket": ticket.ticket + "x",
                                                   "requested": "print"}).status_code == 403
    assert client.post("/inspection/make", data={
        "product": "both",
        "brand": "", "tagline": "x", "color": "red", "shape": "orbit",
        "name": "a", "title": "a", "phone": "a", "email": "a",
    }).status_code == 422
    for product, expected, image_count in (("logo", "50,000원", 1), ("card", "10,000원", 2)):
        separate = client.post("/inspection/make", data={
            "product": product, "brand": "테스트", "tagline": "소개", "color": "#2563eb",
            "shape": "arch", "name": "홍길동", "title": "대표", "phone": "010",
            "email": "a@example.com",
        })
        assert separate.status_code == 200
        assert separate.text.count("data:image/svg+xml;base64,") == image_count
        parser = TicketParser()
        parser.feed(separate.text)
        billed = client.post("/inspection/invoice", data={"ticket": parser.ticket,
                                                         "requested": "print"})
        assert billed.status_code == 200
        assert f"표시 합계: {expected}" in billed.text


def test_inspection_disabled_without_separate_configuration(monkeypatch):
    monkeypatch.delenv("APF_DEMO_INSPECTION_ID", raising=False)
    monkeypatch.delenv("APF_DEMO_SESSION_SECRET", raising=False)
    client = TestClient(create_app(repository=MemoryRepository()))
    assert client.get("/inspection").status_code == 404
