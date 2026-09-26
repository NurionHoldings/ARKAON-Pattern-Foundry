#!/usr/bin/env python3
"""Pattern promotion signing helper. Private keys stay outside Foundry runtime."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from apf.pattern_catalog import PromotionDecision, catalog_revision, validate_catalog  # noqa: E402


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _load_private_key(path: Path) -> Ed25519PrivateKey:
    raw = path.read_bytes()
    if len(raw) == 32:
        return Ed25519PrivateKey.from_private_bytes(raw)
    text = raw.decode("utf-8").strip()
    if text.startswith("{"):
        document = json.loads(text)
        seed = document.get("private_key_b64") or document.get("seed_b64")
        if not seed:
            raise ValueError("private key json must include private_key_b64 or seed_b64")
        key_bytes = base64.urlsafe_b64decode(seed + "=" * (-len(seed) % 4))
        return Ed25519PrivateKey.from_private_bytes(key_bytes)
    key_bytes = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    if len(key_bytes) != 32:
        raise ValueError("private key material must decode to 32 bytes")
    return Ed25519PrivateKey.from_private_bytes(key_bytes)


def _public_key_b64(private: Ed25519PrivateKey) -> str:
    return base64.urlsafe_b64encode(private.public_key().public_bytes_raw()).rstrip(b"=").decode()


def _sign(private: Ed25519PrivateKey, decision: PromotionDecision) -> str:
    raw = _canonical(decision.payload())
    return base64.urlsafe_b64encode(private.sign(raw)).rstrip(b"=").decode()


def _decision_for(package: dict, revision: str, nonce: str) -> PromotionDecision:
    return PromotionDecision(
        pattern_id=package["pattern_id"],
        catalog_revision=revision,
        package_hash=package["package_hash"],
        evidence_digest=hashlib.sha256(_canonical(package["evidence_hashes"])).hexdigest(),
        test_digest=hashlib.sha256(_canonical(package["verification_test_ids"])).hexdigest(),
        policy="apf.public-pattern-promotion/1.0",
        expires_at="2030-01-01T00:00:00Z",
        nonce=nonce,
    )


def _load_candidates() -> list[dict]:
    directory = ROOT / "knowledge" / "patterns" / "candidates"
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(directory.glob("*.json"))
    ]


def cmd_export_public_key(args: argparse.Namespace) -> int:
    private = _load_private_key(Path(args.private_key))
    print(json.dumps({"ethernian_public_key_b64": _public_key_b64(private)}, indent=2))
    return 0


def cmd_sign_manifest(args: argparse.Namespace) -> int:
    private = _load_private_key(Path(args.private_key))
    packages = _load_candidates()
    revision = args.catalog_revision or validate_catalog(packages, ROOT)
    by_id = {package["pattern_id"]: package for package in packages}
    decisions = []
    for index, pattern_id in enumerate(args.pattern_ids):
        package = by_id.get(pattern_id)
        if package is None:
            raise SystemExit(f"unknown pattern_id: {pattern_id}")
        nonce = f"{args.nonce_prefix}-{index}"
        decision = _decision_for(package, revision, nonce)
        decisions.append(
            {
                "pattern_id": pattern_id,
                "source": args.source,
                "decision": decision.payload(),
                "signature": _sign(private, decision),
            }
        )
    manifest = {
        "schema_version": "apf.pattern-promotion-manifest/v1",
        "catalog_revision": revision,
        "decisions": decisions,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "output": output.as_posix(), "decisions": len(decisions)}, indent=2))
    return 0


def cmd_demo_test_vector(args: argparse.Namespace) -> int:
    private = Ed25519PrivateKey.generate()
    packages = _load_candidates()
    revision = validate_catalog(packages, ROOT)
    manifest = {
        "schema_version": "apf.pattern-promotion-manifest/v1",
        "catalog_revision": revision,
        "decisions": [],
        "notes": ["TEST_VECTOR demo only; not a production eternian approval"],
    }
    for index, package in enumerate(packages[: args.count]):
        decision = _decision_for(package, revision, f"demo-test-vector-{index}")
        manifest["decisions"].append(
            {
                "pattern_id": package["pattern_id"],
                "source": "TEST_VECTOR",
                "decision": decision.payload(),
                "signature": _sign(private, decision),
            }
        )
    policy_path = ROOT / "config" / "arkaon-pattern-promotion.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["ethernian_public_key_b64"] = _public_key_b64(private)
    policy["accept_test_vector_decisions"] = True
    manifest_path = ROOT / "config" / "pattern-promotion-manifest.json"
    if args.apply:
        policy_path.write_text(json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    example_dir = ROOT / "config" / "examples"
    example_dir.mkdir(parents=True, exist_ok=True)
    (example_dir / "arkaon-pattern-promotion.test-vector.example.json").write_text(
        json.dumps(policy, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (example_dir / "pattern-promotion-manifest.test-vector.example.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "applied": args.apply,
                "catalog_revision": revision,
                "signed_patterns": len(manifest["decisions"]),
                "ethernian_public_key_b64": policy["ethernian_public_key_b64"],
                "example_policy": (example_dir / "arkaon-pattern-promotion.test-vector.example.json").as_posix(),
                "example_manifest": (
                    example_dir / "pattern-promotion-manifest.test-vector.example.json"
                ).as_posix(),
                "generated_at": datetime.now(tz=UTC).isoformat(),
            },
            indent=2,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Pattern promotion signing helper")
    sub = parser.add_subparsers(dest="command", required=True)

    export_cmd = sub.add_parser("export-public-key", help="print urlsafe-b64 public key from a private key file")
    export_cmd.add_argument("--private-key", required=True, help="32-byte raw or urlsafe-b64 or json seed file")
    export_cmd.set_defaults(func=cmd_export_public_key)

    sign_cmd = sub.add_parser("sign-manifest", help="sign one or more pattern promotion decisions")
    sign_cmd.add_argument("--private-key", required=True)
    sign_cmd.add_argument("--pattern-ids", nargs="+", required=True)
    sign_cmd.add_argument("--catalog-revision", default=None)
    sign_cmd.add_argument("--nonce-prefix", default="external-promotion")
    sign_cmd.add_argument("--source", default="EXTERNAL_ETHERNIAN", choices=("EXTERNAL_ETHERNIAN", "TEST_VECTOR"))
    sign_cmd.add_argument("--output", required=True)
    sign_cmd.set_defaults(func=cmd_sign_manifest)

    demo_cmd = sub.add_parser("demo-test-vector", help="generate TEST_VECTOR demo policy+manifest examples")
    demo_cmd.add_argument("--count", type=int, default=3)
    demo_cmd.add_argument(
        "--apply",
        action="store_true",
        help="write config/arkaon-pattern-promotion.json and config/pattern-promotion-manifest.json",
    )
    demo_cmd.set_defaults(func=cmd_demo_test_vector)

    args = parser.parse_args()
    try:
        return args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "error", "message": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
