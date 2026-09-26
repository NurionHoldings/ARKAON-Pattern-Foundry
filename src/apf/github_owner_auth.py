"""Owner-only GitHub OAuth sign-in for the Railway console.

The provider token is used once to verify the GitHub numeric user ID and is never
stored. GitHub OAuth credentials and the allowed ID are runtime settings.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode, urlsplit
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx


class OwnerAuthError(ValueError):
    pass


@dataclass(frozen=True)
class OwnerIdentity:
    tenant_id: UUID
    principal_id: UUID


class GitHubOwnerAuth:
    def __init__(
        self, *, client_id: str, client_secret: str, owner_id: int,
        tenant_id: str, public_base_url: str, signing_secret: str,
    ) -> None:
        url = urlsplit(public_base_url)
        if (url.scheme != "https" or not url.hostname or url.username or url.password
                or url.path not in ("", "/") or url.query or url.fragment):
            raise OwnerAuthError("OWNER_AUTH_PUBLIC_URL_INVALID")
        if not client_id or not client_secret or owner_id <= 0 or len(signing_secret) < 32:
            raise OwnerAuthError("OWNER_AUTH_CONFIG_INVALID")
        self.client_id = client_id
        self.client_secret = client_secret
        self.owner_id = owner_id
        self.tenant_id = UUID(tenant_id)
        self.base_url = public_base_url.rstrip("/")
        self.secret = signing_secret.encode()

    @classmethod
    def from_environment(cls) -> GitHubOwnerAuth | None:
        names = (
            "APF_GITHUB_OAUTH_CLIENT_ID", "APF_GITHUB_OAUTH_CLIENT_SECRET",
            "APF_GITHUB_OWNER_ID", "APF_TENANT_ID", "APF_PUBLIC_BASE_URL",
            "APF_CONSOLE_SESSION_SECRET",
        )
        values = [os.getenv(name) for name in names]
        if not any(values[:5]):
            return None
        if not all(values):
            raise OwnerAuthError("OWNER_AUTH_CONFIG_INCOMPLETE")
        return cls(
            client_id=values[0], client_secret=values[1], owner_id=int(values[2]),
            tenant_id=values[3], public_base_url=values[4], signing_secret=values[5],
        )

    def start(self) -> tuple[str, str]:
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(48)
        issued_at = int(time.time())
        payload = json.dumps(
            {"state": state, "verifier": verifier, "issued_at": issued_at},
            sort_keys=True, separators=(",", ":"),
        ).encode()
        body = base64.urlsafe_b64encode(payload).decode().rstrip("=")
        signature = hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        params = urlencode({
            "client_id": self.client_id, "redirect_uri": self.base_url + "/console/auth/callback",
            "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
            "allow_signup": "false",
        })
        return "https://github.com/login/oauth/authorize?" + params, body + "." + signature

    def _verifier(self, cookie: str | None, state: str) -> str:
        if not cookie or "." not in cookie:
            raise OwnerAuthError("OWNER_AUTH_STATE_INVALID")
        body, signature = cookie.rsplit(".", 1)
        expected = hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise OwnerAuthError("OWNER_AUTH_STATE_INVALID")
        try:
            payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
            issued_at = payload["issued_at"]
            if (not isinstance(issued_at, int) or not issued_at <= time.time() < issued_at + 300
                    or not hmac.compare_digest(payload["state"], state)):
                raise ValueError
            return payload["verifier"]
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise OwnerAuthError("OWNER_AUTH_STATE_INVALID") from exc

    def verify_callback(self, *, code: str, state: str, cookie: str | None) -> OwnerIdentity:
        if not code or len(code) > 512 or not state or len(state) > 256:
            raise OwnerAuthError("OWNER_AUTH_CALLBACK_INVALID")
        verifier = self._verifier(cookie, state)
        try:
            with httpx.Client(timeout=8.0, follow_redirects=False) as client:
                token_response = client.post(
                    "https://github.com/login/oauth/access_token",
                    headers={"Accept": "application/json"},
                    data={
                        "client_id": self.client_id, "client_secret": self.client_secret,
                        "code": code, "redirect_uri": self.base_url + "/console/auth/callback",
                        "code_verifier": verifier,
                    },
                )
                token_response.raise_for_status()
                token = token_response.json().get("access_token")
                if not isinstance(token, str) or not token:
                    raise OwnerAuthError("OWNER_AUTH_TOKEN_INVALID")
                user_response = client.get(
                    "https://api.github.com/user",
                    headers={
                        "Accept": "application/vnd.github+json",
                        "Authorization": "Bearer " + token,
                    },
                )
                user_response.raise_for_status()
                user_id = user_response.json().get("id")
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise OwnerAuthError("OWNER_AUTH_PROVIDER_FAILED") from exc
        if type(user_id) is not int or user_id != self.owner_id:
            raise OwnerAuthError("OWNER_AUTH_NOT_ALLOWED")
        return OwnerIdentity(
            tenant_id=self.tenant_id,
            principal_id=uuid5(NAMESPACE_URL, "https://github.com/user/" + str(user_id)),
        )
