"""Deployable personal page surface, with local persistent storage.

Requires a persistent volume for APF_NAME_AT_DATA and HTTPS at the proxy.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import subprocess
from html import escape
from pathlib import Path
from urllib.parse import quote, urlsplit
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field

from .name_at import Media, NameAtRegistry, ProfileError
from .name_at_discovery import Submission, submit_google_sitemap, submit_indexnow


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=60, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=256)


class ProfileInput(BaseModel):
    display_name: str
    introduction: str
    image_ids: list[str] = Field(default_factory=list, max_length=3)
    video_id: str | None = None
    image_descriptions: list[str] = Field(default_factory=list)
    video_description: str | None = None
    intent_dna_ref: str | None = None
    profile_id: str | None = None
    expected_revision: int | None = None


class PublishInput(BaseModel):
    expected_revision: int
    approved_digest: str


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        '<!doctype html><html lang="ko"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{escape(title)}</title><meta name="description" content="{escape(title)}">'
        '<style>body{font:1.05rem/1.65 system-ui,sans-serif;max-width:780px;margin:auto;'
        'padding:2rem;color:#15253b;background:#f7f9fc}main{background:#fff;padding:2rem;'
        'border-radius:1rem}a{color:#174caa}img,video{max-width:100%;height:auto}'
        'input,textarea,button{font:inherit;max-width:100%}</style>'
        f'<main>{body}</main></html>',
        headers={"Content-Security-Policy": "default-src 'none'; img-src 'self'; media-src 'self'; "
                 "style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'",
                 "X-Content-Type-Options": "nosniff"},
    )


def _sniff(data: bytes) -> tuple[str, str, int] | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ("image/png", ".png", 8 * 1024 * 1024)
    if data.startswith(b"\xff\xd8\xff"):
        return ("image/jpeg", ".jpg", 8 * 1024 * 1024)
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ("image/webp", ".webp", 8 * 1024 * 1024)
    if data[4:8] == b"ftyp" and data[8:12] in (b"isom", b"iso2", b"mp41", b"mp42", b"avc1"):
        return ("video/mp4", ".mp4", 50 * 1024 * 1024)
    if data.startswith(b"\x1aE\xdf\xa3"):
        return ("video/webm", ".webm", 50 * 1024 * 1024)
    return None


def _validate_media(path: Path, mime: str) -> None:
    if mime.startswith("image/"):
        try:
            with Image.open(path) as picture:
                picture.verify()
            with Image.open(path) as picture:
                if picture.width * picture.height > 20_000_000:
                    raise HTTPException(415, "image dimensions too large")
                normalized = ImageOps.exif_transpose(picture)
                fmt = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}[mime]
                normalized.save(path.with_suffix(".normalized"), format=fmt)
                path.with_suffix(".normalized").replace(path)
                if path.stat().st_size > 8 * 1024 * 1024:
                    raise HTTPException(415, "normalized image too large")
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise HTTPException(415, "invalid image") from exc
        return
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "stream=codec_type,codec_name,width,height:format=duration", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=12, check=True,
        )
        metadata = json.loads(result.stdout)
        videos = [stream for stream in metadata.get("streams", []) if stream.get("codec_type") == "video"]
        allowed = {"video/mp4": {"h264"}, "video/webm": {"vp8", "vp9", "av1"}}
        if (len(videos) != 1 or videos[0].get("codec_name") not in allowed[mime]
                or int(videos[0].get("width", 0)) * int(videos[0].get("height", 0)) > 1920 * 1080
                or not 0 < float(metadata["format"]["duration"]) <= 180):
            raise ValueError("unsupported video stream")
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(415, "invalid video") from exc


def install_name_at(app: FastAPI, *, root: Path, origin: str, secret: str) -> None:
    if len(secret) < 32:
        raise RuntimeError("APF_NAME_AT_SECRET must contain at least 32 characters")
    root.mkdir(parents=True, exist_ok=True)
    db_path = root / "name-at.sqlite3"
    files = root / "media"
    files.mkdir(exist_ok=True)
    registry = NameAtRegistry(db_path, origin=origin, media_host=urlsplit(origin).hostname or "")
    with sqlite3.connect(db_path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS name_at_accounts (id TEXT PRIMARY KEY, "
                   "username TEXT UNIQUE NOT NULL, salt BLOB NOT NULL, hash BLOB NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS name_at_sessions (token_hash TEXT PRIMARY KEY, "
                   "account_id TEXT NOT NULL, csrf TEXT NOT NULL, expires INTEGER NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS name_at_login_attempts (username TEXT PRIMARY KEY, "
                   "failures INTEGER NOT NULL, window_start INTEGER NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS name_at_media (id TEXT PRIMARY KEY, "
                   "owner_id TEXT NOT NULL, filename TEXT NOT NULL, mime TEXT NOT NULL, "
                   "kind TEXT NOT NULL, size INTEGER NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS name_at_submissions (profile_id TEXT NOT NULL, "
                   "engine TEXT NOT NULL, status TEXT NOT NULL, detail TEXT NOT NULL, "
                   "updated_at TEXT NOT NULL, PRIMARY KEY(profile_id,engine))")
    tenant = "name-at"

    def token_hash(token: str) -> str:
        return hmac.new(secret.encode(), token.encode(), hashlib.sha256).hexdigest()

    def connect() -> sqlite3.Connection:
        db = sqlite3.connect(db_path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def owner(request: Request, *, mutate: bool = False) -> str:
        import time
        token = request.cookies.get("name_at_session", "")
        if not token:
            raise HTTPException(401, "login required")
        with connect() as db:
            row = db.execute("SELECT account_id, csrf, expires FROM name_at_sessions "
                             "WHERE token_hash=?", (token_hash(token),)).fetchone()
        if row is None or row["expires"] < time.time():
            raise HTTPException(401, "session expired")
        if mutate and not hmac.compare_digest(row["csrf"], request.headers.get("X-CSRF-Token", "")):
            raise HTTPException(403, "CSRF verification failed")
        return str(row["account_id"])

    def owned_media(ids: list[str], account: str, kind: str) -> list[Media]:
        if len(set(ids)) != len(ids):
            raise HTTPException(422, "duplicate media")
        result = []
        with connect() as db:
            for asset_id in ids:
                try:
                    UUID(asset_id)
                except ValueError:
                    raise HTTPException(422, "invalid media id") from None
                row = db.execute("SELECT * FROM name_at_media WHERE id=? AND owner_id=? AND kind=?",
                                 (asset_id, account, kind)).fetchone()
                if row is None:
                    raise HTTPException(403, "media ownership required")
                result.append(Media(f"{origin}/name-at/media/{asset_id}", ""))
        return result

    def submit(profile_id: str) -> list[dict]:
        from datetime import UTC, datetime
        key = os.getenv("APF_NAME_AT_INDEXNOW_KEY", "")
        results: list[Submission] = []
        with registry._connect() as db:
            row = db.execute("SELECT display_name FROM name_at_profiles WHERE id=?",
                             (profile_id,)).fetchone()
        hub_url = f"{origin}/at/{quote(row['display_name'], safe='')}" if row else None
        if key:
            try:
                results.extend(submit_indexnow(origin=origin, page_url=f"{origin}/p/{profile_id}",
                                               related_urls=(hub_url,) if hub_url else (), key=key))
            except ValueError:
                results.extend([Submission(engine, "failed", "invalid IndexNow configuration")
                                for engine in ("naver", "bing")])
        else:
            results.extend([Submission(engine, "setup_required", "IndexNow key missing")
                            for engine in ("naver", "bing")])
        credentials_file = os.getenv("APF_NAME_AT_GOOGLE_CREDENTIALS_FILE")
        credentials_json = os.getenv("APF_NAME_AT_GOOGLE_SERVICE_ACCOUNT_JSON")
        if credentials_file or credentials_json:
            try:
                results.append(submit_google_sitemap(origin=origin,
                    credentials_file=credentials_file,
                    credentials_json=credentials_json,
                    property_url=os.getenv("APF_NAME_AT_GOOGLE_PROPERTY")))
            except (OSError, ValueError, RuntimeError) as exc:
                results.append(Submission("google", "failed", type(exc).__name__))
        else:
            results.append(Submission("google", "setup_required", "Search Console access missing"))
        results.append(Submission("daum", "manual_review", "platform site registration required"))
        with connect() as db:
            db.executemany("""INSERT INTO name_at_submissions VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(profile_id,engine) DO UPDATE SET status=excluded.status,
                detail=excluded.detail,updated_at=excluded.updated_at""",
                [(profile_id, r.engine, r.status, r.detail, datetime.now(UTC).isoformat())
                 for r in results])
        return [vars(r) for r in results]

    @app.post("/name-at/register")
    def register(payload: Credentials) -> dict:
        salt = os.urandom(16)
        digest = hashlib.scrypt(payload.password.encode(), salt=salt, n=2**14, r=8, p=1)
        with connect() as db:
            try:
                db.execute("INSERT INTO name_at_accounts VALUES (?, ?, ?, ?)",
                           (str(uuid4()), payload.username.casefold(), salt, digest))
            except sqlite3.IntegrityError:
                raise HTTPException(409, "username unavailable") from None
        return {"status": "registered"}

    @app.post("/name-at/login")
    def login(payload: Credentials, response: Response) -> dict:
        import time
        now = int(time.time())
        with connect() as db:
            attempt = db.execute("SELECT failures, window_start FROM name_at_login_attempts "
                                 "WHERE username=?", (payload.username.casefold(),)).fetchone()
            if attempt and now - attempt["window_start"] < 900 and attempt["failures"] >= 5:
                raise HTTPException(429, "try again later")
            row = db.execute("SELECT * FROM name_at_accounts WHERE username=?",
                             (payload.username.casefold(),)).fetchone()
        salt = row["salt"] if row else b"\0" * 16
        actual = hashlib.scrypt(payload.password.encode(), salt=salt, n=2**14, r=8, p=1)
        if row is None or not hmac.compare_digest(actual, row["hash"]):
            with connect() as db:
                failures = (attempt["failures"] + 1 if attempt and now - attempt["window_start"] < 900 else 1)
                start = attempt["window_start"] if attempt and now - attempt["window_start"] < 900 else now
                db.execute("INSERT INTO name_at_login_attempts VALUES (?, ?, ?) ON CONFLICT(username) "
                           "DO UPDATE SET failures=excluded.failures,window_start=excluded.window_start",
                           (payload.username.casefold(), failures, start))
            raise HTTPException(401, "invalid credentials")
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with connect() as db:
            db.execute("DELETE FROM name_at_login_attempts WHERE username=?", (payload.username.casefold(),))
            db.execute("INSERT INTO name_at_sessions VALUES (?, ?, ?, ?)",
                       (token_hash(token), row["id"], csrf,
                        int(time.time()) + 86400))
        response.set_cookie("name_at_session", token, httponly=True, secure=True,
                            samesite="strict", max_age=86400)
        return {"csrf_token": csrf}

    @app.post("/name-at/logout")
    def logout(request: Request, response: Response) -> dict:
        owner(request, mutate=True)
        token = request.cookies.get("name_at_session", "")
        with connect() as db:
            db.execute("DELETE FROM name_at_sessions WHERE token_hash=?",
                       (token_hash(token),))
        response.delete_cookie("name_at_session")
        return {"status": "logged out"}

    @app.get("/name-at/session")
    def session(request: Request) -> dict:
        account = owner(request)
        token = request.cookies.get("name_at_session", "")
        with connect() as db:
            row = db.execute("SELECT csrf FROM name_at_sessions WHERE token_hash=? AND account_id=?",
                             (token_hash(token), account)).fetchone()
        if row is None:
            raise HTTPException(401, "session expired")
        return {"csrf_token": row["csrf"]}

    @app.post("/name-at/media")
    async def upload(request: Request) -> dict:
        account = owner(request, mutate=True)
        with connect() as db:
            usage = db.execute("SELECT COUNT(*) AS n, COALESCE(SUM(size),0) AS bytes "
                               "FROM name_at_media WHERE owner_id=?", (account,)).fetchone()
        if usage["n"] >= 30 or usage["bytes"] >= 250 * 1024 * 1024:
            raise HTTPException(429, "media quota reached")
        prefix = bytearray()
        asset_id = str(uuid4())
        tmp = files / f"{asset_id}.pending"
        size = 0
        try:
            with tmp.open("xb") as handle:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > 50 * 1024 * 1024:
                        raise HTTPException(413, "file too large")
                    if len(prefix) < 16:
                        prefix.extend(chunk[:16 - len(prefix)])
                    handle.write(chunk)
            detected = _sniff(bytes(prefix))
            if not detected or size > detected[2]:
                raise HTTPException(415, "unsupported or oversized media")
            mime, ext, _ = detected
            _validate_media(tmp, mime)
            size = tmp.stat().st_size
            final = f"{asset_id}{ext}"
            tmp.replace(files / final)
            with connect() as db:
                db.execute("INSERT INTO name_at_media VALUES (?, ?, ?, ?, ?, ?)",
                           (asset_id, account, final, mime,
                            "video" if mime.startswith("video/") else "image", size))
            return {"id": asset_id, "kind": "video" if mime.startswith("video/") else "image"}
        finally:
            tmp.unlink(missing_ok=True)

    @app.post("/name-at/profiles")
    def draft(payload: ProfileInput, request: Request) -> dict:
        account = owner(request, mutate=True)
        if payload.profile_id is None:
            with registry._connect() as db:
                count = db.execute("SELECT COUNT(*) FROM name_at_profiles WHERE owner_id=?",
                                   (account,)).fetchone()[0]
            if count >= 20:
                raise HTTPException(429, "profile quota reached")
        if len(payload.image_ids) != len(payload.image_descriptions):
            raise HTTPException(422, "image descriptions required")
        images = owned_media(payload.image_ids, account, "image")
        images = [Media(item.url, description) for item, description in
                  zip(images, payload.image_descriptions, strict=True)]
        video_items = owned_media([payload.video_id], account, "video") if payload.video_id else []
        video = (Media(video_items[0].url, payload.video_description or "")
                 if video_items else None)
        try:
            item = registry.save_draft(tenant_id=tenant, owner_id=account,
                                       display_name=payload.display_name,
                                       introduction=payload.introduction, images=images,
                                       video=video, intent_dna_ref=payload.intent_dna_ref,
                                       profile_id=payload.profile_id,
                                       expected_revision=payload.expected_revision)
        except ProfileError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"id": item["id"], "revision": item["revision"],
                "approval_digest": registry.digest(item), "state": "DRAFT"}

    @app.post("/name-at/profiles/{profile_id}/publish")
    def publish(profile_id: str, payload: PublishInput, request: Request) -> dict:
        account = owner(request, mutate=True)
        try:
            item = registry.publish(tenant_id=tenant, owner_id=account,
                                    profile_id=profile_id, expected_revision=payload.expected_revision,
                                    approved_digest=payload.approved_digest)
        except ProfileError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"url": f"{origin}/p/{profile_id}", "state": item["state"],
                "discovery": submit(profile_id)}

    @app.post("/name-at/profiles/{profile_id}/withdraw")
    def withdraw(profile_id: str, request: Request) -> dict:
        account = owner(request, mutate=True)
        try:
            registry.withdraw(tenant_id=tenant, owner_id=account, profile_id=profile_id)
        except ProfileError as exc:
            raise HTTPException(404, str(exc)) from exc
        return {"state": "WITHDRAWN", "discovery": submit(profile_id)}

    @app.get("/name-at/profiles/{profile_id}/discovery")
    def discovery(profile_id: str, request: Request) -> list[dict]:
        account = owner(request)
        try:
            registry.get(tenant_id=tenant, owner_id=account, profile_id=profile_id)
        except ProfileError as exc:
            raise HTTPException(404, str(exc)) from exc
        with connect() as db:
            rows = db.execute("SELECT engine,status,detail,updated_at FROM name_at_submissions "
                              "WHERE profile_id=? ORDER BY engine", (profile_id,)).fetchall()
        return [dict(row) for row in rows]

    @app.get("/name-at/media/{asset_id}")
    def media(asset_id: str, request: Request) -> FileResponse:
        try:
            UUID(asset_id)
        except ValueError:
            raise HTTPException(404, "not found") from None
        with connect() as db:
            row = db.execute("SELECT * FROM name_at_media WHERE id=?", (asset_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "not found")
        url = f"{origin}/name-at/media/{asset_id}"
        with registry._connect() as db:
            published = db.execute("""SELECT 1 FROM name_at_profiles WHERE state='PUBLISHED'
                AND (images_json LIKE ? OR video_json LIKE ?) LIMIT 1""",
                (f'%"url": "{url}"%', f'%"url": "{url}"%')).fetchone()
        if not published and owner(request) != row["owner_id"]:
            raise HTTPException(404, "not found")
        return FileResponse(files / row["filename"], media_type=row["mime"],
                            headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=60"})

    @app.get("/p/{profile_id}")
    def profile(profile_id: str) -> HTMLResponse:
        try:
            item = registry.public_profile(profile_id)
        except ProfileError:
            raise HTTPException(404, "not found") from None
        name = escape(item["display_name"])
        images = json.loads(item["images_json"])
        video = json.loads(item["video_json"]) if item["video_json"] else None
        media_html = "".join(f'<figure><img src="{escape(i["url"], quote=True)}" '
                             f'alt="{escape(i["description"], quote=True)}"></figure>' for i in images)
        if video:
            media_html += (f'<figure><video controls preload="metadata" src="{escape(video["url"], quote=True)}">'
                           f'{escape(video["description"])}</video><figcaption>{escape(video["description"])}</figcaption></figure>')
        canonical = f"{origin}/p/{profile_id}"
        structured = json.dumps({"@context": "https://schema.org", "@type": "ProfilePage",
                                 "mainEntity": {"@type": "Person", "name": item["display_name"]},
                                 "url": canonical}, ensure_ascii=False).replace("<", "\\u003c")
        page = _page(item["display_name"] + "@", f'<link rel="canonical" href="{escape(canonical)}">'
                     f'<h1>{name}@</h1><p>{escape(item["introduction"])}</p>{media_html}'
                     f'<script type="application/ld+json">{structured}</script>')
        page.headers["Content-Security-Policy"] += "; script-src 'unsafe-inline'"
        return page

    @app.get("/name-at/find")
    def find(q: str) -> HTMLResponse:
        try:
            results = registry.search(q)
        except ProfileError:
            raise HTTPException(422, "enter 이름@") from None
        items = "".join(f'<li><a href="{escape(i["url"], quote=True)}">'
                        f'{escape(i["display_name"])} — {escape(i["introduction"][:80])}</a></li>'
                        for i in results)
        return _page(q, f'<h1>{escape(q)}</h1><ul>{items}</ul>')

    @app.get("/at/{display_name}")
    def name_hub(display_name: str) -> HTMLResponse:
        try:
            results = registry.search(display_name + "@")
        except ProfileError:
            raise HTTPException(404, "not found") from None
        if not results:
            raise HTTPException(404, "not found")
        items = "".join(f'<li><a href="{escape(i["url"], quote=True)}">'
                        f'{escape(i["display_name"])} — {escape(i["introduction"][:120])}</a></li>'
                        for i in results)
        return _page(display_name + "@", f'<h1>{escape(display_name)}@</h1>'
                     f'<p>이 이름으로 게시한 {len(results)}개의 소개 페이지</p><ul>{items}</ul>')

    @app.get("/sitemap.xml")
    def sitemap() -> Response:
        return Response(registry.sitemap(), media_type="application/xml")

    @app.get("/robots.txt")
    def robots() -> PlainTextResponse:
        return PlainTextResponse(f"User-agent: *\nDisallow: /name-at/\nAllow: /p/\nAllow: /at/\nSitemap: {origin}/sitemap.xml\n")

    @app.get("/{key}.txt", include_in_schema=False)
    def indexnow_key(key: str) -> PlainTextResponse:
        configured = os.getenv("APF_NAME_AT_INDEXNOW_KEY", "")
        if not configured or not hmac.compare_digest(key, configured):
            raise HTTPException(404, "not found")
        return PlainTextResponse(configured)

    @app.get("/name-at")
    def homepage() -> HTMLResponse:
        page = HTMLResponse(Path(__file__).with_name("name_at_ui.html").read_text(encoding="utf-8"))
        page.headers["Content-Security-Policy"] = ("default-src 'none'; style-src 'unsafe-inline'; "
            "script-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
        page.headers["X-Content-Type-Options"] = "nosniff"
        return page
