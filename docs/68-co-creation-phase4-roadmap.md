# 68. Co-Creation 4단계 Roadmap — Codegen · Preview · Deploy

- 명세 ID: APF-CO-CREATION-PHASE4-001
- 상태: ROADMAP / PRODUCT_IMPLEMENT_HOLD
- 조회일: 2026-09-19

## North Star

플랫폼이 세상에 나왔을 때, **로그인·결제 사용자**가 채팅으로 원하는 작품(템플릿·플랫폼·경험)을 요청하면, 아르카온이 evidence-bound로 **만들고·미리보고·배포**한다.

자동화는 사용자 요구 충족을 위해 존재하지만, **오염·비밀·무단 배포**는 operator + eternian 이중 gate로 막는다.

## 전체 4단계 (1→4)

| 단계 | 이름 | 핵심 산출 | 현재 |
|------|------|-----------|------|
| **1** | Experience | cross-platform pattern, reflective lesson | IMPLEMENTED (`docs/64`) |
| **2** | Co-Creation Propose | chat → template/platform blueprint | IMPLEMENTED (`docs/65`) |
| **3** | Reference · Build Scaffold | URL feel, GitHub onboarding, scaffold manifest | PARTIAL (`docs/66`) |
| **4** | Codegen → Preview → Deploy | 실행 가능 산출물 → sandbox → staged rollout | **본 문서** (4A W1 IMPLEMENTED) |

```text
[1] 학습 축적
      ↓
[2] 대화 → blueprint 제안 (operator inbox)
      ↓
[3] URL 참조 · 승인 → scaffold/preview manifest
      ↓
[4A] variant codegen (파일 생성)
      ↓
[4B] tenant preview sandbox (격리 미리보기)
      ↓
[4C] staged deploy (shadow → pilot → production)
```

---

## Phase 4 진입 조건

다음 **전부** 충족 시 Phase 4 파이프라인 시작 가능.

| # | 조건 | 근거 |
|---|------|------|
| E1 | proposal `review_status: APPROVED` + `operator_approval_digest` | `docs/65`, phase-3 build |
| E2 | billing entitlement `ACTIVE` (SoT API) | `docs/67` |
| E3 | scaffold manifest 존재 (`state/co-creation/scaffolds/`) | `co_creation_build.py` |
| E4 | reference style bundle (선택) contamination scan PASS | `docs/66` |
| E5 | `automatic_implement_allowed: false` 유지 — 4A codegen은 **제안 파일**만, deploy lock 해제 전 live 반영 금지 | `docs/32`, `docs/51` |

진입 실패 코드: `PROPOSAL_NOT_APPROVED`, `ENTITLEMENT_INACTIVE`, `SCAFFOLD_MISSING`, `CONTAMINATION_BLOCKED`.

---

## 4A — Automatic Codegen

### 목표

operator 승인된 blueprint + reference style tag → **실행 가능한 variant 파일** 생성.

verbatim HTML/CSS/경쟁 문구 복제 **금지**. structural scaffold + clean-room synthesis만.

### 입력

| 소스 | 필드 |
|------|------|
| proposal | `template_blueprint`, `platform_blueprint`, `evidence_table` |
| scaffold | `sections[].pattern_token`, `codegen_status` |
| reference bundle | `style_tags`, `section_rhythm` (digest only) |
| Intent_DNA (향후) | 12축 정렬 score ≥ threshold |

### 출력

| 경로 | 내용 |
|------|------|
| `state/co-creation/codegen/{proposal_id}/` | variant tree (HTML/TSX stubs, route map, copy angle slots) |
| `state/co-creation/codegen/{proposal_id}/manifest.json` | file list, digests, contamination report |
| `inbox/operator-decision/*codegen*` | codegen review packet |

### codegen_status 전이

```text
PENDING_REVIEW → GENERATED → OPERATOR_APPROVED → PREVIEW_READY
                      ↓
                 REJECTED (contamination / evidence gap)
```

### 게이트

1. **Contamination gate** — competitor verbatim, secret, PII scan (`docs/06`, `experience_operations_audit`)
2. **Evidence gate** — section마다 `pattern_token` + digest ref 1개 이상
3. **Reference gate** — style tag만 반영; source URL 원문 저장 금지
4. **Operator gate** — `GENERATED` → live preview 연결 전 `OPERATOR_APPROVED` 필수

### 계획 API

| Method | Path | 설명 |
|--------|------|------|
| POST | `/v1/console/co-creation/codegen` | proposal_id + approval digest → codegen run |
| GET | `/v1/console/co-creation/codegen/{proposal_id}` | manifest + status |
| POST | `/v1/console/co-creation/codegen/{proposal_id}/approve` | operator codegen 승인 digest |

### 계획 모듈

```text
src/apf/co_creation_codegen.py          # variant writer
config/arkaon-co-creation-codegen.json  # template roots, forbidden paths
tests/test_co_creation_codegen.py
```

