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

## experience gate

`minimum_experience_artifacts` 미만이면 `INSUFFICIENT_EXPERIENCE` (409).

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

## 3단계 (미구현)

- 승인 후 template variant codegen
- platform scaffold generation
- tenant-scoped preview sandbox

## 관련

- `docs/51` 2단계 분야 요청
- `docs/64` cross-platform learning (1단계 feed)
- `docs/11` Intent_DNA (향후 chat ↔ 12축 정렬)
