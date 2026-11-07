"""Offline sandbox provisioning. Public provider credentials are NOT production keys."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from .hecto_pg import PGRejected, https_url
from .hecto_pg_config import load_merchants

PLATFORMS = {
    "arkaon": ("ARKAON", "아르카온"),
    "dapanda": ("DAPANDA", "다판다"),
    "the-arirang": ("ARIRANG", "더아리랑"),
    "ai-lawfriend": ("LAWFRIEND", "AI법친"),
}
# Public examples in the official standard authenticated-card documentation.
# This shared test MID does not create four independently issued merchant accounts.
PUBLIC_CARD = ("nxca_jt_il", "ST1009281328226982205", "pgSettle30y739r82jtd709yOfZ2yK5K")


def seed(directory: Path) -> dict:
    """Creates new private files only; never overwrites existing merchant credentials."""
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if any(directory.iterdir()):
        raise PGRejected("SETUP_DIRECTORY_NOT_EMPTY")
    env, platforms = [], {}
    for platform, (prefix, name) in PLATFORMS.items():
        root = "HECTO_" + prefix
        keys = [root + suffix for suffix in ("_MCHT_ID", "_HASH_KEY", "_AES_KEY")]
        env.extend(f"{key}={value}" for key, value in zip(keys, PUBLIC_CARD, strict=True))
        platforms[platform] = {
            "enabled": False, "merchant_name": name,
            "merchant_id_env": keys[0], "hash_key_env": keys[1], "aes_key_env": keys[2],
            "noti_url": "", "next_url": "", "cancel_url": "",
        }
    config = {"schema_version":"apf.hecto-platform-map/v1", "enabled":False,
              "environment":"sandbox", "credential_source":"HECTO_PUBLIC_CARD_SANDBOX",
              "platforms":platforms}
    for filename, content in (
        ("sandbox.env", "# PUBLIC SANDBOX ONLY. Never import into production.\n" + "\n".join(env) + "\n"),
        ("platforms.local.json", json.dumps(config, ensure_ascii=False, indent=2) + "\n"),
    ):
        fd = os.open(directory / filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
    return {"status":"PUBLIC_TEST_KEYS_PREPARED_CALLBACKS_REQUIRED", "platforms":list(platforms),
            "environment":"sandbox", "production_changed":False, "host_env_registered":False}


def read_env(path: Path) -> dict:
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or key in result or not key.startswith("HECTO_"):
            raise PGRejected("SANDBOX_ENV_FORMAT")
        result[key] = value
    return result


def check(directory: Path) -> dict:
    config = json.loads((directory / "platforms.local.json").read_text(encoding="utf-8"))
    if config.get("environment") != "sandbox":
        raise PGRejected("SANDBOX_ONLY")
    env = read_env(directory / "sandbox.env")
    platforms = []
    for platform, item in config["platforms"].items():
        keys_ok = (bool(env.get(item["merchant_id_env"])) and bool(env.get(item["hash_key_env"]))
                   and len(env.get(item["aes_key_env"], "").encode()) == 32)
        callbacks_ok = True
        for field in ("noti_url", "next_url", "cancel_url"):
            try:
                https_url(item.get(field, ""))
            except (ValueError, TypeError):
                callbacks_ok = False
        platforms.append({"platform":platform, "keys_configured":keys_ok,
                          "callbacks_configured":callbacks_ok, "enabled":item.get("enabled") is True})
    # Reuse actual runtime loader when enabled; do not merely report key length as READY.
    ready = config.get("enabled") is True and any(p["enabled"] for p in platforms)
    if ready:
        load_merchants(directory / "platforms.local.json", environ=env)
    return {"status":"READY_FOR_SANDBOX_HOST_TEST" if ready else "CALLBACKS_AND_HOST_PENDING",
            "platforms":platforms, "host_env_registered":False, "payment_executed":False}


def configure(directory: Path, platform: str, api_origin: str, return_url: str, cancel_url: str) -> dict:
    if platform not in PLATFORMS:
        raise PGRejected("UNKNOWN_PLATFORM")
    https_url(api_origin)
    if urlsplit(api_origin).path not in ("", "/"):
        raise PGRejected("API_ORIGIN_REQUIRES_NO_PATH")
    https_url(return_url)
    https_url(cancel_url)
    path = directory / "platforms.local.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("environment") != "sandbox":
        raise PGRejected("SANDBOX_ONLY")
    config["enabled"] = True
    config["platforms"][platform].update(enabled=True,
        noti_url=api_origin.rstrip("/") + "/v1/payments/hecto/" + platform + "/noti",
        next_url=return_url, cancel_url=cancel_url)
    load_merchants_from_config = directory / "platforms.next.json"
    created = False
    try:
        fd = os.open(load_merchants_from_config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(config, stream, ensure_ascii=False, indent=2)
        load_merchants(load_merchants_from_config, environ=read_env(directory / "sandbox.env"))
        os.replace(load_merchants_from_config, path)
    finally:
        if created:
            load_merchants_from_config.unlink(missing_ok=True)
    return check(directory)


def main():
    parser = argparse.ArgumentParser(description="Public Hecto sandbox setup; no payment calls")
    parser.add_argument("action", choices=["seed", "check", "configure"])
    parser.add_argument("--directory", type=Path, default=Path("private/hecto-pg"))
    parser.add_argument("--platform", choices=list(PLATFORMS))
    parser.add_argument("--api-origin")
    parser.add_argument("--return-url")
    parser.add_argument("--cancel-url")
    args = parser.parse_args()
    try:
        if args.action == "seed":
            result = seed(args.directory)
        elif args.action == "check":
            result = check(args.directory)
        else:
            if not all((args.platform, args.api_origin, args.return_url, args.cancel_url)):
                parser.error("configure needs platform/api-origin/return-url/cancel-url")
            result = configure(args.directory, args.platform, args.api_origin, args.return_url, args.cancel_url)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (PGRejected, OSError, ValueError, KeyError):
        parser.exit(1, "Sandbox setup failed; check private configuration. No values printed.\n")


if __name__ == "__main__":
    main()
