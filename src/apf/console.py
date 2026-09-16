import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal, Protocol
from uuid import UUID

from fastapi import Cookie, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .durable_review import (
    DurableStoreError,
    ReviewAttestation,
    ReviewDecision,
    ReviewStage,
)
from .repository import TargetRepository

SESSION_COOKIE = "apf_console_session"
CSRF_COOKIE = "apf_console_csrf"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@dataclass(frozen=True)
class ConsolePrincipal:
    tenant_id: UUID
    principal_id: UUID
    role: Literal["operator", "reviewer", "auditor"]


class DevSessionRequest(BaseModel):
    tenant_id: UUID
    principal_id: UUID
    role: Literal["operator", "reviewer", "auditor"] = "operator"


class ReviewSubmission(BaseModel):
    task_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    task_id: UUID
    job_id: UUID
    request_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    tenant_id: UUID
    principal_id: UUID
    stage: ReviewStage
    evidence_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    decision: ReviewDecision
    expires_at: datetime
    nonce: UUID
    signature: str = Field(pattern=r"^[0-9a-f]{128}$")

    def attestation(self) -> ReviewAttestation:
        values = self.model_dump(mode="python")
        for key in ("task_id", "job_id", "tenant_id", "principal_id", "nonce"):
            values[key] = str(values[key])
        return ReviewAttestation(**values)


class ConsoleReviewStore(Protocol):
    def list_reviews_for_principal(
        self, tenant_id: str, principal_id: str, *, limit: int, offset: int,
    ): ...

    def list_candidate_manifests_for_principal(
        self, tenant_id: str, principal_id: str, *, limit: int, offset: int,
    ): ...

    def decide_review(
        self, tenant_id: str, task_id: str, attestation: ReviewAttestation,
    ): ...


