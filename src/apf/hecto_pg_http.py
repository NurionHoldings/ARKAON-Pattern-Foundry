"""Read-only transaction inquiry over fixed HTTPS endpoint, no redirect or retries."""
from __future__ import annotations

import hmac
import json
from datetime import datetime
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

from .hecto_pg import KST, Merchant, PGRejected, packet_hash


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post_inquiry(payload: dict) -> dict:
    request = Request("https://tbgw.settlebank.co.kr/spay/APITrdcheck.do",
                      data=json.dumps(payload).encode(), method="POST",
                      headers={"Content-Type": "application/json"})
    with build_opener(NoRedirect()).open(request, timeout=10) as response:
        body = response.read(65537)
        if response.status != 200 or len(body) > 65536:
            raise PGRejected("INQUIRY_HTTP_RESPONSE")
    return json.loads(body)


class HectoInquiry:
    def __init__(self, transport=post_inquiry, clock=lambda: datetime.now(KST)):
        self.transport, self.clock = transport, clock

    def __call__(self, merchant: Merchant, row: dict, notification: dict) -> bool:
        now = self.clock().astimezone(KST)
        dt, tm, query_id = now.strftime("%Y%m%d"), now.strftime("%H%M%S"), uuid4().hex
        request_hash = packet_hash(dt, tm, merchant.mcht_id, query_id, row["amount"], merchant.hash_key)
        payload = {
            "params": {"mchtId": merchant.mcht_id, "ver": "0A1M", "mchtTrdNo": query_id,
                       "trdDt": dt, "trdTm": tm},
            "data": {"pktHash": request_hash, "method": "CA", "trdAmt": row["amount"],
                     "orgTrdDt": row["request_date"], "orgMchtTrdNo": row["payment_id"],
                     "orgTrdNo": notification["trdNo"]},
        }
        try:
            result = self.transport(payload)
            p, d = result["params"], result["data"]
            return (p["mchtId"] == merchant.mcht_id and p["mchtTrdNo"] == query_id
                    and p["ver"] == "0A1M" and p["outStatCd"] == "0021"
                    and p["outRsltCd"] == "0000" and d["method"] == "CA"
                    and d["trdAmt"] == row["amount"] and str(d.get("cnclAmt", "0")) == "0"
                    and hmac.compare_digest(d["pktHash"], request_hash))
        except (KeyError, TypeError, ValueError, OSError):
            return False
