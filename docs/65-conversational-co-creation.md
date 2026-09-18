# 65. 대화형 Co-Creation (2단계+ 프로토타입)

- 명세 ID: APF-CO-CREATION-001
- 상태: IMPLEMENTED / PROPOSE_ONLY

## 목표

플랫폼 **로그인 + 결제** 사용자가 채팅으로 요구하는 방향의 **템플릿·플랫폼 blueprint**를 아르카온이 evidence-bound로 제안한다.

자동 구현·배포는 금지 — operator-decision gate 유지.

## 파이프라인

```text
CHAT_INTAKE (tenant + principal + payment digest)
  → EXPERIENCE_GATE (phase-1 artifacts ≥ minimum)
  → INTENT_ALIGN (message keywords → landing-pattern tokens)
  → EVIDENCE_SEARCH (landing-structure-patterns/proposed)
  → PROPOSE (template sections + platform surfaces + copy angles)
  → OPERATOR inbox CONVERSATIONAL_CO_CREATION_PROPOSAL
```

## 결제 entitlement

운영: billing SoT API (`docs/67-billing-api-entitlement.md`).

Dev fallback digest:

```text
sha256("{tenant_id}|{principal_id}|{platform_id}|paid")
```

## experience gate · proposal quality score

North star: `docs/70-learning-assets-for-better-proposals.md`

1. `minimum_experience_artifacts` 미만 → `INSUFFICIENT_EXPERIENCE` (409)
2. `proposal_quality_score < minimum` → 보강(replenish) 시도 후에도 미달 시 `INSUFFICIENT_PROPOSAL_QUALITY` (409)

Score 구성: landing patterns · cross-platform learning · reflective lessons · self-evolution analyses.

gate 실패 또는 사용자 불만+자산 부족 시 `proposal_quality_replenish`가 선행되고, 보강 후 **같은 턴에서 재제안** (`docs/70`).

proposal JSON: `proposal_quality_score_at_intake`, `proposal_quality_replenished`, `proposal_quality_replenish_trigger`.

집계:

- `knowledge/landing-structure-patterns/proposed/*.json`
- `state/cross-platform-learning/20*.json`
- `knowledge/reflective-lessons/*.json`

## Console API

| Method | Path | 설명 |
|--------|------|------|
| POST | `/v1/console/co-creation/chat` | 채팅 턴 → proposal |
| GET | `/v1/console/co-creation/proposals` | 최근 proposal 목록 |
| GET | `/v1/console/co-creation/sessions/{id}` | 세션 transcript |

CSRF header 필수 (`X-CSRF-Token`).

## 산출물

| 경로 | 내용 |
|------|------|
| `state/co-creation/sessions/` | 채팅 transcript |
| `state/co-creation/proposals/` | blueprint JSON |
| `inbox/operator-decision/*co-creation*` | operator 검토 패킷 |

## 3단계

`docs/66-co-creation-phase3-reference-urls.md` — URL 참조, GitHub onboarding, build scaffold (PARTIAL).

## 4단계 (roadmap)

`docs/68-co-creation-phase4-roadmap.md` — codegen → preview sandbox → staged deploy.

## 관련

- `docs/51` 2단계 분야 요청
- `docs/64` cross-platform learning (1단계 feed)
- `docs/66` phase-3 reference · build
- `docs/68` phase-4 codegen · preview · deploy
- `docs/11` Intent_DNA (향후 chat ↔ 12축 정렬)
