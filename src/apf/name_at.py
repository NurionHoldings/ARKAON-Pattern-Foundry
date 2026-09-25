"""Isolated, owner-approved personal profile and search-discovery core.

This module intentionally does not expose an unauthenticated HTTP route or send
requests to a search engine. The host application owns authentication, media
storage, domain verification, and the network submission worker.
"""

from __future__ import annotations

import json
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from html import escape
from pathlib import Path
from urllib.parse import quote, urlsplit
from uuid import uuid4


class ProfileError(ValueError):
    pass


def name_key(name: str) -> str:
    value = unicodedata.normalize("NFC", name).strip()
    if not 2 <= len(value) <= 80 or any(ord(c) < 32 for c in value):
        raise ProfileError("INVALID_DISPLAY_NAME")
    if "@" in value:
        raise ProfileError("DISPLAY_NAME_MUST_NOT_CONTAIN_AT")
    return value.casefold()


def _public_url(value: str, *, host: str | None = None) -> str:
    url = urlsplit(value)
    try:
        port = url.port
    except ValueError as exc:
        raise ProfileError("PUBLIC_HTTPS_URL_REQUIRED") from exc
    if (url.scheme != "https" or not url.hostname or url.username or url.password
            or url.query or url.fragment or port not in (None, 443)):
        raise ProfileError("PUBLIC_HTTPS_URL_REQUIRED")
    if host and url.hostname != host:
        raise ProfileError("MEDIA_HOST_NOT_ALLOWED")
    return value


@dataclass(frozen=True)
class Media:
    url: str
    description: str


