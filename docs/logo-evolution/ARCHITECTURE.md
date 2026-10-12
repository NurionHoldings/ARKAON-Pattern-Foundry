# ARKAON Logo Evolution Engine — 설계 v1

## 목적
사용자가 ARKAON에서 **승인한 로고**를 원본 그대로 보존하고, 레벨 1~5 슬라이더를 통해 로고의 구성 요소에 적합한 애니메이션 기술을 단계적으로 추가한다. 홍채 형태 자체를 복제하지 않는다. 사용자-ARKAON 공동작업 흐름에서 각 단계 미리보기/승인/되돌리기를 제공한다.

## UX
1. 로고 생성 → 원본 승인(버전 v0, immutable)
2. **로고 고도화** 탭 → Level 1~5 슬라이더(기본 Level 1) → 적합 기술 표시
3. 표현 성향(자연/균형/강렬)과 부품별 효과 ON/OFF → 실시간 경량 미리보기
4. 변경 비교(원본/현재), 예상 시간·비용·지원 여부 확인
5. 사용자가 확정한 경우에만 렌더링 요청 → 작업 진행 상태 → MP4/WebM/PNG 다운로드
6. 결과물 버전 관리 및 이전 설정 복구

## 레벨 정책 (기본값, 효과 개수 보장 아님)
- L1 Original: 원본 정적 로고. 효과 없음.
- L2 Color: 요소별 색상 전이/순차 점등.
- L3 Motion: 이동 반사광/텍스트 순차 등장/선 경로 점등.
- L4 Depth: 글자 1.10x pop, 2D 깊이 근사, 재질별 반사, 중심-외곽 감쇠.
- L5 Cinematic: 복합 타임라인, 부품 간 연동, 고품질 마스크·렌더 검증.
상위 레벨은 하위 레벨의 **지원 가능한** 효과를 포함하며, 불필요하거나 불가능한 효과는 제외한다. '강렬함'은 레벨과 독립된 intensity preset.

## 분석 및 적합성
- 입력: raster PNG(투명 권장), SVG(안전한 파싱 필요), 편집 가능한 벡터 레이어(최상).
- 세그먼트: 글자/기하학 선/심볼/금속성 면/캐릭터 부분/기타.
- 효과 capability: text_stagger, color_shift, outline_neon, trace_current, specular_sweep, radial_wave, depth_pop, facial_motion.
- 자동 분류 결과에는 confidence를 표시; 낮으면 사용자에게 영역 지정 요청.
- 실제 3D geometry 또는 금속 재질을 추론했다고 주장하지 않음. 2D 근사와 실제 3D 렌더러 구분.
- 로고별 허용 효과를 사용자에게 설명하고, 효과가 맞지 않으면 대체안을 제공.
- 얼굴/인물/브랜드 표식의 의미를 변경하지 않는 것이 기본.

## 렌더 아키텍처
Frontend Slider → POST /api/logo-evolution/preview (lightweight) → POST /api/logo-evolution/render (authenticated) → job queue → worker → artifact store.
API routes are **proposed contracts**, not currently implemented. Frontend never trusts client-only payment/ownership flags.
- preview debounce 250ms, stale request cancellation, quality tier low, request hash caching.
- final render asynchronous job; dedupe by immutable input hash + config hash; retries safe/idempotent.
- job status: queued → analyzing → previewing → rendering → validating → completed/failed/cancelled.
- preview watermark policy; paid download enforced by server entitlement verification.
- assets stored private by default; signed time-limited downloads.
- avoid running arbitrary SVG scripts or shell interpolation; sanitize SVG, restrict codecs, input dimensions, duration, upload size.
- log per-job pipeline version and parameters, never overwrite source.

## QA acceptance
- Original SHA256 identical after preview/render.
- L1 output visual parity to approved original.
- Unsupported effects absent and explained.
- fixed orbs/parts never drift unless requested.
- text scaling anchors maintain layout; text readable and not cropped.
- temporal flicker below agreed threshold; no flashing >3Hz in default profile.
- preview/final content correspondence; job isolation and authorization.
- mobile reduced-motion preference; keyboard accessible slider.
- cancellation and failures never charge twice.
- no public exposure of unpaid exports.
- baseline 10 representative logo categories; snapshot + visual human review.

## 구현 순서
Phase 1: capability registry, config schema, level resolver, tests.
Phase 2: UI slider and per-logo effect selection with preview.
Phase 3: authenticated render queue, payment gate, artifact download.
Phase 4: QA, mobile, monitoring, performance, staged rollout.
