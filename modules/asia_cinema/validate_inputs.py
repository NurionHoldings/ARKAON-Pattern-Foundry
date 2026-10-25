"""Validate ASIA HOLDINGS cinema input bundle (PR-A). Blocks render on failure."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

SCHEMA_ID = "apf.asia-cinema-input-bundle/v1"
COMPANY_LITERAL = "ASIA HOLDINGS"
REQUIRED_ASSET_IDS = frozenset({"asia_holdings_reference", "asia_a_symbol_mask"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class AssetPin(BaseModel):
    id: str
    path: str
    sha256: str
    role: str | None = None

    @field_validator("sha256")
    @classmethod
    def _hex_lower(cls, v: str) -> str:
        v = v.lower()
        if not _SHA256.match(v):
            raise ValueError("sha256 must be 64 lowercase hex digits")
        return v


class SloganPin(BaseModel):
    path: str
    sha256: str
    registration_path: str

    @field_validator("sha256")
    @classmethod
    def _hex_lower(cls, v: str) -> str:
        v = v.lower()
        if not _SHA256.match(v):
            raise ValueError("sha256 must be 64 lowercase hex digits")
        return v


class InputBundle(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    bundle_schema: str = Field(alias="schema")
    run_id: str = Field(min_length=8, max_length=128)
    company_name_literal: str
    assets: list[AssetPin]
    slogan_ko: SloganPin

    @field_validator("bundle_schema")
    @classmethod
    def _schema(cls, v: str) -> str:
        if v != SCHEMA_ID:
            raise ValueError(f"unsupported schema: {v}")
        return v

    @field_validator("company_name_literal")
    @classmethod
    def _company(cls, v: str) -> str:
        if v != COMPANY_LITERAL:
            raise ValueError("company_name_literal must be ASIA HOLDINGS")
        return v


class SloganRegistration(BaseModel):
    status: str
    approved_text: str | None = None
    approved_text_sha256: str | None = None


@dataclass
class ValidationIssue:
    code: str
    message: str
    asset_id: str | None = None


@dataclass
class ValidationReport:
    schema: str = "apf.asia-cinema-validation-report/v1"
    run_id: str = ""
    created_at: str = ""
    ok: bool = False
    render_allowed: bool = False
    issues: list[ValidationIssue] = field(default_factory=list)
    checked: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        """JSON-safe report without local absolute paths."""
        return {
            "schema": self.schema,
            "run_id": self.run_id,
            "created_at": self.created_at,
            "ok": self.ok,
            "render_allowed": self.render_allowed,
            "issues": [asdict(i) for i in self.issues],
            "checked": self.checked,
        }


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _redact_path(path: str) -> str:
    """Never emit full local paths in public reports."""
    name = Path(path).name
    return f"<asset:{name}>"


def validate_input_bundle(
    bundle: InputBundle | dict[str, Any],
    *,
    repo_root: Path | None = None,
) -> ValidationReport:
    issues: list[ValidationIssue] = []
    checked: dict[str, Any] = {}
    now = datetime.now(UTC).isoformat()

    try:
        if isinstance(bundle, dict):
            model = InputBundle.model_validate(bundle)
        else:
            model = bundle
    except ValidationError as exc:
        rep = ValidationReport(run_id=str((bundle or {}).get("run_id", "")), created_at=now)
        rep.issues.append(ValidationIssue("MANIFEST_SCHEMA", str(exc.errors()[0]["msg"])))
        rep.ok = False
        rep.render_allowed = False
        return rep

    rep = ValidationReport(run_id=model.run_id, created_at=now)
    root = repo_root or Path.cwd()

    asset_ids = {a.id for a in model.assets}
    for req in REQUIRED_ASSET_IDS:
        if req not in asset_ids:
            issues.append(ValidationIssue("ASSET_MISSING", f"required asset id missing: {req}", req))

    reg_path = _resolve_path(model.slogan_ko.registration_path, root)
    if not reg_path.is_file():
        issues.append(ValidationIssue("REGISTRATION_MISSING", "slogan registration file not found"))
    else:
        try:
            reg_raw = json.loads(reg_path.read_text(encoding="utf-8"))
            reg = SloganRegistration.model_validate(reg_raw)
        except (json.JSONDecodeError, ValidationError):
            issues.append(ValidationIssue("REGISTRATION_INVALID", "slogan registration unreadable"))
            reg = None
        if reg is not None:
            if reg.status != "approved":
                issues.append(ValidationIssue("SLOGAN_NOT_APPROVED", "slogan registration status is not approved"))
            checked["slogan_registration_status"] = reg.status

    for asset in model.assets:
        aid = asset.id
        p = _resolve_path(asset.path, root)
        checked[f"asset_{aid}"] = {"path_ref": _redact_path(asset.path), "expected_sha256": asset.sha256}
        if not p.is_file():
            issues.append(ValidationIssue("FILE_MISSING", f"asset file not found: {aid}", aid))
            continue
        actual = _sha256_file(p)
        checked[f"asset_{aid}"]["actual_sha256"] = actual
        if actual != asset.sha256.lower():
            issues.append(ValidationIssue("HASH_MISMATCH", f"sha256 mismatch: {aid}", aid))

    slogan_path = _resolve_path(model.slogan_ko.path, root)
    checked["slogan_ko"] = {
        "path_ref": _redact_path(model.slogan_ko.path),
        "expected_sha256": model.slogan_ko.sha256,
    }
    if not slogan_path.is_file():
        issues.append(ValidationIssue("SLOGAN_FILE_MISSING", "slogan utf-8 file not found"))
    else:
        raw = slogan_path.read_bytes()
        actual_slogan_sha = _sha256_bytes(raw)
        checked["slogan_ko"]["actual_sha256"] = actual_slogan_sha
        if actual_slogan_sha != model.slogan_ko.sha256.lower():
            issues.append(ValidationIssue("SLOGAN_HASH_MISMATCH", "slogan file sha256 mismatch"))
        if reg_path.is_file():
            try:
                reg_raw = json.loads(reg_path.read_text(encoding="utf-8"))
                reg = SloganRegistration.model_validate(reg_raw)
                if reg.status == "approved" and reg.approved_text_sha256:
                    if actual_slogan_sha != reg.approved_text_sha256.lower():
                        issues.append(
                            ValidationIssue(
                                "SLOGAN_REGISTRATION_HASH_MISMATCH",
                                "slogan file does not match approved_text_sha256",
                            )
                        )
                    try:
                        text = raw.decode("utf-8")
                    except UnicodeDecodeError:
                        issues.append(ValidationIssue("SLOGAN_ENCODING", "slogan file is not valid UTF-8"))
                    else:
                        if reg.approved_text is not None and text != reg.approved_text:
                            issues.append(
                                ValidationIssue("SLOGAN_TEXT_MISMATCH", "slogan text differs from approved_text")
                            )
                        checked["slogan_text_length"] = len(text)
            except (json.JSONDecodeError, ValidationError):
                pass

    rep.issues = issues
    rep.checked = checked
    rep.ok = len(issues) == 0
    rep.render_allowed = rep.ok
    return rep


def _resolve_path(path_str: str, repo_root: Path) -> Path:
    p = Path(path_str)
    if p.is_absolute():
        return p
    return (repo_root / path_str).resolve()


def load_bundle(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_report(report: ValidationReport, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report.to_public_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Validate ASIA HOLDINGS input bundle (PR-A)")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    bundle = load_bundle(args.manifest)
    report = validate_input_bundle(bundle, repo_root=args.repo_root)
    write_report(report, args.report)
    if not report.ok:
        raise SystemExit(1)
    print("validation ok", report.run_id)


if __name__ == "__main__":
    main()
