# 외부 학습 후보 → 요소 편집 sandbox

PR #122의 element_editing 후보를 #121의 ab3a2a9e7f6fe7b473403786b84b66270eff664c
기준 UI에서 별도 브랜치로 구현한다. 에테르니언 직접 보완이며 아르카온 1차 검증·별도 근거의
독립 감사 완료로 표시하지 않는다. 원래 #121 브랜치는 변경하지 않는다.

심벌 크기(40–100), 심벌/글자 간격(8–64), 글자 간격(0–4), 좌/중앙/우 정렬을 조절한다.
기존 3종 로고와 새 6종 방향 모두 같은 요소 모델 v1을 사용한다. 가로/세로/심벌별 SVG를
생성하며 긴 상호는 줄을 나누고 필요한 viewBox 높이를 계산한다. 워드마크에는 심벌 크기와
간격을 적용하지 않고 심벌만 보기에서는 이름을 유지한다. legacy 초안은 기본값을 적용한다.

전체 편집값 snapshot을 10단계 유지하고 undo/redo를 제공한다. 새 분기 편집 시 redo를
제거한다. 값/모델 버전은 기존 brief에 저장한다. 편집 이력은 현재 화면 세션에만 유지한다.
직접 수정한 문구·가상 예시 표시·project id와 기존 초안 저장 경로를 보존한다.

검증: Node 16개 시험에서 10단계 undo/redo 후 값·SVG 해시 동일성, 이력 독립 복사·상한,
이전 draft 기본값·숫자 경계·60자 한글 내용 보존·저장용 JSON 복원을 확인한다.
이는 실제 브라우저의 시각 잘림/접근성·저장 완주를 증명하지 않는다.

`node tools/measure-brand-elements.cjs --baseline-dir <기준체크아웃> --candidate-dir <후보체크아웃> --baseline-sha <40자리> --candidate-sha <40자리> --out <증거폴더>`

고정된 태양광/카페/개인 디자이너 가상 brief 3건으로 전후 HTML 해시와 Node render 100회
중앙값/p95를 기록한다. Node 렌더 시간은 브라우저 입력 반응시간이 아니다. manifest의
12개 viewport 비교·브라우저 undo/redo·저장/재오픈·독립 감사·아르카온 1차 검증은
미실행을 NOT_RUN으로 보존한다. CI run ID는 실제 실행 확인 후 별도 결속한다.

개선 인정은 false다. 운영 worker 연결·QR·인쇄·결제·외부 자산 채택·자동 승격은 범위 밖이다.
병합·운영반영 HOLD 유지. 롤백은 sandbox PR revert이며 저장한 프로젝트를 삭제하지 않는다.


## Netlify와 분리한 브라우저 시험 환경

`tools/test-brand-browser.cjs`는 baseline/candidate 저장소를 127.0.0.1 임시 포트에서
각각 정적 제공한다. 운영 서버·계정·API·배포 설정을 변경하지 않는다.
3개 고정 brief × 4개 실제 Chromium viewport × 전후 2종 = 24회 렌더를 수행하며,
외부 편집기 문구를 가져오지 않고 가상 입력만 사용한다. 실제 폼 조작으로 같은 brief를
입력하고 선택한 지평선 방향을 비교한다. HTML/입력값/결과물/PNG와 SHA-256을 남긴다.
후보 12개 조건의 가로 넘침·SVG 글자 경계·줄 겹침이 없을 때 자동 comparison을 PASS로
한다. baseline의 문제는 별도 기록하며 baseline FAIL을 숨기지 않는다.

10개 변경 → undo 10회 → redo 10회의 입력값·SVG 해시를 비교하고 저장 후 같은 브라우저
context의 새 탭에서 복원을 확인한다. 이력의 입력값·해시는 browser-manifest에 기록한다.
글꼴/카드의 모든 시각 겹침, 사용성 선호, 실기기, 전체 접근성은 자동 합격으로 인정하지 않는다.
visual_human_review/아르카온 1차 검증/독립 감사는 NOT_RUN을 유지한다.

실행 예시:
`NODE_PATH=<playwright설치폴더>/node_modules node tools/test-brand-browser.cjs --baseline-dir <기준체크아웃> --candidate-dir <후보체크아웃> --baseline-sha ab3a2a9e7f6fe7b473403786b84b66270eff664c --candidate-sha <실행한40자리SHA> --out <출력폴더>`

`.github/workflows/brand-browser-regression.yml`은 PR에서 고정 baseline과 PR head를 각각
checkout하고 격리된 Playwright 1.62.1/Chromium으로 실행한다. secrets·배포 권한 없이
contents:read만 사용하며 실패 시에도 manifest/DOM/스크린샷을 14일 artifact로 보존한다.
기존 docs/evidence/brand-elements/manifest.json의 NOT_RUN은 실행 전 수동 승격하지 않는다.
실제 새 workflow 실행에서 나온 browser-manifest의 tested SHA/CI run과 결과를 별도로
결속한 후만 자동 검사 상태를 갱신한다. Netlify preview BLOCKED는 독립 상태로 유지한다.