class NameAtRegistry:
    def __init__(self, database: Path, *, origin: str, media_host: str) -> None:
        self.database = database
        self.origin = _public_url(origin).rstrip("/")
        if urlsplit(self.origin).path not in ("", "/"):
            raise ProfileError("ORIGIN_MUST_BE_SITE_ROOT")
        self.media_host = media_host
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS name_at_profiles (
                id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, owner_id TEXT NOT NULL,
                display_name TEXT NOT NULL, name_key TEXT NOT NULL,
                introduction TEXT NOT NULL, images_json TEXT NOT NULL,
                video_json TEXT, intent_dna_ref TEXT, state TEXT NOT NULL,
                revision INTEGER NOT NULL, approved_digest TEXT, updated_at TEXT NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS ix_name_at_lookup ON name_at_profiles(name_key, state)")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def save_draft(self, *, tenant_id: str, owner_id: str, display_name: str,
                   introduction: str, images: list[Media], video: Media | None = None,
                   intent_dna_ref: str | None = None, profile_id: str | None = None,
                   expected_revision: int | None = None) -> dict:
        key = name_key(display_name)
        if not 1 <= len(introduction.strip()) <= 2000 or len(images) > 3:
            raise ProfileError("PROFILE_CONTENT_INVALID")
        if any(not item.description.strip() for item in images) or (
            video is not None and not video.description.strip()
        ):
            raise ProfileError("MEDIA_DESCRIPTION_REQUIRED")
        for item in [*images, *([video] if video else [])]:
            _public_url(item.url, host=self.media_host)
        payload = (display_name.strip(), key, introduction.strip(),
                   json.dumps([vars(i) for i in images], ensure_ascii=False),
                   json.dumps(vars(video), ensure_ascii=False) if video else None,
                   intent_dna_ref, datetime.now(UTC).isoformat())
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if profile_id is None:
                profile_id = str(uuid4())
                db.execute("""INSERT INTO name_at_profiles VALUES
                    (?, ?, ?, ?, ?, ?, ?, ?, ?, 'DRAFT', 1, NULL, ?)""",
                    (profile_id, tenant_id, owner_id, *payload))
            else:
                old = db.execute("SELECT * FROM name_at_profiles WHERE id=?", (profile_id,)).fetchone()
                if old is None or old["tenant_id"] != tenant_id or old["owner_id"] != owner_id:
                    raise ProfileError("PROFILE_NOT_FOUND")
                if old["revision"] != expected_revision:
                    raise ProfileError("REVISION_CONFLICT")
                db.execute("""UPDATE name_at_profiles SET display_name=?, name_key=?,
                    introduction=?, images_json=?, video_json=?, intent_dna_ref=?, updated_at=?,
                    state='DRAFT', revision=revision+1, approved_digest=NULL WHERE id=?""",
                    (*payload, profile_id))
        return self.get(tenant_id=tenant_id, owner_id=owner_id, profile_id=profile_id)

    def get(self, *, tenant_id: str, owner_id: str, profile_id: str) -> dict:
        with self._connect() as db:
            row = db.execute("SELECT * FROM name_at_profiles WHERE id=? AND tenant_id=? AND owner_id=?",
                             (profile_id, tenant_id, owner_id)).fetchone()
        if row is None:
            raise ProfileError("PROFILE_NOT_FOUND")
        return dict(row)

    @staticmethod
    def digest(row: dict) -> str:
        fields = ("id", "tenant_id", "owner_id", "display_name", "introduction",
                  "images_json", "video_json", "intent_dna_ref", "revision")
        raw = json.dumps({k: row[k] for k in fields}, sort_keys=True, ensure_ascii=False)
        return "sha256:" + sha256(raw.encode()).hexdigest()

    def publish(self, *, tenant_id: str, owner_id: str, profile_id: str,
                expected_revision: int, approved_digest: str) -> dict:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM name_at_profiles WHERE id=? AND tenant_id=? AND owner_id=?",
                             (profile_id, tenant_id, owner_id)).fetchone()
            if row is None:
                raise ProfileError("PROFILE_NOT_FOUND")
            if row["revision"] != expected_revision or row["state"] != "DRAFT":
                raise ProfileError("REVISION_CONFLICT")
            if self.digest(dict(row)) != approved_digest:
                raise ProfileError("APPROVAL_DIGEST_MISMATCH")
            db.execute("""UPDATE name_at_profiles SET state='PUBLISHED', approved_digest=?,
                updated_at=? WHERE id=?""",
                (approved_digest, datetime.now(UTC).isoformat(), profile_id))
        return self.get(tenant_id=tenant_id, owner_id=owner_id, profile_id=profile_id)

    def withdraw(self, *, tenant_id: str, owner_id: str, profile_id: str) -> None:
        with self._connect() as db:
            updated = db.execute("""UPDATE name_at_profiles SET state='WITHDRAWN',
                approved_digest=NULL, revision=revision+1, updated_at=?
                WHERE id=? AND tenant_id=? AND owner_id=?""",
                (datetime.now(UTC).isoformat(), profile_id, tenant_id, owner_id)).rowcount
        if not updated:
            raise ProfileError("PROFILE_NOT_FOUND")

    def search(self, query: str) -> list[dict]:
        if not query.endswith("@"):
            raise ProfileError("NAME_AT_QUERY_REQUIRED")
        key = name_key(query[:-1])
        with self._connect() as db:
            rows = db.execute("""SELECT id, display_name, introduction FROM name_at_profiles
                WHERE name_key=? AND state='PUBLISHED' ORDER BY id""", (key,)).fetchall()
        return [dict(row) | {"url": f"{self.origin}/p/{row['id']}"} for row in rows]

    def public_profile(self, profile_id: str) -> dict:
        with self._connect() as db:
            row = db.execute("SELECT * FROM name_at_profiles WHERE id=? AND state='PUBLISHED'",
                             (profile_id,)).fetchone()
        if row is None:
            raise ProfileError("PROFILE_NOT_FOUND")
        return dict(row)

    def sitemap(self) -> str:
        with self._connect() as db:
            rows = db.execute("SELECT id, updated_at FROM name_at_profiles WHERE state='PUBLISHED' ORDER BY id").fetchall()
            names = db.execute("SELECT DISTINCT display_name FROM name_at_profiles "
                               "WHERE state='PUBLISHED' ORDER BY display_name").fetchall()
        items = "".join(f"<url><loc>{escape(self.origin)}/p/{row['id']}</loc>"
                        f"<lastmod>{escape(row['updated_at'][:10])}</lastmod></url>" for row in rows)
        items += "".join(f"<url><loc>{escape(self.origin)}/at/"
                         f"{quote(row['display_name'], safe='')}</loc></url>" for row in names)
        return ('<?xml version="1.0" encoding="UTF-8"?>'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                f'{items}</urlset>')

    def discovery_jobs(self, profile_id: str) -> list[dict[str, str]]:
        with self._connect() as db:
            row = db.execute("SELECT state FROM name_at_profiles WHERE id=?", (profile_id,)).fetchone()
        if row is None:
            raise ProfileError("PROFILE_NOT_FOUND")
        url = f"{self.origin}/p/{profile_id}"
        action = "updated" if row["state"] == "PUBLISHED" else "deleted"
        return [
            {"engine": "naver", "method": "indexnow", "action": action, "url": url},
            {"engine": "bing", "method": "indexnow", "action": action, "url": url},
            {"engine": "google", "method": "sitemap", "action": action,
             "url": f"{self.origin}/sitemap.xml"},
            {"engine": "daum", "method": "site-registration-review", "action": "manual_review",
             "url": self.origin},
        ]
