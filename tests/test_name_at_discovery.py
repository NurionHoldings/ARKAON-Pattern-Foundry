import httpx
import pytest

from apf.name_at_discovery import submit_indexnow


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