class ConsoleSecurity:
    def __init__(
        self, *, environment: str, secret: str | None, allow_dev_sessions: bool = False
    ) -> None:
        self.environment = environment.lower()
        self.secret = secret.encode() if secret else None
        self.allow_dev_sessions = allow_dev_sessions and self.environment not in {"production", "prod"}
        if self.environment in {"production", "prod"} and not self.secret:
            raise RuntimeError("APF_CONSOLE_SESSION_SECRET is required in production")

    def _signature(self, body: bytes) -> str:
        if not self.secret:
            raise HTTPException(status_code=503, detail="console authentication unavailable")
        return hmac.new(self.secret, body, hashlib.sha256).hexdigest()

    def issue(self, principal: ConsolePrincipal) -> str:
        body = json.dumps(
            {
                "principal_id": str(principal.principal_id),
                "role": principal.role,
                "tenant_id": str(principal.tenant_id),
                "expires_at": int(time.time()) + 3600,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        encoded = base64.urlsafe_b64encode(body).decode().rstrip("=")
        return f"{encoded}.{self._signature(body)}"

    def verify(self, token: str | None) -> ConsolePrincipal:
        if not token or "." not in token:
            raise HTTPException(status_code=401, detail="console authentication required")
        encoded, signature = token.rsplit(".", 1)
        try:
            body = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            if not hmac.compare_digest(signature, self._signature(body)):
                raise ValueError
            value = json.loads(body)
            if not isinstance(value["expires_at"], int) or int(time.time()) >= value["expires_at"]:
                raise ValueError
            return ConsolePrincipal(
                tenant_id=UUID(value["tenant_id"]),
                principal_id=UUID(value["principal_id"]),
                role=value["role"],
            )
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            raise HTTPException(status_code=401, detail="invalid console session") from None


def install_console(
    application, *, security: ConsoleSecurity, review_store: ConsoleReviewStore | None = None,
) -> None:
    application.state.console_security = security
    application.state.console_review_store = review_store

    def principal(
        request: Request,
        session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    ) -> ConsolePrincipal:
        return request.app.state.console_security.verify(session)

    def csrf_guard(
        request: Request,
        csrf_cookie: Annotated[str | None, Cookie(alias=CSRF_COOKIE)] = None,
        csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> None:
        if request.method not in SAFE_METHODS and (
            not csrf_cookie or not csrf_header or not hmac.compare_digest(csrf_cookie, csrf_header)
        ):
            raise HTTPException(status_code=403, detail="CSRF verification failed")

    def repo(request: Request) -> TargetRepository:
        return request.app.state.repository

    def durable(request: Request) -> ConsoleReviewStore:
        store = request.app.state.console_review_store
        if store is None:
            raise HTTPException(status_code=503, detail="durable review store unavailable")
        return store

    def store_error(error: Exception) -> HTTPException:
        if isinstance(error, DurableStoreError):
            code = error.code
            if code in {"REVIEW_NOT_FOUND", "JOB_NOT_FOUND"}:
                return HTTPException(status_code=404, detail="review not found")
            if code in {"REVIEW_ALREADY_CLOSED", "REVIEW_NONCE_REPLAY"}:
                return HTTPException(status_code=409, detail=code)
            if code in {"REVIEW_EXPIRED", "REVIEW_ATTESTATION_EXPIRED"}:
                return HTTPException(status_code=422, detail=code)
            if code in {"REVIEW_BINDING_MISMATCH", "INVALID_REVIEW_SIGNATURE"}:
                return HTTPException(status_code=403, detail=code)
        return HTTPException(status_code=503, detail="durable review store unavailable")

    @application.post("/console/dev/session", include_in_schema=False)
    def create_dev_session(payload: DevSessionRequest, response: Response) -> dict[str, str]:
        if not security.allow_dev_sessions:
            raise HTTPException(status_code=404, detail="not found")
        token = security.issue(ConsolePrincipal(**payload.model_dump()))
        csrf = secrets.token_urlsafe(32)
        response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=True, samesite="strict")
        response.set_cookie(CSRF_COOKIE, csrf, httponly=False, secure=True, samesite="strict")
        return {"csrf_token": csrf}

    @application.get("/console", response_class=HTMLResponse, include_in_schema=False)
    def console_home(actor: Annotated[ConsolePrincipal, Depends(principal)]) -> HTMLResponse:
        del actor
        html_path = Path(__file__).with_name("console_ui.html")
        return HTMLResponse(
            html_path.read_text(encoding="utf-8"),
            headers={
                "Cache-Control": "no-store",
                "Content-Security-Policy": (
                    "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
                    "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
                ),
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @application.get("/v1/console/summary")
    def summary(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        repository: Annotated[TargetRepository, Depends(repo)],
    ) -> dict[str, object]:
        targets = repository.list_targets(actor.tenant_id)
        readiness_path = Path(__file__).parents[2] / "knowledge/readiness/v0.1-readiness.json"
        readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
        return {
            "principal": {"role": actor.role, "tenant_id": str(actor.tenant_id)},
            "counts": {"targets": len(targets), "open_reviews": 0, "asset_candidates": 0},
            "readiness": {
                "as_of_phase": readiness["as_of_phase"],
                "overall_status": readiness["overall_status"],
                "locks": readiness["locks"],
            },
        }

    @application.get("/v1/console/targets")
    def targets(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        repository: Annotated[TargetRepository, Depends(repo)],
    ) -> list[dict[str, object]]:
        return [
            {
                "id": str(item.id),
                "name": item.name,
                "type": item.target_type.value,
                "classification": item.classification.value,
                "state": item.state.value,
                "revision": item.revision,
                "evidence_count": len(item.source_evidence_ids),
            }
            for item in repository.list_targets(actor.tenant_id)
        ]

    @application.get("/console/api/reviews", include_in_schema=False)
    @application.get("/v1/console/reviews")
    def reviews(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[ConsoleReviewStore, Depends(durable)],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[dict[str, object]]:
        try:
            items = store.list_reviews_for_principal(
                str(actor.tenant_id), str(actor.principal_id), limit=limit, offset=offset
            )
        except (DurableStoreError, sqlite3.Error, OSError) as error:
            raise store_error(error) from None
        return [{
            "task_id": item.task_id, "job_id": item.job_id, "stage": item.stage.value,
            "reason_code": item.reason_code, "evidence_fingerprint": item.evidence_fingerprint,
            "expires_at": item.expires_at.isoformat(), "status": item.status.value,
        } for item in items]

    @application.get("/console/api/candidates", include_in_schema=False)
    @application.get("/v1/console/candidates")
    def candidates(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[ConsoleReviewStore, Depends(durable)],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[dict[str, object]]:
        try:
            return list(store.list_candidate_manifests_for_principal(
                str(actor.tenant_id), str(actor.principal_id), limit=limit, offset=offset
            ))
        except (DurableStoreError, sqlite3.Error, OSError) as error:
            raise store_error(error) from None

    @application.post(
        "/console/api/reviews/{task_id}/decisions", status_code=status.HTTP_202_ACCEPTED,
        include_in_schema=False,
    )
    @application.post("/v1/console/reviews/{task_id}/decisions", status_code=status.HTTP_202_ACCEPTED)
    def submit_review(
        task_id: UUID,
        payload: ReviewSubmission,
        request: Request,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, str]:
        del csrf_verified
        if actor.role != "reviewer":
            raise HTTPException(status_code=403, detail="reviewer role required")
        store = durable(request)
        if (payload.task_id != task_id or payload.tenant_id != actor.tenant_id
                or payload.principal_id != actor.principal_id):
            raise HTTPException(status_code=403, detail="review binding mismatch")
        try:
            decided = store.decide_review(str(actor.tenant_id), str(task_id), payload.attestation())
        except (DurableStoreError, sqlite3.Error, OSError) as error:
            raise store_error(error) from None
        return {"task_id": decided.task_id, "decision": payload.decision.value,
                "status": decided.status.value}


def console_security_from_config(
    *, environment: str | None = None, secret: str | None = None
) -> ConsoleSecurity:
    return ConsoleSecurity(
        environment=environment or os.getenv("APF_ENV", "development"),
        secret=secret or os.getenv("APF_CONSOLE_SESSION_SECRET"),
        allow_dev_sessions=os.getenv("APF_ENABLE_DEV_SESSION", "").lower() == "true",
    )
