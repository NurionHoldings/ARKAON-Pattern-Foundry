import httpx
import pytest

from apf.name_at_discovery import submit_google_sitemap, submit_indexnow


def test_fixed_search_endpoints_and_received_is_not_indexed():
    targets = []

    def respond(request):
        targets.append(str(request.url))
        assert request.method == "POST"
        body = __import__("json").loads(request.content)
        assert body["urlList"] == ["https://profiles.example/p/123"]
        return httpx.Response(202)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = submit_indexnow(origin="https://profiles.example",
                                 page_url="https://profiles.example/p/123",
                                 key="abcdef1234567890", client=client)
    assert {item.engine for item in result} == {"naver", "bing"}
    assert all(item.status == "received" for item in result)
    assert targets == ["https://searchadvisor.naver.com/indexnow", "https://www.bing.com/indexnow"]


def test_foreign_url_cannot_be_submitted():
    with pytest.raises(ValueError):
        submit_indexnow(origin="https://profiles.example", page_url="https://evil.example/p/1",
                        key="abcdef1234567890")


def test_google_submission_uses_verified_property_and_sitemap(monkeypatch):
    from google.oauth2 import service_account

    class FakeCredentials:
        token = "test-token"

        def refresh(self, request):
            del request

    monkeypatch.setattr(service_account.Credentials, "from_service_account_info",
                        lambda info, scopes: FakeCredentials())

    def respond(request):
        assert request.method == "PUT"
        assert request.headers["Authorization"] == "Bearer test-token"
        assert "/sites/https%3A%2F%2Fprofiles.example%2F/sitemaps/" in str(request.url)
        assert str(request.url).endswith("https%3A%2F%2Fprofiles.example%2Fsitemap.xml")
        return httpx.Response(204)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = submit_google_sitemap(origin="https://profiles.example", credentials_json="{}",
                                       client=client)
    assert result.status == "received"
