"""Build a static Netlify home and, when configured, a same-origin API proxy."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "netlify-site"
TARGET = ROOT / "dist"


def backend_origin(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
            or parsed.hostname in {"localhost", "127.0.0.1"}):
        raise ValueError("ARKAON_API_ORIGIN must be a credential-free HTTPS origin")
    return f"https://{parsed.netloc.rstrip('/')}"


def build() -> None:
    if TARGET.exists():
        shutil.rmtree(TARGET)
    shutil.copytree(SOURCE, TARGET)
    origin = os.environ.get("ARKAON_API_ORIGIN", "").strip()
    if origin:
        origin = backend_origin(origin)
        (TARGET / "_redirects").write_text(
            f"/inspection/* {origin}/inspection/:splat 200\n", encoding="utf-8"
        )
    else:
        (TARGET / "_redirects").write_text("", encoding="utf-8")
    (TARGET / "api-config.json").write_text(
        '{"inspection_available":' + ("true" if origin else "false") + "}\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    build()
