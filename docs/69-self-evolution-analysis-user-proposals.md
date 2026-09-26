# 69. Self-Evolution 분석 · 사용자 기능 제안

- 명세 ID: APF-SELF-EVOLUTION-ANALYSIS-001
- 상태: IMPLEMENTED / PROPOSE_ONLY

## 목표

범(BEOM)·ETERNIAN이 기능을 개선할 때마다 아르카온은:

1. **과거 vs 현재** capability snapshot 비교
2. **나아진 과정** 분석 (contributor 흐름, pipeline 단계)
3. **추가된 기능** 분석 (intent, user value, process phase)
4. **사용자에게 제안** (Co-Creation 진입 프롬프트 포함)

## 파이프라인

```text
capture_snapshot (BEOM / ETERNIAN / TENANT_FEEDBACK / …)
  → compare (baseline vs candidate)
  → analyze (process steps + added feature insights)
  → propose_to_user (paid tenant — feature offers + assistant_pitch)
```

## 모듈

| 모듈 | 역할 |
|------|------|
| `arkaon_self_evolution_compare.py` | snapshot · diff |
| `arkaon_self_evolution_analysis.py` | 과정·기능 분석 |
| `arkaon_user_feature_proposal.py` | 사용자 제안 |

## Console API

| Method | Path | 설명 |
|--------|------|------|
| GET | `/v1/console/self-evolution/snapshots` | snapshot 목록 |
| GET | `/v1/console/self-evolution/compare` | diff report |
| GET | `/v1/console/self-evolution/analyze` | 과정·기능 분석 |
| POST | `/v1/console/self-evolution/propose-to-user` | 사용자 기능 제안 |
| GET | `/v1/console/self-evolution/user-proposals` | tenant별 제안 목록 |

## Analyze 응답

- `process_narrative` — BEOM→ETERNIAN 등 개선 흐름 요약
- `process_steps[]` — 단계별 contributor, capability gain
- `added_features[]` — feature_id, user_value, proposable_to_user, suggested_prompt
- `pipeline_progression[]` — pipeline stage 라벨

## 사용자 제안

`POST /v1/console/self-evolution/propose-to-user`

```json
{
  "platform_id": "NARANG_RIDER",
  "payment_entitlement_digest": "<64-hex>",
  "analysis_digest": "<optional>",
  "baseline_snapshot_id": "<optional>",
  "candidate_snapshot_id": "<optional>"
}
```

응답:

- `assistant_pitch` — 사용자에게 보여줄 개선·제안 메시지
- `feature_offers[]` — headline, user_value, suggested_prompt
- `co_creation_entry_hint` — Co-Creation chat API 안내

## 산출물

| 경로 | 내용 |
|------|------|
| `state/self-evolution/snapshots/` | capability snapshot |
| `state/self-evolution/comparisons/` | diff report |
| `state/self-evolution/analyses/` | improvement analysis |
| `state/self-evolution/user-proposals/` | tenant user proposal |
| `inbox/operator-decision/*user-feature-proposal*` | operator notice |

## 경계

- 자동 구현·배포 **금지**
- user proposal은 **PROPOSED** — operator gate 유지
- verbatim 경쟁 copy 금지; suggested_prompt는 capability 안내만

## 관련

- `docs/68-co-creation-phase4-roadmap.md`
- `docs/40-arkaon-reflective-learning.md`
- `docs/65-conversational-co-creation.md`
