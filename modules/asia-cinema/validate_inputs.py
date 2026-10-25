"""ASIA cinema PR-A: read-only input validation; no rendering or network access."""
import argparse
import hashlib
import json
from pathlib import Path

REQUIRED = ("reference", "symbol_mask", "slogan")
SLOGAN = "세상을 연결하는 가치, 더 큰 내일을 만듭니다"
APPROVED_SHA = "e9cc11036d72e2b6216b118d1dce41e3abcf345be7d98cdcffd1b05e16bc19a8"

def digest(data):
    return hashlib.sha256(data).hexdigest()

def validate(manifest_path):
    path = Path(manifest_path).resolve()
    report = {"status": "FAIL", "checks": [], "errors": []}
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("manifest must be an object")
        assets = manifest.get("assets")
        if not isinstance(assets, dict):
            raise ValueError("assets must be an object")
        for name in REQUIRED:
            entry = assets.get(name)
            if not isinstance(entry, dict):
                report["errors"].append(f"{name}: missing asset declaration")
                continue
            relative = entry.get("path")
            expected = entry.get("sha256")
            if not isinstance(relative, str) or not relative or not isinstance(expected, str) or len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
                report["errors"].append(f"{name}: invalid path or sha256")
                continue
            candidate = (path.parent / relative).resolve()
            if not candidate.is_relative_to(path.parent):
                report["errors"].append(f"{name}: path outside manifest directory")
                continue
            if not candidate.is_file():
                report["errors"].append(f"{name}: missing file")
                continue
            raw = candidate.read_bytes()
            if digest(raw) != expected:
                report["errors"].append(f"{name}: sha256 mismatch")
                continue
            if name == "slogan":
                if entry.get("status") != "approved":
                    report["errors"].append("slogan: not approved")
                    continue
                try:
                    text = raw.decode("utf-8", errors="strict")
                except UnicodeDecodeError:
                    report["errors"].append("slogan: invalid UTF-8")
                    continue
                if text != SLOGAN or expected != APPROVED_SHA:
                    report["errors"].append("slogan: text or approved hash mismatch")
                    continue
            report["checks"].append({"asset": name, "status": "PASS"})
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report["errors"].append(f"manifest: {type(exc).__name__}")
    if not report["errors"] and len(report["checks"]) == len(REQUIRED):
        report["status"] = "PASS"
    return report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = validate(args.manifest)
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")
    print(payload, end="")
    raise SystemExit(0 if result["status"] == "PASS" else 1)

if __name__ == "__main__":
    main()
