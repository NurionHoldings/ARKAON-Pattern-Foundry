"""Secure GitHub account signup/login guidance for co-creation tenants."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlencode


class GitHubOnboardingRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class GitHubOnboardingPolicy:
    enabled: bool = True
    oauth_authorize_base: str = "https://github.com/login/oauth/authorize"
    signup_url: str = "https://github.com/signup"
    login_url: str = "https://github.com/login"
    callback_path: str = "/v1/console/github/oauth/callback"
    session_ttl_minutes: int = 30
    client_id_env: str = "ARKAON_GITHUB_OAUTH_CLIENT_ID"
    require_https_callback: bool = True

    @classmethod
    def load(cls, path: Path) -> GitHubOnboardingPolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.github-onboarding/v1":
            raise GitHubOnboardingRejected("POLICY_SCHEMA", "unsupported github onboarding schema")
        return cls(
            enabled=bool(document.get("enabled", True)),
            oauth_authorize_base=str(document.get("oauth_authorize_base", cls.oauth_authorize_base)),
            signup_url=str(document.get("signup_url", cls.signup_url)),
            login_url=str(document.get("login_url", cls.login_url)),
            callback_path=str(document.get("callback_path", cls.callback_path)),
            session_ttl_minutes=max(5, int(document.get("session_ttl_minutes", 30))),
            client_id_env=str(document.get("client_id_env", cls.client_id_env)),
            require_https_callback=bool(document.get("require_https_callback", True)),
        )


@dataclass(frozen=True)
class GitHubOnboardingGuide:
    session_id: str
    tenant_id: str
    principal_id: str
    platform_id: str
    signup_url: str
    login_url: str
    oauth_authorize_url: str
    secure_steps: tuple[str, ...]
    expires_at: datetime
    guide_digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.github-onboarding-guide/v1",
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "principal_id": self.principal_id,
            "platform_id": self.platform_id,
            "signup_url": self.signup_url,
            "login_url": self.login_url,
            "oauth_authorize_url": self.oauth_authorize_url,
            "secure_steps": list(self.secure_steps),
            "expires_at": self.expires_at.isoformat(),
            "guide_digest": self.guide_digest,
        }


class GitHubOnboardingEngine:
    def __init__(self, *, foundry_root: Path, policy: GitHubOnboardingPolicy | None = None) -> None:
        self.foundry_root = foundry_root.resolve()
        config = self.foundry_root / "config" / "arkaon-github-onboarding.json"
        self.policy = policy or GitHubOnboardingPolicy.load(config)
        self.store_root = self.foundry_root / "state" / "co-creation" / "github-onboarding"
        self.store_root.mkdir(parents=True, exist_ok=True)

    def start_guide(
        self,
        *,
        tenant_id: str,
        principal_id: str,
        platform_id: str,
        console_base_url: str,
        now: datetime,
        client_id: str | None = None,
    ) -> GitHubOnboardingGuide:
        if now.tzinfo is None:
            raise GitHubOnboardingRejected("TIMESTAMP", "timezone-aware timestamp required")
        if not self.policy.enabled:
            raise GitHubOnboardingRejected("DISABLED", "github onboarding is disabled")
        if self.policy.require_https_callback and not console_base_url.startswith("https://"):
            raise GitHubOnboardingRejected("CALLBACK_INSECURE", "console base URL must be HTTPS")
        resolved_client = client_id or ""
        state = secrets.token_urlsafe(24)
        callback = f"{console_base_url.rstrip('/')}{self.policy.callback_path}"
        oauth_url = self.policy.oauth_authorize_base
        if resolved_client:
            oauth_url = (
                f"{self.policy.oauth_authorize_base}?"
                + urlencode(
                    {
                        "client_id": resolved_client,
                        "redirect_uri": callback,
                        "scope": "read:user",
                        "state": state,
                    }
                )
            )
        session_id = sha256(f"{tenant_id}|{principal_id}|{now.isoformat()}|{state}".encode()).hexdigest()[:24]
        expires = now + timedelta(minutes=self.policy.session_ttl_minutes)
        steps = (
            "1. Use HTTPS only — never enter GitHub credentials on non-HTTPS pages.",
            f"2. If you have no GitHub account, open signup: {self.policy.signup_url}",
            f"3. If you already have an account, open login: {self.policy.login_url}",
            "4. After login, authorize ARKAON via OAuth (read:user scope only).",
            f"5. Complete OAuth callback at {callback} — state token binds this session.",
            "6. Do not share OAuth codes; ARKAON stores no GitHub password.",
        )
        digest = sha256(
            json.dumps(
                {"session_id": session_id, "tenant_id": tenant_id, "state": state},
                sort_keys=True,
            ).encode()
        ).hexdigest()
        guide = GitHubOnboardingGuide(
            session_id=session_id,
            tenant_id=tenant_id,
            principal_id=principal_id,
            platform_id=platform_id,
            signup_url=self.policy.signup_url,
            login_url=self.policy.login_url,
            oauth_authorize_url=oauth_url,
            secure_steps=steps,
            expires_at=expires,
            guide_digest=digest,
        )
        path = self.store_root / f"{session_id}.json"
        path.write_text(json.dumps(guide.to_document(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return guide
