"""Measured design observations -> original CSS candidates -> reviewable feedback.

Discovery is open-ended. Only the small, typed CSS adapter below is automated;
unsupported opportunities survive as backlog and never become executable CSS.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from datetime import UTC, datetime
from hashlib import sha256
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

SCHEMA = "apf.design-observation/v1"
ROLE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
SELECTOR = re.compile(r"^[.#][A-Za-z_][A-Za-z0-9_-]{0,79}$")
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def number(value: object, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("finite number required")
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError("measurement out of bounds")
    return float(value)


def contrast(foreground: str, background: str) -> float:
    def luminance(color: str) -> float:
        if not HEX.fullmatch(color):
            raise ValueError("opaque hex color required")
        channels = [int(color[i:i+2], 16) / 255 for i in (1, 3, 5)]
        channels = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4
                    for c in channels]
        return sum(c * w for c, w in zip(channels, (.2126, .7152, .0722)))
    a, b = sorted((luminance(foreground), luminance(background)))
    return (b + .05) / (a + .05)


def validate_observation(raw: dict) -> dict:
    if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA:
        raise ValueError("unsupported observation")
    source = raw["source"]
    url = urlsplit(source["url"])
    if url.scheme not in ("https", "http") or not url.hostname or url.username or url.password:
        raise ValueError("source URL required; no credentials")
    if not re.fullmatch(r"[0-9a-f]{64}", source["artifact_sha256"]):
        raise ValueError("capture artifact hash required")
    if not source.get("observed_at") or source.get("usage") != "PRINCIPLES_ONLY":
        raise ValueError("capture time and principles-only usage required")
    viewport = raw["viewport"]
    for dimension in ("width", "height"):
        number(viewport[dimension], 240, 8192)
    samples = raw["samples"]
    if not isinstance(samples, list) or not 1 <= len(samples) <= 100:
        raise ValueError("bounded non-empty samples required")
    seen = set()
    for sample in samples:
        role = sample["role"]
        if not ROLE.fullmatch(role) or role in seen:
            raise ValueError("unique semantic role required")
        seen.add(role)
        if not SELECTOR.fullmatch(sample["selector"]):
            raise ValueError("simple class/id selector required")
        for field, low, high in (("font_size_px", 1, 200), ("line_height", .5, 5),
                                 ("gap_px", 0, 200), ("overflow_px", 0, 10000)):
            number(sample[field], low, high)
        contrast(sample["foreground"], sample["background"])
    return raw


DIRECTIONS = {
    "readable": {"title": "가독성 중심", "font": 17, "leading": 1.7, "gap": 20,
                 "summary": "본문과 안내를 넉넉하게 읽는 구성", "tradeoff": "같은 화면의 정보량이 줄어듭니다."},
    "expressive": {"title": "브랜드 표현 중심", "font": 18, "leading": 1.6, "gap": 24,
                   "summary": "큰 글자와 여백으로 핵심 메시지를 강조", "tradeoff": "긴 콘텐츠는 더 많이 스크롤합니다."},
    "mobile": {"title": "모바일 사용 중심", "font": 16, "leading": 1.65, "gap": 16,
               "summary": "작은 화면에서 줄바꿈과 공간 균형을 우선", "tradeoff": "큰 화면에서도 간결한 구성이 유지됩니다."},
    "compact": {"title": "정보 탐색 중심", "font": 16, "leading": 1.5, "gap": 12,
                "summary": "읽기 쉬운 최소 간격으로 정보를 모아 비교", "tradeoff": "여유로운 브랜드 연출은 줄어듭니다."},
}


def propose(reference: dict, baseline: dict, *, target_css: str,
            direction_id: str = "readable") -> dict:
    direction = DIRECTIONS[direction_id]
    reference, baseline = map(validate_observation, (reference, baseline))
    path = Path(target_css)
    if (path.is_absolute() or ".." in path.parts or "\\" in target_css
            or not target_css.startswith("services/") or path.suffix != ".css"):
        raise ValueError("relative services CSS target required")
    if reference["viewport"] != baseline["viewport"]:
        raise ValueError("compare the same viewport")
    reference_roles = {s["role"]: s for s in reference["samples"]}
    changes, rules = [], []
    for own in baseline["samples"]:
        ref = reference_roles.get(own["role"])
        if ref is None:
            continue
        css, reasons = [], []
        # These are our adapters, not copied external selectors, CSS or font assets.
        if contrast(own["foreground"], own["background"]) < 4.5:
            foreground = max(("#172033", "#ffffff"),
                             key=lambda c: contrast(c, own["background"]))
            css.append(f"color: {foreground}")
            reasons.append("contrast")
        if own["font_size_px"] < 16 <= ref["font_size_px"]:
            css.append(f"font-size: {direction['font']}px")
            reasons.append("text_size")
        if own["line_height"] < 1.4 <= ref["line_height"]:
            css.append(f"line-height: {direction['leading']}")
            reasons.append("line_height")
        if own["gap_px"] < 8 <= ref["gap_px"]:
            css.append(f"gap: {direction['gap']}px")
            reasons.append("spacing")
        if own["overflow_px"] > 1 and ref["overflow_px"] <= 1:
            css.extend(("min-width: 0", "max-width: 100%", "overflow-wrap: anywhere"))
            reasons.append("overflow")
        if css:
            rules.append(own["selector"] + " { " + "; ".join(css) + "; }")
            changes.append({"role": own["role"], "criteria": reasons,
                            "reason": "Observed gap; independently authored bounded CSS adapter"})
    css = "/* ARKAON original measured-gap candidate; review required. */\n" + "\n".join(rules)
    backlog = list(reference.get("opportunities", []))
    if not all(isinstance(s, str) and 0 < len(s) <= 2000 for s in backlog) or len(backlog) > 100:
        raise ValueError("bounded textual opportunities required")
    proposal = {
        "schema_version": "apf.design-evolution-proposal/v1",
        "direction_id": direction_id, "direction": direction,
        "reference_digest": digest(reference), "baseline_digest": digest(baseline),
        "baseline": baseline, "target_css": target_css, "changes": changes,
        "candidate_css": css, "candidate_css_sha256": sha256(css.encode()).hexdigest(),
        "discovery_scope": "OPEN_ENDED", "additional_opportunities": backlog,
        "reference_role": "COMPARISON_BASELINE_ONLY",
        "differentiation_required": True,
        "status": "OWNER_APPROVAL_PENDING" if changes else "RESEARCH_REQUIRED",
        "improvement_accepted": False, "merge_allowed": False, "deployment_allowed": False,
    }
    proposal["proposal_digest"] = digest(proposal)
    return proposal


def validate_proposal(proposal: dict) -> None:
    if proposal.get("schema_version") != "apf.design-evolution-proposal/v1":
        raise ValueError("unsupported proposal")
    if digest({k: v for k, v in proposal.items() if k != "proposal_digest"}) != proposal.get(
            "proposal_digest"):
        raise ValueError("proposal tampered")
    if digest(validate_observation(proposal["baseline"])) != proposal["baseline_digest"]:
        raise ValueError("baseline tampered")
    if sha256(proposal["candidate_css"].encode()).hexdigest() != proposal["candidate_css_sha256"]:
        raise ValueError("CSS tampered")


def select_direction(bundle: dict, selection: dict) -> dict:
    if (bundle.get("schema_version") != "apf.design-direction-choices/v1"
            or selection.get("schema_version") != "apf.design-direction-selection/v1"
            or not selection.get("selected_at")):
        raise ValueError("explicit direction selection required")
    matches = [p for p in bundle["choices"]
               if p["proposal_digest"] == selection.get("proposal_digest")
               and p["direction_id"] == selection.get("direction_id")]
    if len(matches) != 1:
        raise ValueError("selection does not identify exactly one direction")
    validate_proposal(matches[0])
    return matches[0]


def materialize(proposal: dict, approval: dict, output: Path) -> Path:
    """Writes only a fresh sandbox artifact; never writes target_css in the repository.

    approval is an explicit local operator attestation, NOT authenticated receipt sync.
    Production runners must additionally use the existing durable approval ledger.
    """
    validate_proposal(proposal)
    if (approval.get("proposal_digest") != proposal["proposal_digest"]
            or approval.get("target_css") != proposal["target_css"]
            or approval.get("decision") != "OWNER_APPROVED"
            or not approval.get("approver") or not approval.get("approved_at")
            or proposal["status"] != "OWNER_APPROVAL_PENDING"):
        raise ValueError("exact proposal approval required")
    output.mkdir(parents=True, exist_ok=True)
    target = output / (proposal["proposal_digest"] + ".css")
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(proposal["candidate_css"])
    return target


def evaluate(proposal: dict, after: dict, *, differentiation: dict) -> dict:
    validate_proposal(proposal)
    after = validate_observation(after)
    baseline = proposal["baseline"]
    if (after["viewport"] != baseline["viewport"]
            or after["source"]["url"] != baseline["source"]["url"]
            or after.get("applied_css_sha256") != proposal["candidate_css_sha256"]):
        raise ValueError("same page/viewport and applied candidate hash required")
    before = {s["role"]: s for s in baseline["samples"]}
    observed = {s["role"]: s for s in after["samples"]}
    if before.keys() != observed.keys():
        raise ValueError("all baseline roles must be observed")
    findings = []
    for role, old in before.items():
        new = observed[role]
        old_ratio = contrast(old["foreground"], old["background"])
        new_ratio = contrast(new["foreground"], new["background"])
        if (new_ratio + .01 < min(old_ratio, 4.5)
                or new["overflow_px"] > max(old["overflow_px"], 1)
                or new["font_size_px"] < old["font_size_px"]
                or new["line_height"] < old["line_height"]):
            findings.append({"role": role, "reason": "REGRESSION"})
    for change in proposal["changes"]:
        sample = observed[change["role"]]
        checks = {"contrast": contrast(sample["foreground"], sample["background"]) >= 4.5,
                  "text_size": sample["font_size_px"] >= 16,
                  "line_height": sample["line_height"] >= 1.4,
                  "spacing": sample["gap_px"] >= 8, "overflow": sample["overflow_px"] <= 1}
        for criterion in change["criteria"]:
            if not checks[criterion]:
                findings.append({"role": change["role"], "reason": criterion})
    # A prose claim cannot automatically prove original composition or visual quality.
    distinct = all(isinstance(differentiation.get(k), str) and differentiation[k].strip()
                   for k in ("user_purpose", "original_composition", "beyond_color", "evidence_ref"))
    passed = bool(proposal["changes"]) and not findings
    return {"schema_version": "apf.design-evolution-evaluation/v1",
            "proposal_digest": proposal["proposal_digest"], "after_digest": digest(after),
            "automated_check_passed": passed, "findings": findings,
            "differentiation": differentiation, "differentiation_documented": distinct,
            "status": "INDEPENDENT_REVIEW_PENDING" if passed and distinct else "FOLLOWUP_REQUIRED",
            "improvement_accepted": False, "visual_review": "NOT_RUN",
            "independent_audit_status": "NOT_RUN", "merge_allowed": False,
            "deployment_allowed": False}


def preview(bundle: dict) -> str:
    """Own neutral content in four sandboxed CSS previews, not external screenshots."""
    cards = []
    for choice in bundle["choices"]:
        samples = choice["baseline"]["samples"]
        elements = []
        base_css = []
        for sample in samples:
            selector = sample["selector"]
            attribute = "class" if selector.startswith(".") else "id"
            label = "우리 사업의 가치를 알기 쉽게 전합니다. 서비스 안내와 문의를 확인하세요."
            elements.append(f'<div {attribute}="{escape(selector[1:])}">{label}</div>')
            base_css.append(selector + " { display: grid; color: " + sample["foreground"]
                            + "; background: " + sample["background"]
                            + f"; font-size: {sample['font_size_px']}px; "
                            + f"line-height: {sample['line_height']}; gap: {sample['gap_px']}px; }}")
        source = ('<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" '
                  "content=\"default-src 'none'; style-src 'unsafe-inline'\">"
                  '<style>body{font-family:system-ui;margin:16px}div{padding:16px;margin:8px 0}'
                  + "\n".join(base_css) + choice["candidate_css"] + '</style>'
                  + "".join(elements))
        direction = choice["direction"]
        cards.append('<article><h2>' + escape(direction["title"]) + '</h2><p>'
                     + escape(direction["summary"]) + '</p><iframe sandbox title="자체 시안" srcdoc="'
                     + escape(source, quote=True) + '"></iframe><p>'
                     + escape(direction["tradeoff"]) + '</p><button data-digest="'
                     + choice["proposal_digest"] + '" data-direction="' + choice["direction_id"]
                     + '">이 방향 선택</button></article>')
    return ("<!doctype html><html lang=ko><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            "<title>디자인 방향 선택</title><style>body{font-family:system-ui;background:#f3f5f8;"
            "color:#172033;margin:24px}main{display:grid;grid-template-columns:repeat(auto-fit,"
            "minmax(280px,1fr));gap:20px}article{background:white;padding:20px;border-radius:16px}"
            "iframe{width:100%;height:280px;border:1px solid #d0d5dd}button{padding:12px 20px}"
            "button[aria-pressed=true]{background:#172033;color:white}</style>"
            "<h1>어떤 방향으로 발전시킬까요?</h1><p>동일한 자체 예시 문구입니다. 실제 전체 화면과 "
            "디자인의 우수성은 추가 검토가 필요합니다. 선택은 병합·배포 승인이 아닙니다.</p><main>"
            + "".join(cards) + "</main><p id=status role=status></p><script>"
            "document.querySelectorAll('button').forEach(b=>b.onclick=()=>{"
            "document.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',x===b));"
            "const r={schema_version:'apf.design-direction-selection/v1',"
            "proposal_digest:b.dataset.digest,direction_id:b.dataset.direction,"
            "selected_at:new Date().toISOString(),merge_allowed:false,deployment_allowed:false};"
            "const u=URL.createObjectURL(new Blob([JSON.stringify(r,null,2)],{type:'application/json'}));"
            "const a=document.createElement('a');a.href=u;a.download='design-selection.json';a.click();"
            "URL.revokeObjectURL(u);document.getElementById('status').textContent="
            "'방향을 선택했습니다. 선택 기록을 저장합니다.';});</script></html>")


def delegated_sandbox(root: Path, bundle: dict, selection: dict) -> str:
    """Standing owner delegation removes per-candidate sandbox approval prompts.

    Direction selection is required, and authorization never grants merge/deploy.
    This adapter only emits independently authored CSS artifacts.
    """
    policy_path = root / "config/arkaon-design-evolution-policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    if (policy.get("schema_version") != "apf.design-evolution-delegation/v1"
            or policy.get("enabled") is not True or policy.get("autonomous_sandbox_css") is not True
            or policy.get("user_direction_selection_required") is not True
            or policy.get("automatic_improvement_acceptance") is not False
            or policy.get("merge_allowed") is not False or policy.get("deployment_allowed") is not False
            or not policy.get("owner") or not policy.get("authorization_basis")):
        raise ValueError("valid sandbox-only standing delegation required")
    proposal = select_direction(bundle, selection)
    directory = root / "state/design-learning/sandbox"
    expected = directory / (proposal["proposal_digest"] + ".css")
    if expected.exists():
        if expected.is_symlink() or sha256(expected.read_bytes()).hexdigest() != proposal["candidate_css_sha256"]:
            raise ValueError("existing sandbox candidate altered")
        return str(expected.relative_to(root))
    attestation = {"proposal_digest": proposal["proposal_digest"], "target_css": proposal["target_css"],
                   "decision": "OWNER_APPROVED", "approver": policy["owner"],
                   "approved_at": "STANDING_DELEGATION:" + digest(policy)}
    target = materialize(proposal, attestation, directory)
    (directory / (proposal["proposal_digest"] + ".authorization.json")).write_text(
        json.dumps({"authorization_kind": "STANDING_SANDBOX_DELEGATION",
                    "policy_digest": digest(policy), "selection": selection,
                    "candidate_css_sha256": proposal["candidate_css_sha256"],
                    "merge_allowed": False, "deployment_allowed": False},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    return str(target.relative_to(root))


def post_improvement_request(root: Path, bundle: dict, evidence_data: dict) -> str:
    from .evidence_capability import CollectedEvidence, EvidenceKind
    from .self_improvement import detect_self_improvement, post_self_improvement

    data = dict(evidence_data)
    data["kind"] = EvidenceKind(data["kind"])
    evidence = CollectedEvidence(**data)
    now = datetime.now(UTC)
    changes = bundle["choices"][0]["changes"]
    opportunities = bundle["choices"][0]["additional_opportunities"]
    scope = {"measured_gaps": changes, "additional_research": opportunities,
             "capability_comparisons": bundle.get("capability_comparisons", []),
             "implementation_feedback": bundle.get("evaluation")}
    request = detect_self_improvement(
        request_id="design-" + bundle["job_digest"][:32], now=now,
        intent_dna="외부에서 더 나은 방식을 발견하고 독자적 디자인·기능 향상으로 연결",
        capability_gap=json.dumps(scope, ensure_ascii=False, sort_keys=True),
        evidence_refs=("state/design-learning/" + bundle["job_digest"] + ".json",),
        proposed_change="4개 개선 방향 중 사용자 선택 후 승인 범위 sandbox 구현. "
                        "미지원 기능도 별도 개선 과제로 유지하고 참고 디자인을 그대로 적용하지 않음.",
        expected_benefit="같은 과제에서 현재 기능의 부족함을 줄임. 효과는 구현·비교 후 판단.",
        risks=("문구·브랜드 훼손 및 반응형 회귀", "외부 관찰의 맥락·권리·측정 오류"),
        validation_plan=("동일 콘텐츠·viewport 전후 비교 및 참고 기준선 비교",
                         "선택한 방향과 CSS digest 결속; 원본 구성·색상 외 개선 근거 검토",
                         "모바일·성능·저장 회귀시험; 실패는 다음 개선요청으로 환류",
                         "아르카온 1차 검증과 에테르니언 독립 감사 분리; 자동 최종 인정 금지"),
        evidence=evidence,
    )
    _, path = post_self_improvement(request, inbox_root=root / "inbox", now=now)
    return str(path.relative_to(root))


def cycle(root: Path) -> dict:
    """Consume bounded observation jobs; malformed jobs never starve later jobs."""
    inbox = root / "inbox/design-learning"
    out = root / "state/design-learning"
    result = {"proposed": 0, "duplicate": 0, "blocked": []}
    if not inbox.is_dir():
        return result
    out.mkdir(parents=True, exist_ok=True)
    processed = out / "processed"
    processed.mkdir(exist_ok=True)
    attempted = 0
    for path in sorted(inbox.glob("*.json")):
        if attempted >= 30:
            break
        receipt = None
        try:
            if path.is_symlink() or path.stat().st_size > 2_000_000:
                raise ValueError("unsafe job file")
            raw = path.read_bytes()
            receipt = processed / (sha256(raw).hexdigest() + ".json")
            if receipt.exists():
                result["duplicate"] += 1
                continue
            attempted += 1
            job = json.loads(raw.decode("utf-8"))
            choices = [propose(job["reference"], job["baseline"],
                               target_css=job["target_css"], direction_id=key)
                       for key in DIRECTIONS]
            comparisons = job.get("capability_comparisons", [])
            if not isinstance(comparisons, list) or len(comparisons) > 100:
                raise ValueError("bounded capability comparisons required")
            for comparison in comparisons:
                if not isinstance(comparison, dict) or not all(
                    isinstance(comparison.get(k), str) and 0 < len(comparison[k]) <= 2000
                    for k in ("capability", "current", "external", "implementation_needed",
                              "acceptance", "evidence_ref")
                ):
                    raise ValueError("current/external gap and implementation/evidence required")
            bundle = {"schema_version": "apf.design-direction-choices/v1",
                      "job_digest": digest(job), "selection_required": True,
                      "capability_comparisons": comparisons,
                      "choices": choices, "automatic_selection_allowed": False}
            if job.get("after") is not None:
                selected = select_direction(bundle, job.get("selection", {}))
                bundle["evaluation"] = evaluate(selected, job["after"],
                                                differentiation=job.get("differentiation", {}))
            target = out / (bundle["job_digest"] + ".json")
            try:
                with target.open("x", encoding="utf-8") as stream:
                    json.dump(bundle, stream, ensure_ascii=False, indent=2)
                (out / (bundle["job_digest"] + ".html")).write_text(
                    preview(bundle), encoding="utf-8")
                result["proposed"] += 1
            except FileExistsError:
                if json.loads(target.read_text(encoding="utf-8")) != bundle:
                    raise ValueError("existing proposal differs")
                result["duplicate"] += 1
            if job.get("evidence") is not None:
                request_path = post_improvement_request(root, bundle, job["evidence"])
            else:
                request_path = None
            sandbox_path = None
            if job.get("selection") is not None:
                sandbox_path = delegated_sandbox(root, bundle, job["selection"])
            receipt.write_text(json.dumps({"status": "PROPOSED", "request_path": request_path,
                                           "sandbox_path": sandbox_path,
                                           "evidence_review_required": request_path is None}),
                               encoding="utf-8")
        except (ValueError, KeyError, TypeError, OSError, AttributeError) as exc:
            result["blocked"].append({"file": path.name, "reason": str(exc)})
            if receipt is not None:
                receipt.write_text(json.dumps({"status": "BLOCKED", "file": path.name,
                                               "reason": str(exc)}), encoding="utf-8")
    (out / "latest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Design observations to bounded original CSS candidates")
    parser.add_argument("--foundry-root", type=Path, default=Path("."))
    args = parser.parse_args()
    print(json.dumps(cycle(args.foundry_root), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
