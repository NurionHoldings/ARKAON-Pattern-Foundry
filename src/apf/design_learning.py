"""Public design documentation -> evidence-bound implementation candidates.

A product claim is not an executed benchmark or an accepted lesson. No code runs
from external content, and no task is automatically merged or deployed.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

ALLOWED_HOSTS = frozenset({'www.miricanvas.com', 'help.miricanvas.com'})
MAX_BYTES = 500_000
PLANS = {
    'element_editing': {
        'signals': [r'간격|spacing', r'정렬|alignment', r'크기|resize'],
        'title': '로고 글자·심벌의 크기와 간격을 직접 조절',
        'implementation': '독립 SVG 요소 모델과 크기·간격·정렬 조절, 실행 취소/다시 실행을 구현한다.',
        'paths': ['services/brand-studio.js', 'services/brand-concepts.js'],
        'acceptance': ['같은 로고의 심벌 크기·문자 간격을 각각 변경하고 저장/재오픈해 유지',
                       '실행 취소/다시 실행 10회 후 요소 값과 SVG 동일',
                       '긴 한글 상호 60자에서 잘림·겹침 0건'],
    },
    'brand_kit': {
        'signals': [r'로고|logo', r'색상|color|palette', r'글꼴|font'],
        'title': '로고·명함·홈페이지에 같은 브랜드 설정 적용',
        'implementation': '사용자가 만든 로고·색상·허용 글꼴 설정을 버전 있는 브랜드 키트로 저장한다.',
        'paths': ['services/services.js', 'services/brand-studio.js', 'services/studio.js'],
        'acceptance': ['한 브랜드의 로고·명함·홈페이지에 같은 키트 버전·색상 적용',
                       '키트 수정 전후 버전을 비교하고 이전 버전 복원',
                       '다른 사용자의 키트 접근을 거절하는 API 시험'],
    },
}


def digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def validate_url(url: str) -> None:
    parsed = urlparse(url)
    if (parsed.scheme != 'https' or parsed.hostname not in ALLOWED_HOSTS
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise ValueError('SOURCE_URL_NOT_ALLOWED')


class _Redirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_public(url: str) -> bytes:
    validate_url(url)
    request = Request(url, headers={'User-Agent': 'ARKAON-Public-Design-Research/1.0'})
    with build_opener(_Redirects()).open(request, timeout=15) as response:
        if response.headers.get_content_type() not in ('text/html', 'text/plain'):
            raise ValueError('SOURCE_CONTENT_TYPE')
        payload = response.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise ValueError('SOURCE_TOO_LARGE')
    return payload


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def observe(url: str, payload: bytes, now: datetime) -> dict:
    validate_url(url)
    if now.tzinfo is None:
        raise ValueError('TIMEZONE_REQUIRED')
    if len(payload) > MAX_BYTES:
        raise ValueError('SOURCE_TOO_LARGE')
    parser = _VisibleText()
    parser.feed(payload.decode('utf-8', errors='strict'))
    text = ' '.join(parser.parts)
    features = [key for key, plan in PLANS.items()
                if all(re.search(signal, text, re.IGNORECASE) for signal in plan['signals'])]
    return {'source_url': url, 'observed_at': now.isoformat(),
            'source_digest': sha256(payload).hexdigest(), 'features': features,
            'evidence_kind': 'PUBLIC_DOCUMENTATION_SIGNALS',
            'executed_product_test': False}


def build_report(observations: list[dict], baseline_ref: str) -> dict:
    if not re.fullmatch(r'[0-9a-f]{40}', baseline_ref):
        raise ValueError('FULL_BASELINE_COMMIT_REQUIRED')
    tasks = []
    for feature, plan in PLANS.items():
        evidence = [o for o in observations if feature in o['features']]
        if not evidence:
            continue
        task = {'feature': feature, **{k: v for k, v in plan.items() if k != 'signals'},
                'baseline_commit': baseline_ref, 'baseline_status': 'MEASUREMENT_REQUIRED',
                'sources': evidence, 'status': 'ETERNIAN_REVIEW_REQUIRED',
                'comparison_plan': {
                    'briefs': ['태양광 시공업체', '동네 카페', '개인 디자이너'],
                    'widths': [360, 390, 768, 1440],
                    'required_evidence': ['동일 brief 해시', 'baseline/candidate 커밋 및 결과물 해시',
                                          '전후 화면', '작업 완주 단계·시간·오류', '회귀시험',
                                          '에테르니언 독립 검토', '사용자 승인'],
                },
                'improvement_accepted': False, 'automatic_implement_allowed': False,
                'production_change_allowed': False}
        # Transport dedup uses the same sources + task + baseline, not fetch time.
        task['task_id'] = 'design-' + digest([feature, baseline_ref, plan,
                                             sorted(o['source_url'] for o in evidence)])[:24]
        task['scope_digest'] = digest({'paths': plan['paths'], 'acceptance': plan['acceptance']})
        task['task_digest'] = digest(task)
        tasks.append(task)
    return {'schema_version': 'apf.design-learning-report/v1', 'tasks': tasks,
            'observations': observations, 'learning_status': 'CANDIDATE_EVIDENCE_ONLY',
            'improvement_accepted': False}


def run(root: Path, sources: list[str], baseline_ref: str, now: datetime, *,
        fetch=fetch_public, dry_run: bool = True) -> dict:
    if len(sources) > 5 or len(sources) != len(set(sources)):
        raise ValueError('SOURCE_COUNT_OR_DUPLICATE')
    observations, failures = [], []
    for url in sources:
        try:
            validate_url(url)
            observations.append(observe(url, fetch(url), now))
        except (ValueError, OSError, UnicodeError) as error:
            failures.append({'source_url': url, 'error': type(error).__name__})
    report = build_report(observations, baseline_ref)
    report['failures'] = failures
    report['dry_run'] = dry_run
    if not dry_run:
        out = root / 'state' / 'design-learning'
        out.mkdir(parents=True, exist_ok=True)
        for task in report['tasks']:
            packet = {'schema_version': 'apf.design-learning-packet/v1',
                      'packet_id': task['task_id'], 'stage': 'ETERNIAN_REVIEW',
                      'packet_kind': 'DESIGN_LEARNING_IMPLEMENTATION_CANDIDATE',
                      'platform_id': 'ARKAON_FOUNDRY', 'summary': task['title'],
                      'created_at': now.isoformat(), 'task': task,
                      'automatic_implement_allowed': False, 'production_change_allowed': False}
            inbox = root / 'inbox' / 'eternian-review'
            inbox.mkdir(parents=True, exist_ok=True)
            path = inbox / f"{task['task_id']}.json"
            try:
                with path.open('x', encoding='utf-8') as file:
                    json.dump(packet, file, ensure_ascii=False, indent=2)
            except FileExistsError:
                pass  # Preserve reviewer decisions and avoid duplicate packets.
        report_path = out / f'{digest(report)}.json'
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report