### 4A 완료 기준

- [x] blueprint section N개 → N개 variant stub + manifest digest (`co_creation_codegen.py`)
- [x] contamination scan 0 BLOCKER
- [x] operator inbox packet 자동 생성 (`co_creation_codegen_bridge.py`)
- [x] `automatic_deploy_allowed` policy load 시 **거부** (기존 phase-3와 동일)
- [x] PREVIEW_READY 이후 4B sandbox 연결 (`co_creation_preview.py`)

---

## 4B — Tenant Preview Sandbox

### 목표

tenant-scoped **격리 미리보기** URL에서 사용자·operator가 codegen 결과를 확인하고, 채팅 피드백으로 blueprint를 수정할 수 있다.

production traffic·공개 DNS **연결 금지** (preview host only).

### 입력

- 4A `OPERATOR_APPROVED` codegen manifest
- tenant_id, platform_id, billing entitlement (preview session TTL)

### 출력

| 경로 | 내용 |
|------|------|
| `state/co-creation/previews/{id}/runtime.json` | sandbox id, expiry, routes, auth mode |
| Preview URL | `https://preview.{console_host}/t/{tenant_slug}/{sandbox_id}/` (계획) |

### Preview lifecycle

```text
PROVISION → ACTIVE → FEEDBACK_LOOP (optional chat revise) → EXPIRED | PROMOTE_CANDIDATE
```

| 상태 | 설명 |
|------|------|
| PROVISION | 격리 runtime 기동 (container / static host / dev server — 구현 선택) |
| ACTIVE | entitlement-valid 사용자만 접근 |
| FEEDBACK_LOOP | chat revision → proposal v2 (phase-2 재진입, 동일 session) |
| EXPIRED | TTL 만료, sandbox teardown |
| PROMOTE_CANDIDATE | deploy 4C 후보로 표시 (자동 promote 아님) |

### 게이트

1. **Tenant isolation** — cross-tenant URL·cookie·asset 접근 금지
2. **Billing re-verify** — preview session open 시 entitlement 재검증
3. **HTTPS only** — preview base URL http 거부
4. **No production_change** — preview는 `production_change_allowed: false` 고정

### 계획 API

| Method | Path | 설명 |
|--------|------|------|
| POST | `/v1/console/co-creation/preview/start` | codegen manifest → sandbox provision |
| GET | `/v1/console/co-creation/preview/{sandbox_id}` | status, URL, expiry |
| DELETE | `/v1/console/co-creation/preview/{sandbox_id}` | teardown |
| POST | `/v1/console/co-creation/preview/{sandbox_id}/feedback` | chat → proposal revision hook |

### 4B 완료 기준

- [x] tenant A preview가 tenant B 데이터에 접근 불가 (IDOR test)
- [x] entitlement 만료 시 preview 403
- [x] sandbox TTL 후 자동 EXPIRED + teardown
- [x] feedback loop가 phase-2 proposal v2 생성 (기존 session_id 유지)

### 구현 (W2)

| 구성 | 경로 |
|------|------|
| Engine | `src/apf/co_creation_preview.py` |
| Policy | `config/arkaon-co-creation-preview.json` |
| Tests | `tests/test_co_creation_preview.py` |

---

## 4C — Staged Deploy

### 목표

preview에서 승인된 variant를 **단계적 rollout**으로 tenant production scope에 반영.

`docs/34` staged rollout 원칙 정렬: SHADOW → PILOT → PRODUCTION.

### 입력

- 4B `PROMOTE_CANDIDATE` sandbox + operator deploy approval digest
- eternian audit packet (scope-bound)
- predeployment readiness PASS (`docs/43`)

### Rollout 단계

| 단계 | traffic | 승인 | 설명 |
|------|---------|------|------|
| **SHADOW** | 0% (mirrored observe) | operator | codegen diff 관측, public fallback 유지 |
| **PILOT** | tenant subset / beta flag | operator + eternian **독립** | tenant-scoped beta URL 또는 feature flag |
| **PRODUCTION** | tenant production | operator + eternian **독립** | full tenant scope 반영 |
| **KILL** | 0% | operator | 즉시 PAUSE, rollback manifest |

동일 principal이 eternian + operator deploy 승인 **겸직 불가** (`docs/34`).

### 출력

| 경로 | 내용 |
|------|------|
| `state/co-creation/deployments/{proposal_id}/` | rollout state, promotion log |
| `state/co-creation/deployments/{proposal_id}/rollback.json` | 이전 known-good digest |

### 게이트

1. **Predeployment readiness** — `GET /v1/console/predeployment` PASS
2. **Independent dual approval** — PILOT/PRODUCTION promote
3. **Deployment lock** — `IMPLEMENT_HOLD` / `automatic_deploy_allowed: false` 해제 전 **PRODUCTION 불가**
4. **Kill switch** — operator 단일 호출로 PAUSE (`docs/34`)
5. **Audit append-only** — promote/rollback 이벤트 `audit_events` 기록

