"""Single-use preview approval for a bounded Railway resource change."""

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from pathlib import Path

from .railway_provider import RailwayClient, RailwayProviderError

NAME = re.compile(r"[a-z][a-z0-9-]{2,39}\Z")


def _secret() -> bytes:
    secret = os.environ.get("APF_RAILWAY_ACTION_SECRET", "")
    if len(secret) < 32:
        raise RailwayProviderError("Railway action signing is not configured")
    return secret.encode()


def _ledger() -> Path:
    root = os.environ.get("APF_RUNTIME_ROOT", "")
    if not root:
        raise RailwayProviderError("Persistent action ledger is not configured")
    path = Path(root)
    if not path.is_dir():
        raise RailwayProviderError("Persistent action ledger is unavailable")
    return path / "railway-actions.sqlite3"


def preview(client: RailwayClient, name: str, principal_id: str) -> dict:
    if not NAME.fullmatch(name):
        raise RailwayProviderError("Invalid Railway service name")
    snapshot = client.snapshot()
    if any(item["name"] == name for item in snapshot["services"]):
        raise RailwayProviderError("A service with this name already exists")
    _ledger()
    payload = {"project_id": client.project_id, "environment_id": client.environment_id,
               "name": name, "principal_id": principal_id, "nonce": secrets.token_hex(16),
               "expires_at": int(time.time()) + 300}
    body = base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True).encode()).decode()
    signature = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    return {"action": "CREATE_EMPTY_SERVICE", "project_name": snapshot["project_name"],
            "project_id": client.project_id, "environment_id": client.environment_id,
            "service_name": name, "cost_note": "Railway 자원 생성 후 과금 가능; 배포는 별도 작업",
            "expires_at": payload["expires_at"], "approval_token": body + "." + signature}


def execute(client: RailwayClient, approval_token: str, principal_id: str) -> dict:
    try:
        body, signature = approval_token.rsplit(".", 1)
        expected = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        payload = json.loads(base64.urlsafe_b64decode(body))
        if (payload["project_id"] != client.project_id or
            payload["environment_id"] != client.environment_id or
            payload["principal_id"] != principal_id or
            time.time() >= payload["expires_at"] or
            not NAME.fullmatch(payload["name"])):
            raise ValueError
    except (ValueError, KeyError, TypeError, binascii.Error):
        raise RailwayProviderError("Railway approval is invalid or expired") from None
    try:
        with sqlite3.connect(_ledger(), timeout=5) as db:
            db.execute("CREATE TABLE IF NOT EXISTS actions (nonce TEXT PRIMARY KEY, name TEXT NOT NULL)")
            db.execute("INSERT INTO actions(nonce, name) VALUES (?, ?)",
                       (payload["nonce"], payload["name"]))
            db.commit()
    except (sqlite3.Error, OSError):
        raise RailwayProviderError("Railway action already used or ledger unavailable") from None
    # A failed or ambiguous provider response consumes the nonce; recheck Railway before retrying.
    return client.create_empty_service(payload["name"])
