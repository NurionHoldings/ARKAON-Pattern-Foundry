"""Explicit platform registration; environment values are never returned or logged."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .hecto_pg import Merchant, PGRejected


def load_merchants(path: Path, *, environ=None) -> dict[str, Merchant]:
    env = os.environ if environ is None else environ
    data = json.loads(path.read_text(encoding="utf-8"))
    if (data.get("schema_version") != "apf.hecto-platform-map/v1"
            or data.get("enabled") is not True or data.get("environment") != "sandbox"):
        raise PGRejected("SANDBOX_CONFIGURATION_DISABLED")
    result = {}
    for platform, config in data["platforms"].items():
        # Only explicitly enabled merchants load; an example entry is not a contract.
        if config.get("enabled") is not True:
            continue
        try:
            result[platform] = Merchant(
                platform, env[config["merchant_id_env"]], config["merchant_name"],
                env[config["hash_key_env"]], env[config["aes_key_env"]].encode("utf-8"),
                config["noti_url"], config["next_url"], config["cancel_url"],
            )
        except KeyError as e:
            raise PGRejected("MERCHANT_CONFIGURATION_MISSING") from e
    if not result:
        raise PGRejected("NO_ENABLED_MERCHANTS")
    return result