### 계획 API

| Method | Path | 설명 |
|--------|------|------|
| POST | `/v1/console/co-creation/deploy/shadow` | shadow start |
| POST | `/v1/console/co-creation/deploy/promote` | `{ stage: PILOT \| PRODUCTION }` + approvals |
| POST | `/v1/console/co-creation/deploy/kill` | kill switch |
| GET | `/v1/console/co-creation/deploy/{proposal_id}` | rollout status |

### 4C 완료 기준

- [ ] SHADOW → PILOT → PRODUCTION 순서 위반 promote 거부
- [ ] 동일 person dual approval 거부
- [ ] kill switch 후 traffic 0 + rollback manifest 기록
- [ ] predeployment FAIL 시 promote fail-closed

---

## Phase 4 통합 파이프라인

```text
CHAT (phase-2)
  → PROPOSE → operator APPROVE
  → BUILD scaffold (phase-3)
  → CODEGEN (4A)
  → operator codegen APPROVE
  → PREVIEW sandbox (4B)
  → user/operator ACCEPT preview
  → DEPLOY shadow (4C)
  → PILOT (dual approve)
  → PRODUCTION (dual approve + HOLD release)
```

피드백 루프:

```text
PREVIEW feedback → CHAT revise → proposal v2 → (승인부터 재진입)
```

---

## 정책 · 설정

`config/arkaon-co-creation-phase4-roadmap.json`

| 필드 | 기본 | 설명 |
|------|------|------|
| `enabled` | false | Phase 4 전체 (HOLD 해제 전 false) |
| `codegen_enabled` | false | 4A |
| `preview_enabled` | false | 4B |
| `deploy_enabled` | false | 4C |
| `preview_ttl_minutes` | 120 | sandbox TTL |
| `require_billing_api_for_preview` | true | digest-only preview 거부 (운영) |
| `require_eternian_for_pilot` | true | PILOT promote |
| `require_eternian_for_production` | true | PRODUCTION promote |
| `max_codegen_files` | 64 | variant tree 상한 |
| `forbidden_codegen_paths` | `[".env", "secrets/", ".git/"]` | write 금지 |

기존 `config/arkaon-co-creation-build.json`의 `automatic_deploy_allowed: false`는 Phase 4C PRODUCTION까지 **유지**한다.

---

## 구현 Wave (권장 순서)

| Wave | 범위 | 선행 |
|------|------|------|
| **W1** | 4A codegen engine + contamination + inbox packet | phase-3 build — **DONE** |
| **W2** | 4B preview provisioner (static host MVP) + entitlement re-verify | W1 — **DONE** |
| **W3** | 4B feedback → proposal v2 loop | W2, phase-2 chat |
| **W4** | 4C SHADOW + deploy state machine | W2, `docs/34` |
| **W5** | 4C PILOT/PRODUCTION dual approval + kill switch | W4, predeployment |
| **W6** | Intent_DNA 12축 chat 정렬 (`docs/11`) | W1 |

각 Wave는 **독립 PR + 테스트 + operator HOLD**로 merge. 한 Wave에서 PRODUCTION unlock 하지 않는다.

---

## 테스트 계획

| 층 | 대상 |
|----|------|
| Unit | codegen manifest, status transition, policy forbidden paths |
| Integration | proposal → scaffold → codegen → preview manifest chain |
| Security | tenant isolation, IDOR, entitlement expiry, contamination BLOCKER |
| Concurrency | duplicate codegen/deploy idempotency |
| Rollout | shadow→pilot order, dual approval, kill switch |

---

## 현재 vs 목표 gap

| 항목 | 지금 (phase-3) | Phase 4 목표 |
|------|----------------|--------------|
| 산출물 | JSON scaffold/manifest | 실행 가능 variant 파일 |
| 미리보기 | manifest only | 격리 live preview URL |
| 배포 | **금지** | staged rollout (gate-heavy) |
| 사용자 loop | chat → propose | chat → propose → preview → revise → deploy |
| billing | chat gate | preview session + deploy entitlement |

---

## 경계 (불변)

- Intent_DNA mutation / owned_asset 자동 승격 **금지**
- verbatim competitor copy / secret / PII 저장 **금지**
- `automatic_learning`, `production_change` policy **false** (HOLD 해제 전)
- eternian-review 필요 scope는 inbox 경유; operator-decision 없이 partial-apply **금지**
- Phase 4 PRODUCTION은 `docs/50` IMPLEMENT_HOLD 해제 + deployment lock 해제 **후**만

---

## 관련

- `docs/51` — 1→2단계 학습·제안 전략
- `docs/65` — Co-Creation propose
- `docs/66` — phase-3 reference · build scaffold
- `docs/67` — billing entitlement
- `docs/32` — evolution boundary
- `docs/34` — staged rollout
- `docs/43` — predeployment readiness
- `docs/50` — v0.1 gate progress
