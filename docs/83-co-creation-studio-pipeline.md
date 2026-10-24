# 공동제작 ↔ 스튜디오 연결 (검토용)

상태: **HOLD** — 병합·운영 배포 승인 아님.

## 한 번에 완주하는 흐름

1. `/services/co-create.html`에서 요청(고객·목적·차별점 등) 입력
2. 같은 `session_id`·`proposal_id`로 `/services/site-builder.html`에 brief 자동 채움
3. 스튜디오에서 수정 후 저장 → `localStorage` + (API 연결 시) `PUT /v1/console/co-creation/studio/{session_id}`
4. URL의 `project`·`session`으로 다시 열면 brief·HTML 유지

Foundry API `POST /v1/console/co-creation/chat`도 채팅 후 동일 세션에 studio draft를 기록하고
`studio_brief`·`studio_open_path`를 반환합니다.

## 참고 URL (동의 연결)

메시지·`reference_site_url`에 URL이 있으면 **범위 결속 receipt** 없이 chat/codegen을 진행하지 않습니다.
`428` + `consent_path` → `/reference-material-consent` (owner 세션). 체크만으로 무단 복제·플랫폼 면책은 되지 않습니다.

## 개선 효과 검증

`POST /v1/console/co-creation/product-improvement/evaluate?session_id=…`

- 동일 brief로 **이전 단일 소개 HTML(baseline)** vs **스튜디오 candidate HTML** 채점
- `automated_check_passed`는 내용·단계·`@media`·placeholder **기초 검사**만 반영합니다.
- API가 반환하는 `improvement_accepted`는 **항상 false**이며, 통과 시 `status_display`는
  **「자동 검사 통과·독립 검토 대기」**입니다. 디자인·사용성 efficay는 에테르니언/운영자 독립 검토 전까지 인정하지 않습니다.
- 자동 검사 미통과 시 `state/co-creation/learning-followups/`에 후속 학습 과제 연결

## 코드

- `src/apf/co_creation_studio.py` — brief 추출·저장·채워진 섹션 HTML
- `src/apf/co_creation_product_improvement.py` — 전후 비교·채점 artifact
- `src/apf/co_creation_reference_gate.py` — consent 게이트

## 연결 보완 (검토 후속)

- 동의 UI: `return` 절대 URL → 기록 성공 시 스튜디오로 redirect + `reference_consent_request_id`
- co-create: 동의 전 session/brief/project·stash(`title`/`message`/`brief`)·return URL query
- studio: 서버 `GET` 초안, `PUT` 시 `X-CSRF-Token` 및 실패 시 HTTP 상태 메시지
- session id: 문자 제거(sanitize) 대신 형식 검증·`SESSION_ID_INVALID`
- receipt: `receipt_digest`·`notice_version`·co-creation 허용 decision 재검증

**판정:** 개별 기능·자동시험 통과 ≠ 브라우저 완주·교차 사용자·독립 감사 완료.

## 재검토 후속 (86d689a 이후)

- 저장 UX: 로컬 저장 성공과 API 동기화 실패 분리. cross-origin API는 `canConsoleApiSync()` false 시 서버 PUT 생략.
- return URL: Netlify preview·production·localhost + `/services/site-builder.html|co-create.html` 만 허용.
- `reference_consent_request_id`: URL·local draft·서버 studio draft·PUT payload에 연결.
- pattern catalog (`3a1d9a8`): 텍스트 근거 CRLF→LF 정규화 후 `evidence_file_digest` — 생성기·검증기 동일 규칙 (`docs/30-public-pattern-catalog.md`). 에테르니언 독립 확인: 후보 30·근거 60건 JSON = norm(Git HEAD) = norm(작업공간), 카탈로그·승격 16 PASS, GitHub test·PostgreSQL·Windows·boot 성공. **줄바꿈 CI 실패는 해소.** (전체 기능 최종 감사 완료 아님.)

## 병합 보류 중 남은 검증 (브라우저·E2E) — **미완료**

검증 순서: (1) 동의 후 복귀 → (2) API 저장·재조회 → (3) 교차 사용자 차단 → (4) 모바일 화면.

| # | 항목 | 상태 |
|---|------|------|
| 1 | 동의 후 복귀 URL·`reference_consent_request_id` 연속성 | 미완료 |
| 2 | 실제 API 서버 저장·재조회 (same-origin PUT·CSRF) | 미완료 |
| 3 | 교차 사용자·tenant studio API 접근 차단 | 미완료 |
| 4 | 모바일 화면 비교 | 미완료 |

**확인 기준 커밋:** `3a1d9a8` (코드·CI·패턴 카탈로그 독립 확인). 위 E2E 네 항목은 해당 커밋 범위에 포함되지 않음.
