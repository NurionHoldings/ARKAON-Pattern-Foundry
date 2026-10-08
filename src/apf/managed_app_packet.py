"""Validate a management-app intake packet and emit a bounded build plan."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REQUIRED_TOP = (
    "application", "workflows", "data_entities", "business_rules", "source_systems",
    "security", "privacy", "analytics", "deployment", "acceptance_criteria",
    "open_questions", "approval",
)
MODES = {"manual", "csv", "rest-pull", "webhook"}
BUILD_PHASES = (
    ("1. 업무 이해", "요청자·실무자·업무 흐름·용어·성공 기준을 확인하고 가정과 미해결 질문을 기록"),
    ("2. 데이터와 권한", "데이터 관계, 변경 이력, 중복방지 키, 업체별 접근범위, 보존기간을 설계"),
    ("3. 외부 자료 연결", "업체 공식 문서·동의·샌드박스를 확보하고 CSV/API 어댑터와 필드 변환을 시험"),
    ("4. 한 흐름 구현", "권한 확인부터 원장 저장, 예외 확인, 승인·내보내기까지 작은 업무 흐름을 구현"),
    ("5. 분석과 검증", "근거가 보이는 요약을 만들고 데이터 격리·중복·환불·계산·장애 테스트 실행"),
    ("6. 운영 인계", "컨테이너·HTTPS·비밀키·백업복구·실무자 매뉴얼과 근거가 연결된 PR 작성"),
)


def validate_packet(packet: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if packet.get("schema_version") != "apf.managed-app-intake/v1":
        errors.append("schema_version은 apf.managed-app-intake/v1이어야 합니다.")
    for key in REQUIRED_TOP:
        if key not in packet:
            errors.append(f"필수 영역이 없습니다: {key}")
    app = packet.get("application", {})
    if not isinstance(app, dict) or not all(str(app.get(k, "")).strip() for k in ("name", "owner", "business_goal")):
        errors.append("application.name/owner/business_goal을 채워야 합니다.")
    for key in ("workflows", "data_entities", "business_rules", "source_systems", "analytics", "acceptance_criteria", "open_questions"):
        if not isinstance(packet.get(key), list) or not packet.get(key):
            errors.append(f"{key}는 한 개 이상 항목이 있는 목록이어야 합니다.")
    security = packet.get("security", {})
    if not isinstance(security, dict) or not isinstance(security.get("tenant_isolation"), bool):
        errors.append("security.tenant_isolation에 업체 분리가 필요한지 true/false로 명시해야 합니다.")
    if not isinstance(security, dict) or security.get("production_change_allowed") is not False:
        errors.append("production_change_allowed는 자동화 단계에서 false여야 합니다.")
    approval = packet.get("approval", {})
    if not isinstance(approval, dict) or approval.get("production_deploy_authorized") is not False:
        errors.append("운영 배포 승인 여부를 명시하고, 기본 템플릿에서는 false로 둬야 합니다.")
    seen: set[str] = set()
    for i, source in enumerate(packet.get("source_systems", []), start=1):
        if not isinstance(source, dict):
            errors.append(f"source_systems[{i}]는 객체여야 합니다.")
            continue
        sid = str(source.get("id", "")).strip()
        if not sid or sid in seen:
            errors.append(f"source_systems[{i}]의 id가 비었거나 중복입니다.")
        seen.add(sid)
        if source.get("mode") not in MODES:
            errors.append(f"source_systems[{i}] mode는 {', '.join(sorted(MODES))} 중 하나여야 합니다.")
        if source.get("enabled") is True and source.get("mode") in {"rest-pull", "webhook"}:
            for field in ("owner_authorized", "official_docs_ref", "stable_event_id_field", "credential_ref"):
                if not source.get(field):
                    errors.append(f"활성 API 커넥터 source_systems[{i}]에 {field} 증거/설정이 필요합니다.")
    return errors


def render_plan(packet: dict[str, Any]) -> str:
    name = packet.get("application", {}).get("name", "신규 관리 프로그램")
    questions = packet.get("open_questions", [])
    bullets = "\n".join(f"- [ ] {phase}: {detail}" for phase, detail in BUILD_PHASES)
    qs = "\n".join(f"- {q}" for q in questions) or "- 없음"
    return f"# {name} · ARKAON 구현 계획 초안\n\n## 개발 단계\n\n{bullets}\n\n## 업체·운영자에게 확인할 질문\n\n{qs}\n\n## 변경 경계\n\n이 계획은 구현 제안입니다. 운영 배포, 실제 자격증명 주입, 원장 이월·정정 정책과 잠금 Intent_DNA 변경은 각각 승인된 별도 게이트를 통과해야 합니다.\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="관리 프로그램 요구사항 패킷 검사와 개발계획 생성")
    parser.add_argument("packet", type=Path, help="managed-app-intake JSON")
    parser.add_argument("--plan-out", type=Path, help="검증 성공 시 계획 문서를 저장할 경로")
    args = parser.parse_args()
    try:
        packet = json.loads(args.packet.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"패킷을 읽을 수 없습니다: {exc}", file=sys.stderr)
        return 2
    if not isinstance(packet, dict):
        print("최상위 JSON은 객체여야 합니다.", file=sys.stderr)
        return 2
    errors = validate_packet(packet)
    if errors:
        for error in errors:
            print(f"오류: {error}", file=sys.stderr)
        return 1
    plan = render_plan(packet)
    if args.plan_out:
        args.plan_out.parent.mkdir(parents=True, exist_ok=True)
        args.plan_out.write_text(plan, encoding="utf-8")
        print(f"요구사항 검증 통과. 개발 계획 초안 생성: {args.plan_out}")
    else:
        print("요구사항 검증 통과.\n")
        print(plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
