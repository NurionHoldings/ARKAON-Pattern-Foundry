"""Export a self-contained, reviewable MACOL browser application draft."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from apf.call_template import CallTemplateRequest, build_call_template

SEED = Path(__file__).with_name("macol_seed")
PERSONAL_CALL = "개인적인 통화"
FILES = (
    "app.py", "index.html", "manifest.webmanifest", "icon.svg", "requirements.txt",
    "Dockerfile", "test_app.py", ".github/workflows/test.yml",
)


def export_macol(request: CallTemplateRequest, output: Path) -> Path:
    """Write a fresh, standalone draft directory; never overwrite existing work."""
    asset = build_call_template(request)
    purposes = list(asset.purpose_prompts)
    if request.allow_call_request and PERSONAL_CALL not in purposes:
        purposes.append(PERSONAL_CALL)
    if not request.allow_call_request and PERSONAL_CALL in purposes:
        raise ValueError("PERSONAL_CALL_REQUIRES_ALLOW_CALL_REQUEST")
    if len(purposes) > 8:
        raise ValueError("TOO_MANY_MENUS_FOR_ROOM")
    if any(len(title) > 80 for title in purposes):
        raise ValueError("MENU_TITLE_TOO_LONG_FOR_ROOM")
    if output.exists():
        raise FileExistsError(f"OUTPUT_EXISTS: {output}")
    rendered: dict[str, str] = {}
    for relative in FILES:
        source = SEED / relative
        content = source.read_text(encoding="utf-8")
        if relative == "index.html":
            content = content.replace("__MACOL_DISPLAY_NAME__", html.escape(asset.display_name, quote=True))
            content = content.replace("__MACOL_INTRODUCTION__", html.escape(asset.introduction))
            content = content.replace("__MACOL_MENU_TITLES__", "&#10;".join(
                html.escape(title) for title in purposes
            ))
        elif relative == "manifest.webmanifest":
            manifest = json.loads(content)
            manifest["name"] = f"마컬 · {asset.display_name}의 전화응대"
            content = json.dumps(manifest, ensure_ascii=False) + "\n"
        elif relative == "test_app.py":
            content = content.replace('"__MACOL_TEST_PURPOSE__"', repr(purposes[0]))
            content = content.replace(
                '"__MACOL_TEST_CALL__"',
                repr(PERSONAL_CALL if request.allow_call_request else purposes[0]),
            )
        rendered[relative] = content
    rendered["template.json"] = asset.model_dump_json(indent=2) + "\n"
    rendered["README.md"] = (
        f"# {asset.display_name}의 마컬 앱 초안\n\n"
        f"ARKAON이 `{asset.content_digest}`에서 생성한 독립 브라우저 앱 초안입니다. "
        "010 발신 감지·발신자 화면 자동 열림·실회선 ARS는 구현되지 않았습니다. "
        "방 생성과 초대 링크는 메뉴/브라우저 음성 수동 시험 전용입니다.\n\n"
        "`python -m pip install -r requirements.txt pytest httpx` 후 "
        "`python -m pytest -q`로 검사합니다. "
        "`MACOL_OWNER_KEY`를 별도로 설정하고 `uvicorn app:app --host 127.0.0.1 --port 8000`"
        "으로 로컬 시험을 실행할 수 있습니다. 공개 배포에는 HTTPS, 단일 worker, "
        "실제 기기 시험, 소유자 인증 보강이 필요합니다.\n"
    )
    output.mkdir(parents=True, exist_ok=False)
    for relative, content in rendered.items():
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="ARKAON standalone MACOL app draft export")
    parser.add_argument("--request", type=Path, required=True, help="CallTemplateRequest JSON")
    parser.add_argument("--output", type=Path, required=True, help="New output directory")
    args = parser.parse_args()
    request = CallTemplateRequest.model_validate_json(args.request.read_text(encoding="utf-8"))
    print(export_macol(request, args.output))


if __name__ == "__main__":
    main()
