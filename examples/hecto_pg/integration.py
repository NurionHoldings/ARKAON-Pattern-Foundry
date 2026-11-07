"""Host integration factory, no public unauthenticated checkout app by default."""
from pathlib import Path

from apf.hecto_pg import Ledger
from apf.hecto_pg_config import load_merchants
from apf.hecto_pg_http import HectoInquiry
from apf.hecto_pg_routes import build_router


def install(app, *, config_path: Path, persistent_db: Path,
            authorize_checkout, resolve_order, authorize_read):
    app.include_router(build_router(
        load_merchants(config_path), Ledger(persistent_db),
        authorize_checkout=authorize_checkout, resolve_order=resolve_order,
        authorize_read=authorize_read, inquiry=HectoInquiry(),
    ))
# Host responsibilities:
# authorize_checkout: authenticate session/API credential + check platform + CSRF for cookies.
# resolve_order: load owner-bound unpaid order from authoritative DB. Never use browser amount.
# authorize_read: authenticate identity and return its actual principal_id, never a browser claim.
# Consume PAYMENT_VERIFIED outbox in an idempotent application transaction keyed by payment_id.
# Existing billing DIGEST mode is NOT payment proof; production must use a verified billing SoT.
