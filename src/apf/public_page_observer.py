"""Bounded static-page observation for registered public HTTPS design references.

This reads HTML and same-origin CSS only. It never executes scripts or captures a
rendered browser screenshot, and it stores only derived observations.
"""

from __future__ import annotations

import http.client
import ipaddress
import re
import socket
import ssl
import time
from hashlib import sha256
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from uuid import UUID

from .design_reference_urls import DesignReferenceError, canonical_public_url
from .design_style_proposal import PublicObservation

_HTML_LIMIT = 512 * 1024
_CSS_LIMIT = 256 * 1024
_HEX = re.compile(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\b")
_RGB = re.compile(r"\brgba?\(\s*(\d{1,3})\s*[, ]\s*(\d{1,3})\s*[, ]\s*(\d{1,3})", re.IGNORECASE)
_DECLARATION = re.compile(r"(?P<name>--[a-z-]+|[a-z-]+)\s*:\s*(?P<value>[^;{}]+)", re.IGNORECASE)
_GAP = re.compile(r"(?:gap|padding)\s*:\s*(\d{1,3})px", re.IGNORECASE)


class ObservationError(ValueError):
    pass


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host: str, address: str, timeout: float) -> None:
        super().__init__(host, port=443, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self) -> None:
        raw = socket.create_connection((self.address, 443), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


class PublicPageObserver:
    def __init__(self, *, timeout: float = 5.0) -> None:
        self.timeout = timeout

    def _resolve(self, host: str) -> str:
        try:
            answers = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            addresses = {item[4][0] for item in answers}
        except (OSError, socket.gaierror) as exc:
            raise ObservationError("DESIGN_CAPTURE_DNS_FAILED") from exc
        if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
            raise ObservationError("DESIGN_CAPTURE_NON_PUBLIC_ADDRESS")
        return min(addresses)

    def _get(self, url: str, *, limit: int, media_type: str) -> bytes:
        try:
            url = canonical_public_url(url)
        except DesignReferenceError as exc:
            raise ObservationError("DESIGN_CAPTURE_URL_INVALID") from exc
        deadline = time.monotonic() + 10
        parsed = urlsplit(url)
        host = parsed.hostname
        assert host is not None
        address = self._resolve(host)
        connection = _PinnedHTTPS(host, address, self.timeout)
        try:
            connection.request(
                "GET", parsed.path or "/",
                headers={"Accept": "text/html,text/css", "Accept-Encoding": "identity",
                         "User-Agent": "ARKAON-DesignObserver/1.0", "Connection": "close"},
            )
            response = connection.getresponse()
            if response.status != 200:
                raise ObservationError("DESIGN_CAPTURE_HTTP_STATUS")
            content_type = response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != media_type:
                raise ObservationError("DESIGN_CAPTURE_CONTENT_TYPE")
            if response.getheader("Content-Encoding", "identity").lower() != "identity":
                raise ObservationError("DESIGN_CAPTURE_ENCODING")
            length = response.getheader("Content-Length")
            if length and int(length) > limit:
                raise ObservationError("DESIGN_CAPTURE_TOO_LARGE")
            chunks = []
            size = 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ObservationError("DESIGN_CAPTURE_TIMEOUT")
                if connection.sock is not None:
                    connection.sock.settimeout(min(self.timeout, remaining))
                chunk = response.read(min(16384, limit + 1 - size))
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    raise ObservationError("DESIGN_CAPTURE_TOO_LARGE")
                chunks.append(chunk)
            return b"".join(chunks)
        except (OSError, ssl.SSLError, http.client.HTTPException, TimeoutError, ValueError) as exc:
            if isinstance(exc, ObservationError):
                raise
            raise ObservationError("DESIGN_CAPTURE_NETWORK_FAILED") from exc
        finally:
            connection.close()

    def observe(self, url: str, reference_id: UUID) -> dict[str, object]:
        page = self._get(url, limit=_HTML_LIMIT, media_type="text/html")
        try:
            html = page.decode("utf-8", errors="replace")
            parser = _StylesheetParser()
            parser.feed(html)
            parser.close()
            css_parts = parser.inline[:4]
            origin = urlsplit(url).hostname
            for href in parser.links[:3]:
                candidate = urljoin(url, href)
                try:
                    safe = canonical_public_url(candidate)
                except DesignReferenceError:
                    continue
                if urlsplit(safe).hostname != origin:
                    continue
                try:
                    css_parts.append(self._get(safe, limit=_CSS_LIMIT, media_type="text/css").decode(
                        "utf-8", errors="replace"
                    ))
                except ObservationError:
                    continue
            css = "\n".join(css_parts)[:_CSS_LIMIT]
            result = extract_observation(html, css, reference_id)
            result["source_digest"] = "sha256:" + sha256(page + css.encode()).hexdigest()
            result["source_kind"] = "STATIC_HTML_AND_SAME_ORIGIN_CSS"
            result["style_sheets_read"] = len(css_parts)
            return result
        except (UnicodeError, ValueError) as exc:
            raise ObservationError("DESIGN_CAPTURE_PARSE_FAILED") from exc


class _StylesheetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.inline: list[str] = []
        self._style = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = dict(attrs)
        if tag == "style":
            self._style = True
        if data.get("style") and len(data["style"]) <= 4096:
            self.inline.append(data["style"])
        if tag == "link" and "stylesheet" in (data.get("rel") or "").lower().split():
            href = data.get("href")
            if href and len(href) < 2048:
                self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "style":
            self._style = False

    def handle_data(self, data: str) -> None:
        if self._style and len(data) <= _CSS_LIMIT:
            self.inline.append(data)


def _color(value: str) -> str | None:
    match = _HEX.search(value)
    if not match:
        rgb = _RGB.search(value)
        if rgb:
            channels = [int(part) for part in rgb.groups()]
            if all(channel <= 255 for channel in channels):
                return "#" + "".join(f"{channel:02x}" for channel in channels)
        return None
    found = match.group().lower()
    if len(found) == 4:
        return "#" + "".join(ch * 2 for ch in found[1:])
    return found if len(found) == 7 else None


def extract_observation(html: str, css: str, reference_id: UUID) -> dict[str, object]:
    """Read bounded color and layout signals; no source CSS is returned."""
    if len(html) > _HTML_LIMIT or len(css) > _CSS_LIMIT:
        raise ObservationError("DESIGN_CAPTURE_TOO_LARGE")
    declarations = [(name.lower(), value) for name, value in _DECLARATION.findall(css)]
    colors = [(name, color) for name, raw in declarations if (color := _color(raw))]
    if not colors:
        raise ObservationError("DESIGN_CAPTURE_NO_STYLE_SIGNALS")
    backgrounds = [color for name, color in colors if name in {"background", "background-color", "--background", "--surface"}]
    foregrounds = [color for name, color in colors if name in {"color", "--text", "--foreground"}]
    accents = [color for name, color in colors if any(part in name for part in ("accent", "brand", "primary"))]
    background = backgrounds[0] if backgrounds else "#ffffff"
    ink = foregrounds[0] if foregrounds else "#1d3042"
    accent = accents[0] if accents else next((color for _, color in colors if color not in {background, ink}), "#087f70")
    layout = "cards" if re.search(r"(?:\.card|\.grid)[\w-]*\s*[{,]", css) else (
        "split" if "grid-template-columns" in css or "display:flex" in css.replace(" ", "") else "editorial"
    )
    gaps = [int(value) for value in _GAP.findall(css)]
    density = "compact" if gaps and min(gaps) <= 14 else "airy" if gaps and min(gaps) >= 30 else "balanced"
    observation = PublicObservation(
        reference_id=reference_id, background=background, text=ink, accent=accent,
        layout=layout, density=density,
        note="공개 정적 HTML/CSS에서 자동 관찰한 값입니다. 동적 화면은 포함되지 않습니다.",
    )
    return observation.model_dump(mode="json")
