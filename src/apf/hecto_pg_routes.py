"""Explicitly mounted adapter: host supplies authenticated order/ownership policy.

Not automatically mounted in apf.api. No price/principal/merchant/key in browser input.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from .hecto_pg import KST, Ledger, Merchant, Order, PGRejected, checkout, parse_notification


class CheckoutInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    business_order_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")


def build_router(merchants: dict[str, Merchant], ledger: Ledger, *, resolve_order, authorize_read,
                 authorize_checkout, inquiry) -> APIRouter:
    """Callbacks are trusted host code. authorize_checkout MUST enforce auth/CSRF.

    resolve_order(request, platform, business_order_id) -> principal_id, amount_krw, product
    authorize_read(request, platform, payment_id) -> authenticated principal_id
    No default allow policy is provided.
    """
    router = APIRouter(prefix="/v1/payments/hecto")

    def merchant(platform):
        if platform not in merchants or merchants[platform].platform_id != platform:
            raise HTTPException(404, "결제 플랫폼을 찾을 수 없습니다")
        return merchants[platform]

    @router.post("/{platform}/checkout")
    def start(platform: str, body: CheckoutInput, request: Request):
        m = merchant(platform)
        if authorize_checkout(request, platform) is not True:
            raise HTTPException(403, "결제 요청 권한을 확인해 주세요")
        principal, price, product = resolve_order(request, platform, body.business_order_id)
        now = datetime.now(KST)
        # One payment attempt per business order. Existing orders must be explicitly resumed.
        order = Order(platform, principal, body.business_order_id, uuid4().hex, price, product)
        try:
            ledger.register(m, order, now)
            return {"payment_id": order.payment_id, **checkout(m, order, now)}
        except PGRejected as e:
            raise HTTPException(409, str(e)) from e

    @router.get("/{platform}/orders/{payment_id}")
    def status(platform: str, payment_id: str, request: Request):
        merchant(platform)
        principal = authorize_read(request, platform, payment_id)
        try:
            row = ledger.get(platform, principal, payment_id)
        except PGRejected as e:
            raise HTTPException(404, "주문을 찾을 수 없습니다") from e
        return {"payment_id": payment_id, "status": row["status"]}

    @router.post("/{platform}/noti", response_class=PlainTextResponse)
    async def noti(platform: str, request: Request):
        m = merchant(platform)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 16384:
                return PlainTextResponse("FAIL", status_code=413)
        try:
            data = parse_notification(bytes(body), request.headers.get("content-type", ""))
            # Blocking disk/inquiry work runs off the event loop.
            from starlette.concurrency import run_in_threadpool
            result = await run_in_threadpool(ledger.receive, m, data, inquiry)
            return PlainTextResponse(result)
        except (PGRejected, OSError, ValueError, sqlite3.Error):
            return PlainTextResponse("FAIL")

    return router
