"""Publish only public assets, with hashes for existing inline scripts."""
from __future__ import annotations

import base64
import hashlib
import shutil
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ScriptHashes(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.inline = False
        self.parts: list[str] = []
        self.hashes: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "script":
            self.inline = "src" not in dict(attrs)
            self.parts = []

    def handle_data(self, data: str) -> None:
        if self.inline:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self.inline:
            digest = hashlib.sha256("".join(self.parts).encode()).digest()
            self.hashes.add("'sha256-" + base64.b64encode(digest).decode() + "'")
            self.inline = False


def build(destination: Path) -> None:
    if destination.resolve() != (ROOT / "dist").resolve() or destination.is_symlink():
        raise ValueError("output must be the repository dist directory")
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir()
    shutil.copy2(ROOT / "index.html", destination / "index.html")
    for folder in ("assets", "services", "examples"):
        for source in (ROOT / folder).rglob("*"):
            if source.is_symlink():
                raise ValueError("symlinks cannot be published")
            if not source.is_file() or source.suffix.lower() not in {
                ".html", ".css", ".js", ".mp4", ".webm", ".svg", ".png", ".jpg", ".webp",
            }:
                continue
            target = destination / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    (destination / "config").mkdir()
    for name in ("arkaon-home-services.json", "arkaon-public-api.json"):
        shutil.copy2(ROOT / "config" / name, destination / "config" / name)
    headers = [
        "/*",
        "  X-Content-Type-Options: nosniff",
        "  X-Frame-Options: DENY",
        "  Referrer-Policy: strict-origin-when-cross-origin",
        "  Permissions-Policy: camera=(), microphone=(), geolocation=()",
        "  Strict-Transport-Security: max-age=31536000",
    ]
    for page in sorted(destination.rglob("*.html")):
        parser = ScriptHashes()
        parser.feed(page.read_text(encoding="utf-8"))
        if page.name == "entry-effects-studio.html":
            # The studio's sandboxed srcdoc uses this fixed repository script;
            # user text changes markup/styles, never this script body.
            parser.feed((ROOT / "src/apf/cinematic_gate.html").read_text(encoding="utf-8"))
        scripts = " ".join(sorted(parser.hashes))
        policy = (
            "default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; "
            f"script-src 'self' {scripts}; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "font-src 'self' data: https://cdn.jsdelivr.net; img-src 'self' data: blob: https:; "
            "media-src 'self' data: blob:; frame-src 'self' blob:; "
            "connect-src 'self' https: http://localhost:* http://127.0.0.1:*; form-action 'self'"
        )
        route = "/" + page.relative_to(destination).as_posix()
        routes = {route, route.removesuffix(".html"), route.removesuffix("index.html")}
        for pattern in sorted(routes):
            headers.extend([pattern, "  Content-Security-Policy: " + policy])
    (destination / "_headers").write_text("\n".join(headers) + "\n", encoding="utf-8")
    print(f"Static bundle: {sum(p.is_file() for p in destination.rglob('*'))} public files")


if __name__ == "__main__":
    build(ROOT / "dist")
