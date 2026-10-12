from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlsplit
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
import requests

GOOGLE_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
TRANSACTION_COOKIE = "apf_google_oauth_tx"
TRANSACTION_TTL_SECONDS = 600
ALLOWED_ROLES = frozenset({"owner", "operator", "reviewer", "auditor"})


class GoogleIAMConfigurationError(ValueError):
    """Raised when Google Workspace sign-in is not configured safely."""


@dataclass(frozen=True)
class GoogleWorkspaceSettings:
    client_id: str
    client_secret: str
    redirect_uri: str
    public_origin: str
    hosted_domains: frozenset[str]
    principals_by_email: dict[str, dict[str, str]]

    @classmethod
    def from_environment(cls) -> GoogleWorkspaceSettings:
        client_id = os.getenv("APF_GOOGLE_OIDC_CLIENT_ID", "").strip()
        client_secret = os.getenv("APF_GOOGLE_OIDC_CLIENT_SECRET", "").strip()
        public_origin = os.getenv("APF_CONSOLE_PUBLIC_ORIGIN", "").strip()
        domain_value = os.getenv("APF_GOOGLE_WORKSPACE_DOMAINS", "")
        mapping_value = os.getenv("APF_IAM_PRINCIPAL_MAP_JSON", "")
        if not all((client_id, client_secret, public_origin, domain_value, mapping_value)):
            raise GoogleIAMConfigurationError("Google Workspace IAM is not configured")

        try:
            origin = urlsplit(public_origin)
        except ValueError:
            raise GoogleIAMConfigurationError("invalid console public origin") from None
        if (
            origin.scheme != "https"
            or not origin.hostname
            or origin.username
            or origin.password
            or origin.path not in ("", "/")
            or origin.query
            or origin.fragment
        ):
            raise GoogleIAMConfigurationError("console public origin must be an HTTPS origin")
        public_origin = f"https://{origin.netloc}"

        domains = frozenset(
            item.strip().lower().rstrip(".")
            for item in domain_value.split(",")
            if item.strip()
        )
        if not domains or any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", domain)
            or ".." in domain
            for domain in domains
        ):
            raise GoogleIAMConfigurationError("invalid Google Workspace domain allowlist")

        try:
            raw_mapping = json.loads(mapping_value)
        except json.JSONDecodeError:
            raise GoogleIAMConfigurationError("invalid IAM principal map") from None
        if not isinstance(raw_mapping, dict) or not raw_mapping:
            raise GoogleIAMConfigurationError("IAM principal map must be a non-empty object")

        principals: dict[str, dict[str, str]] = {}
        for raw_email, raw_entry in raw_mapping.items():
            email = raw_email.strip().lower() if isinstance(raw_email, str) else ""
            if (
                not email
                or "@" not in email
                or email.rsplit("@", 1)[1] not in domains
                or not isinstance(raw_entry, dict)
                or not {"tenant_id", "principal_id", "role"} <= set(raw_entry)
                or set(raw_entry) - {"tenant_id", "principal_id", "role", "google_sub"}
            ):
                raise GoogleIAMConfigurationError("invalid IAM principal map entry")
            try:
                UUID(raw_entry["tenant_id"])
                UUID(raw_entry["principal_id"])
            except (ValueError, TypeError, AttributeError):
                raise GoogleIAMConfigurationError("IAM principal IDs must be UUIDs") from None
            if raw_entry["role"] not in ALLOWED_ROLES:
                raise GoogleIAMConfigurationError("invalid IAM role")
            google_sub = raw_entry.get("google_sub", "")
            if google_sub and (not isinstance(google_sub, str) or len(google_sub) > 255):
                raise GoogleIAMConfigurationError("invalid Google subject binding")
            principals[email] = {
                "tenant_id": str(UUID(raw_entry["tenant_id"])),
                "principal_id": str(UUID(raw_entry["principal_id"])),
                "role": raw_entry["role"],
                "google_sub": google_sub,
            }

        return cls(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=f"{public_origin}/console/auth/callback",
            public_origin=public_origin,
            hosted_domains=domains,
            principals_by_email=principals,
        )


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _signed_transaction(value: dict[str, Any], secret: bytes) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return f"{_encode(body)}.{signature}"


def _read_transaction(token: str | None, secret: bytes) -> dict[str, Any] | None:
    if not token or "." not in token:
        return None
    encoded, signature = token.rsplit(".", 1)
    try:
        body = _decode(encoded)
        expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        value = json.loads(body)
        if not isinstance(value, dict) or int(value.get("expires_at", 0)) <= int(time.time()):
            return None
        return value
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def _security(request: Request):
    security = request.app.state.console_security
    if not security.secret:
        raise HTTPException(status_code=503, detail="console authentication unavailable")
    return security


def _settings() -> GoogleWorkspaceSettings:
    try:
        return GoogleWorkspaceSettings.from_environment()
    except GoogleIAMConfigurationError:
        raise HTTPException(status_code=503, detail="organization sign-in unavailable") from None


