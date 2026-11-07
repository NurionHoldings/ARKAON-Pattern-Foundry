"""Hecto standard card form adapter and durable, tenant-bound sandbox ledger.

No network payment initiation. Checkout fields follow the card FORM contract
(method=card), not the inconsistent CA example in the SDK overview.
"""
from __future__ import annotations

import base64
import hmac
import json
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

KST = timezone(timedelta(hours=9), "KST")


class PGRejected(ValueError):
    """Safe reason codes only: never include keys or complete provider payloads."""


def token(value: str, maximum: int = 100) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1," + str(maximum) + "}", value):
        raise PGRejected("INVALID_IDENTIFIER")
    return value


def amount(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]{0,11}", value):
        raise PGRejected("INVALID_KRW_AMOUNT")
    return value


def text(value: str, maximum: int) -> str:
    if not value or len(value.encode("utf-8")) > maximum or not re.fullmatch(r"[가-힣A-Za-z0-9 ._-]+", value):
        raise PGRejected("INVALID_DISPLAY_TEXT")
    return value


def https_url(value: str) -> str:
    u = urlsplit(value)
    if (u.scheme != "https" or not u.hostname or u.username or u.password or u.fragment
            or u.query or u.port not in (None, 443) or len(value.encode()) > 250):
        raise PGRejected("INVALID_CALLBACK_URL")
    return value


def packet_hash(*parts: str) -> str:
    return sha256("".join(parts).encode("utf-8")).hexdigest()


def encrypt(value: str, key: bytes) -> str:
    if len(key) != 32:
        raise PGRejected("AES_KEY_MUST_BE_32_BYTES")
    padder = padding.PKCS7(128).padder()
    padded = padder.update(value.encode("utf-8")) + padder.finalize()
    enc = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return base64.b64encode(enc.update(padded) + enc.finalize()).decode("ascii")


@dataclass(frozen=True)
class Merchant:
    platform_id: str
    mcht_id: str
    name: str
    hash_key: str = field(repr=False)
    aes_key: bytes = field(repr=False)
    noti_url: str = ""
    next_url: str = ""
    cancel_url: str = ""
    environment: str = "sandbox"

    def __post_init__(self):
        token(self.platform_id)
        token(self.mcht_id, 12)
        text(self.name, 100)
        if self.environment != "sandbox":
            # Production needs separate integration certification and owner activation.
            raise PGRejected("PRODUCTION_NOT_ENABLED")
        if not self.hash_key or len(self.aes_key) != 32:
            raise PGRejected("MERCHANT_KEYS_REQUIRED")
        for u in (self.noti_url, self.next_url, self.cancel_url):
            https_url(u)


@dataclass(frozen=True)
class Order:
    platform_id: str
    principal_id: str
    business_order_id: str
    payment_id: str
    amount_krw: str
    product: str

    def __post_init__(self):
        for v in (self.platform_id, self.principal_id, self.business_order_id, self.payment_id):
            token(v)
        amount(self.amount_krw)
        text(self.product, 128)


def checkout(merchant: Merchant, order: Order, now: datetime) -> dict:
    if merchant.platform_id != order.platform_id or now.tzinfo is None:
        raise PGRejected("ORDER_BINDING_OR_TIMEZONE")
    at = now.astimezone(KST)
    dt, tm = at.strftime("%Y%m%d"), at.strftime("%H%M%S")
    fields = {
        "mchtId": merchant.mcht_id, "method": "card", "mchtTrdNo": order.payment_id,
        "mchtName": merchant.name, "pmtPrdtNm": order.product, "trdDt": dt, "trdTm": tm,
        "trdAmt": encrypt(order.amount_krw, merchant.aes_key),
        "notiUrl": merchant.noti_url, "nextUrl": merchant.next_url, "cancUrl": merchant.cancel_url,
        "pktHash": packet_hash(merchant.mcht_id, "card", order.payment_id, dt, tm,
                               order.amount_krw, merchant.hash_key),
    }
    return {"action": "https://tbnpg.settlebank.co.kr/card/main.do", "method": "POST",
            "fields": fields}


def parse_notification(body: bytes, content_type: str) -> dict[str, str]:
    if len(body) > 16384 or content_type.split(";", 1)[0].lower() != "application/x-www-form-urlencoded":
        raise PGRejected("NOTIFICATION_FORMAT")
    try:
        pairs = parse_qsl(body.decode("utf-8"), keep_blank_values=True, strict_parsing=True,
                          encoding="utf-8", errors="strict", max_num_fields=100)
    except (ValueError, UnicodeError) as e:
        raise PGRejected("NOTIFICATION_ENCODING") from e
    result = {}
    for key, value in pairs:
        if key in result:
            raise PGRejected("DUPLICATE_NOTIFICATION_FIELD")
        result[key] = value
    return result


