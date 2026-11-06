# 외부 관찰에서 독자적 디자인·기능 개선으로

## 사용자 의도

최인석 사용자의 2026-11-06 지시: 기능 향상의 탐색 범위를 제한하지 않는다. 외부의 더 나은 기능·CSS·배경·서체·구성을 발견하고 현재 기능과의 차이를 개선요청으로 전환한다. 외부 결과를 그대로 적용하는 대신 그 기준선에서 우리 목적에 맞는 독자적 구성을 제시하고 향상을 검증한다. 4개 방향 중 사용자가 선택하고, 이후의 sandbox 구현·시험·보완은 위임 범위에서 매번 승인을 다시 묻지 않고 진행한다. 병합·운영반영 승인은 별도다.

## 실제 구현 범위

- `apf.design_learning.cycle`이 관찰 작업을 읽고 4개 CSS 후보·선택 미리보기를 생성한다. `collector_service`의 매 수집 주기와 `--once`에 연결했다. 작업이 없으면 기존 동작을 유지한다.
- 외부/현재 화면의 동일 역할·viewport 측정치를 비교한다. 현 adapter는 대비, 작은 글자, 행간, 간격, 넘침을 다룬다. 외부 CSS·선택자·서체 파일을 복사하지 않고 자체 CSS 규칙을 생성한다.
- 가독성·브랜드 표현·모바일·정보 탐색 방향을 제공한다. 현재 방향 차이는 서체 크기·행간·간격 중심의 **초기 규칙 adapter**다. 완성된 네 종류의 독창적 레이아웃이나 범용 AI 디자인 엔진이라고 표시하지 않는다. 차이가 부족하면 보완 과제다.
- 미지원 새 기능은 `capability_comparisons`와 `opportunities`로 보존한다. discovery는 개방적이며 현재 adapter의 기능 수가 학습·제안 범위를 제한하지 않는다.
- 근거가 기존 evidence capability 정책을 만족하면 `detect_self_improvement` → `post_self_improvement`를 사용해 **기존 relay가 읽는 `inbox/self-improvement/`**에 요청을 게시한다. 근거가 없으면 후보는 연구 상태로 남으며 권한·검증을 꾸며내지 않는다.
- 선택 + config의 상시 위임 정책이 있으면 선택한 CSS를 `state/design-learning/sandbox/`에 자동 생성한다. 같은 파일은 재생성하지 않고 해시를 확인한다. 운영 파일은 수정하지 않는다. 이 경로는 기존 durable GitHub 승인 동기화 원장을 대체하지 않는다.
- `after` 관찰과 실제 적용 CSS hash를 넣으면 전후 검사·회귀·독자화 설명을 평가한다. 미달은 `FOLLOWUP_REQUIRED`, 개선요청에 환류한다. 자동 통과도 `improvement_accepted=false`; 독립 감사·시각 심사 전 최종 인정은 불가하다.

## 입력·출력

`inbox/design-learning/*.json`:

```json
{
  "reference": {"schema_version": "apf.design-observation/v1", "source": {}, "viewport": {}, "samples": []},
  "baseline": {"schema_version": "apf.design-observation/v1", "source": {}, "viewport": {}, "samples": []},
  "target_css": "services/example.css",
  "capability_comparisons": [{
    "capability": "문장으로 요소 수정", "current": "수치 입력만 지원",
    "external": "문장 수정 지원", "implementation_needed": "의도 해석·요소 모델·undo 연결",
    "acceptance": "다른 필드 보존 및 undo/redo 실브라우저 검증", "evidence_ref": "관찰 자료 경로"
  }]
}
```

위 예시는 구조 설명이며 실행용 완성 데이터가 아니다. 실행 데이터는 `tests/test_design_learning.py`의 합성 fixture와 `tests/design-learning-browser.test.cjs` 참고. `source`: url, observed_at, artifact_sha256, usage=PRINCIPLES_ONLY. 각 sample: role, 단일 class/id selector, font_size_px, line_height 비율, gap_px, foreground/background 불투명 #RRGGBB, overflow_px.

`evidence`는 기존 `CollectedEvidence` 필드다. 수집 URL이나 자체 캡처만으로 independently_verified·권리 확인을 true로 올리지 않는다. 검토된 수집 원장의 판정을 연결해야 한다.

선택 화면은 `state/design-learning/<job_digest>.html`. 버튼은 digest가 결속된 `design-selection.json`을 내려받는다. 이 기록을 job의 `selection`으로 넣으면 다음 수집 주기에 해당 방향만 sandbox로 생성한다. **운영 Console로 선택을 인증·자동 업로드하는 API는 미연결**이며 선택 기록은 전자서명/병합승인 receipt가 아니다. 정책은 로컬 신뢰 설정이다.

```sh
python -m apf.design_learning --foundry-root /path/to/foundry
# 보관된 HTML의 오프라인 브라우저 관찰 (Playwright 설치 환경)
node tools/capture-design-observation.cjs archived.html roles.json observation.json 390 https://source.example/page
# CSS 적용 후 동일 페이지 관찰
node tools/capture-design-observation.cjs baseline.html roles.json after.json 390 http://localhost:8080/demo.html candidate.css
```

캡처는 **이미 수집한 로컬 HTML**만 렌더하며 HTTP 요청은 차단한다. 외부 사이트를 스스로 검색·수집하거나 출처를 인증하지 않는다. 외부 파일 폰트·스타일 누락, 복합 배경, normal 행간 등은 별도 검토 대상이다. screenshot/HTML/CSS hash는 캡처 바이트의 무결성 근거일 뿐 원격 출처 진위를 증명하지 않는다. 기하검사도 전수 접근성·미적 우수성 판정이 아니다.

## 다음 연결과 완료로 보지 않는 것

1. 운영 수집물에서 실제 브라우저 관찰·capability 비교를 생성하는 모델/worker 연결.
2. 4개 완성 시안 및 인증된 사용자 선택을 Console에 연결.
3. 미지원 기능의 일반 코드 생성 worker 연결. 현재 자동 구현 adapter는 CSS 아티팩트 범위다.
4. 승인된 후보의 실제 제품·모바일·실기기·성능·회귀 시험과 독립 감사.
5. 최종 승인 후 병합·운영반영. 이 PR에서 수행하지 않는다.

“스스로 발전 완료”, “실제 외부 학습 효과 입증”, “완전 자율 개발”로 표시하지 않는다. 학습→후보→요청→선택→sandbox CSS→관찰 환류의 연결 및 검증 기반을 구현한 단계다. 합성 fixture 시험과 실제 외부 자료 학습을 구분한다.


## 측정 기준의 의미

색 대비는 [W3C 일반 텍스트 대비 설명](https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html)을 참고한다. 현재 16px·행간 1.4·gap 8px 경계는 adapter의 제품 휴리스틱이며 WCAG 준수 인증 기준이 아니다. 특히 행간 기본값 1.4/1.6을 접근성 인증으로 표현하지 않는다. 측정 통과가 참조 디자인보다 미적으로 우수함을 증명하지 않는다. 원본 구성과 사용자 목적·실화면을 독립 검토해야 한다.