def install_google_workspace_iam(application, principal_type, session_cookie: str, csrf_cookie: str) -> None:
    router = APIRouter()

    @router.get("/console/login", response_class=HTMLResponse, include_in_schema=False)
    def login_page() -> HTMLResponse:
        return HTMLResponse(
            "<!doctype html><html lang=\"ko\"><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>ARKAON 로그인</title><main><h1>ARKAON 운영 콘솔</h1>"
            "<p>조직 계정으로 로그인하세요.</p>"
            "<a href=\"/console/auth/login\">Google Workspace로 로그인</a></main></html>",
            headers={
                "Cache-Control": "no-store",
                "Content-Security-Policy": (
                    "default-src 'none'; style-src 'unsafe-inline'; "
                    "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
                ),
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @router.get("/console/auth/login", include_in_schema=False)
    def begin_login(request: Request) -> Response:
        settings = _settings()
        security = _security(request)
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(48)
        challenge = _encode(hashlib.sha256(verifier.encode("ascii")).digest())
        transaction = _signed_transaction(
            {
                "state": state,
                "nonce": nonce,
                "verifier": verifier,
                "expires_at": int(time.time()) + TRANSACTION_TTL_SECONDS,
            },
            security.secret,
        )
        query = urlencode(
            {
                "client_id": settings.client_id,
                "redirect_uri": settings.redirect_uri,
                "response_type": "code",
                "scope": "openid email",
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "hd": next(iter(sorted(settings.hosted_domains))),
            }
        )
        response = RedirectResponse(
            f"{GOOGLE_AUTHORIZATION_ENDPOINT}?{query}", status_code=302
        )
        response.set_cookie(
            TRANSACTION_COOKIE,
            transaction,
            max_age=TRANSACTION_TTL_SECONDS,
            httponly=True,
            secure=True,
            samesite="lax",
            path="/console/auth/callback",
        )
        return response

    @router.get("/console/auth/callback", include_in_schema=False)
    def finish_login(request: Request, code: str | None = None, state: str | None = None) -> Response:
        settings = _settings()
        security = _security(request)
        transaction = _read_transaction(
            request.cookies.get(TRANSACTION_COOKIE), security.secret
        )
        if (
            transaction is None
            or not code
            or not state
            or not isinstance(transaction.get("state"), str)
            or not hmac.compare_digest(transaction["state"], state)
        ):
            raise HTTPException(status_code=400, detail="invalid sign-in response")

        try:
            token_response = requests.post(
                GOOGLE_TOKEN_ENDPOINT,
                data={
                    "code": code,
                    "client_id": settings.client_id,
                    "client_secret": settings.client_secret,
                    "redirect_uri": settings.redirect_uri,
                    "grant_type": "authorization_code",
                    "code_verifier": transaction["verifier"],
                },
                timeout=(3, 8),
            )
            if token_response.status_code != 200:
                raise ValueError("token exchange failed")
            token_body = token_response.json()
            encoded_id_token = token_body["id_token"]
            claims = id_token.verify_oauth2_token(
                encoded_id_token, GoogleRequest(), audience=settings.client_id
            )
        except (GoogleAuthError, requests.RequestException, ValueError, KeyError, TypeError):
            raise HTTPException(status_code=401, detail="organization sign-in failed") from None

        issuer = claims.get("iss")
        if issuer not in {"https://accounts.google.com", "accounts.google.com"}:
            raise HTTPException(status_code=401, detail="organization sign-in failed")
        if (
            not isinstance(claims.get("nonce"), str)
            or not hmac.compare_digest(claims["nonce"], transaction["nonce"])
            or claims.get("email_verified") is not True
            or not isinstance(claims.get("sub"), str)
            or not claims["sub"]
        ):
            raise HTTPException(status_code=401, detail="organization sign-in failed")

        hosted_domain = str(claims.get("hd", "")).lower()
        email = str(claims.get("email", "")).strip().lower()
        if hosted_domain not in settings.hosted_domains:
            raise HTTPException(status_code=403, detail="organization account required")
        principal_record = settings.principals_by_email.get(email)
        if principal_record is None:
            raise HTTPException(status_code=403, detail="account is not authorized")
        expected_sub = principal_record.get("google_sub")
        if expected_sub and not hmac.compare_digest(expected_sub, claims["sub"]):
            raise HTTPException(status_code=403, detail="account is not authorized")

        principal = principal_type(
            tenant_id=UUID(principal_record["tenant_id"]),
            principal_id=UUID(principal_record["principal_id"]),
            role=principal_record["role"],
        )
        response = RedirectResponse(
            f"{settings.public_origin}/console", status_code=303
        )
        response.set_cookie(
            session_cookie,
            security.issue(principal),
            httponly=True,
            secure=True,
            samesite="strict",
            path="/",
            max_age=3600,
        )
        response.set_cookie(
            csrf_cookie,
            secrets.token_urlsafe(32),
            httponly=False,
            secure=True,
            samesite="strict",
            path="/",
            max_age=3600,
        )
        response.delete_cookie(
            TRANSACTION_COOKIE,
            secure=True,
            httponly=True,
            samesite="lax",
            path="/console/auth/callback",
        )
        return response

    application.include_router(router)