def verify_notification(merchant: Merchant, order: Order, data: dict) -> dict:
    required = ("outStatCd", "trdDtm", "mchtId", "mchtTrdNo", "trdAmt", "pktHash", "method", "bizType", "trdNo")
    if not all(isinstance(data.get(k), str) and data[k] for k in required):
        raise PGRejected("NOTIFICATION_FIELDS")
    if (merchant.platform_id != order.platform_id or data["mchtId"] != merchant.mcht_id
            or data["mchtTrdNo"] != order.payment_id or data["trdAmt"] != order.amount_krw):
        raise PGRejected("NOTIFICATION_ORDER_MISMATCH")
    if not re.fullmatch(r"[0-9]{14}", data["trdDtm"]):
        raise PGRejected("NOTIFICATION_TIME")
    try:
        datetime.strptime(data["trdDtm"], "%Y%m%d%H%M%S")
    except ValueError as e:
        raise PGRejected("NOTIFICATION_TIME") from e
    expected = packet_hash(data["outStatCd"], data["trdDtm"], merchant.mcht_id,
                           order.payment_id, order.amount_krw, merchant.hash_key)
    if not re.fullmatch(r"[0-9a-f]{64}", data["pktHash"]) or not hmac.compare_digest(expected, data["pktHash"]):
        raise PGRejected("NOTIFICATION_HASH")
    # Never interpret authentication-only 0061, issuance, billing-key or cancel as PAID.
    if (data["outStatCd"], data["bizType"], data["method"]) != ("0021", "B0", "CA"):
        raise PGRejected("UNSUPPORTED_NOTIFICATION_STATE")
    token(data["trdNo"], 40)
    # These fields are not all protected by pktHash. A trusted S2S inquiry is mandatory.
    return {k: data[k] for k in required if k != "pktHash"}


class Ledger:
    """SQLite durable sandbox store. Local disk only; not a serverless /tmp database."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS hecto_orders (
                    platform TEXT NOT NULL, principal TEXT NOT NULL, business_id TEXT NOT NULL,
                    payment_id TEXT PRIMARY KEY, amount TEXT NOT NULL, product TEXT NOT NULL,
                    mcht_id TEXT NOT NULL, request_date TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING', provider_trd TEXT,
                    UNIQUE(platform, business_id), UNIQUE(mcht_id, provider_trd));
                CREATE TABLE IF NOT EXISTS hecto_outbox (
                    payment_id TEXT PRIMARY KEY REFERENCES hecto_orders(payment_id),
                    platform TEXT NOT NULL, principal TEXT NOT NULL, business_id TEXT NOT NULL,
                    event_type TEXT NOT NULL, evidence_digest TEXT NOT NULL);
            ''')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db
        finally:
            db.close()

    def register(self, merchant: Merchant, order: Order, now: datetime) -> None:
        checkout(merchant, order, now)  # validate before persisting any request
        values = (order.platform_id, order.principal_id, order.business_order_id, order.payment_id,
                  order.amount_krw, order.product, merchant.mcht_id,
                  now.astimezone(KST).strftime("%Y%m%d"))
        with self.connection() as db:
            db.execute("INSERT OR IGNORE INTO hecto_orders "
                       "(platform,principal,business_id,payment_id,amount,product,mcht_id,request_date) "
                       "VALUES (?,?,?,?,?,?,?,?)", values)
            row = db.execute("SELECT * FROM hecto_orders WHERE payment_id=?", (order.payment_id,)).fetchone()
            if row is None or tuple(row[k] for k in (
                    "platform", "principal", "business_id", "payment_id", "amount", "product", "mcht_id")) != values[:7]:
                raise PGRejected("ORDER_IDEMPOTENCY_CONFLICT")

    def get(self, platform: str, principal: str, payment_id: str) -> dict:
        with self.connection() as db:
            row = db.execute("SELECT * FROM hecto_orders WHERE platform=? AND principal=? AND payment_id=?",
                             (platform, principal, payment_id)).fetchone()
        if row is None:
            raise PGRejected("ORDER_NOT_FOUND")
        return dict(row)

    def receive(self, merchant: Merchant, data: dict, inquiry) -> str:
        with self.connection() as db:
            row = db.execute("SELECT * FROM hecto_orders WHERE platform=? AND mcht_id=? AND payment_id=?",
                             (merchant.platform_id, merchant.mcht_id, data.get("mchtTrdNo", ""))).fetchone()
        if row is None:
            raise PGRejected("ORDER_NOT_FOUND")
        order = Order(row["platform"], row["principal"], row["business_id"], row["payment_id"],
                      row["amount"], row["product"])
        verified = verify_notification(merchant, order, data)
        if inquiry is None or inquiry(merchant, dict(row), verified) is not True:
            raise PGRejected("S2S_INQUIRY_REQUIRED")
        evidence = packet_hash(json.dumps(verified, sort_keys=True, separators=(",", ":")))
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT * FROM hecto_orders WHERE payment_id=?", (order.payment_id,)).fetchone()
            if current["status"] == "PAID":
                if current["provider_trd"] != verified["trdNo"]:
                    raise PGRejected("PROVIDER_TRANSACTION_CONFLICT")
                return "OK"
            if current["status"] != "PENDING":
                raise PGRejected("ORDER_STATE_CONFLICT")
            try:
                db.execute("UPDATE hecto_orders SET status='PAID',provider_trd=? WHERE payment_id=?",
                           (verified["trdNo"], order.payment_id))
                db.execute("INSERT INTO hecto_outbox VALUES (?,?,?,?,?,?)",
                           (order.payment_id, order.platform_id, order.principal_id,
                            order.business_order_id, "PAYMENT_VERIFIED", evidence))
            except sqlite3.IntegrityError as e:
                raise PGRejected("PROVIDER_TRANSACTION_CONFLICT") from e
        return "OK"  # only after payment and durable outbox commit
