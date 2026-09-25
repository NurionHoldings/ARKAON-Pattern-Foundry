"""Fixed-destination search submission for a verified platform domain."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

import httpx


@dataclass(frozen=True)
class Submission:
    engine: str
    status: str
    detail: str


def submit_indexnow(*, origin: str, page_url: str, key: str,
                    related_urls: tuple[str, ...] = (),
                    client: httpx.Client | None = None) -> list[Submission]:
    if not key or len(key) < 8 or len(key) > 128 or not key.isalnum():
        raise ValueError("invalid IndexNow key")
    for url in (page_url, *related_urls):
        if urlsplit(url).netloc != urlsplit(origin).netloc or not url.startswith(origin + "/"):
            raise ValueError("page is outside verified site")
    owns = client is None
    http = client or httpx.Client(timeout=5.0, follow_redirects=False)
    try:
        results = []
        for engine, endpoint in (("naver", "https://searchadvisor.naver.com/indexnow"),
                                 ("bing", "https://www.bing.com/indexnow")):
            try:
                response = http.post(endpoint, json={
                    "host": urlsplit(origin).hostname, "key": key,
                    "keyLocation": f"{origin}/{key}.txt", "urlList": [page_url, *related_urls],
                })
                results.append(Submission(engine, "received" if response.status_code in (200, 202)
                                          else "failed", f"HTTP {response.status_code}"))
            except httpx.HTTPError as exc:
                results.append(Submission(engine, "failed", type(exc).__name__))
        return results
    finally:
        if owns:
            http.close()


def submit_google_sitemap(*, origin: str, credentials_file: str | None = None,
                          credentials_json: str | None = None,
                          property_url: str | None = None,
                          client: httpx.Client | None = None) -> Submission:
    import google.auth.transport.requests
    from google.oauth2 import service_account

    site = property_url or origin + "/"
    if site != origin + "/" and site != "sc-domain:" + (urlsplit(origin).hostname or ""):
        raise ValueError("Search Console property does not match origin")
    if bool(credentials_file) == bool(credentials_json):
        raise ValueError("provide exactly one Google credential source")
    scope = ["https://www.googleapis.com/auth/webmasters"]
    credentials = (service_account.Credentials.from_service_account_file(credentials_file,
                   scopes=scope) if credentials_file else
                   service_account.Credentials.from_service_account_info(json.loads(credentials_json or ""),
                   scopes=scope))
    credentials.refresh(google.auth.transport.requests.Request())
    endpoint = ("https://www.googleapis.com/webmasters/v3/sites/" + quote(site, safe="")
                + "/sitemaps/" + quote(origin + "/sitemap.xml", safe=""))
    owns = client is None
    http = client or httpx.Client(timeout=8.0, follow_redirects=False)
    try:
        response = http.put(endpoint, headers={"Authorization": "Bearer " + credentials.token})
        return Submission("google", "received" if response.status_code in (200, 204)
                          else "failed", f"HTTP {response.status_code}")
    except httpx.HTTPError as exc:
        return Submission("google", "failed", type(exc).__name__)
    finally:
        if owns:
            http.close()
