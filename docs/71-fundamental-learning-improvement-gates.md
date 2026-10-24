# 71. 근본 학습 개선 5단계 게이트

상태: **MEMORY_FOUNDATION_ONLY** / **efficacy_validation: NEEDS_HARDENING** / **PRODUCT_IMPLEMENT_HOLD**  
운영 적용 완료로 표시하지 않음. **PR #105 · #115 · #116** CI Green, **미병합**. PR 분리: `docs/72-fundamental-learning-pr-split.md`.

## 현재 판정 (인석형 검토 반영)

**기억 누적 기반 + 평가 틀 구현**은 있으나, **실효성 검증 로직을 강화 중**이다.  
Stage 5 **`CANDIDATE_EVIDENCE`** = 키워드·후보 패킷 수준일 뿐, **실패 환류 완료가 아님**.

## 단계별 완료 판단 vs 평가기 검증

| 단계 | 완료 판단 기준 | 평가기가 요구하는 증거 |
|------|----------------|------------------------|
| 1 실행 확인 | 24h 기록에서 누락·오류 원인 확인 | `state/hourly-learning/*.jsonl` **`topic.observed_at`** 창, **`cycle.failed`** 및 `failure_reason`, 예정 시간대(slot) 누락 (mtime·`*.json` 사용 안 함) |
| 2 교훈↔작업 | 교훈·작업·결과 추적 | `lesson-work-traces.jsonl` **digest 재검증**, `work_outcome_digest`, 교훈 파일 **ACCEPT** + `evidence_digest` |
| 3 held-out | 학습자료와 분리 20+ 전후 비교 | **고유 `task_id`**, `separated_from_training`, baseline/post **`executed_at`·`evidence_digest`·채점**, boolean만으로 불가 |
| 4 개선 인정 | 안전 실패 0·회귀 0·실패 감소 | `metrics.json` v1: **delta&lt;0**, `safe_failure_count=0`, `regression_count=0`, **동일 `ci_commit_sha`·Green `ci_run_id`** + **인간 서명** |
| 5 실패 환류 | 실패→원인→학습과제→독립 검토 | `apf.failure-learning-feedback/v1` 전链 또는 4필드 inline; 키워드만 → **`CANDIDATE_EVIDENCE`** |

## 상태값

| `GateStatus` | 의미 |
|--------------|------|
| `NOT_STARTED` | 필수 증거 없음 |
| `PARTIAL` | 일부 증거·미해결 blocker |
| `CANDIDATE_EVIDENCE` | 후보 패킷만 (주로 5단계) |
| `READY_FOR_REVIEW` | strict 증거 충족 → **사람 검토 대기** (자동 승인 아님) |

## CLI

```bash
py -3.11 orchestrator/arkaon-fundamental-learning-gates.py --dry-run
```

산출: `state/fundamental-learning-gates/` (`apf.fundamental-learning-gate-report/v2`)

## 예시 스키마

- `config/examples/failure-learning-feedback.example.json`
- `config/examples/held-out-evaluation-tasks.example.json`
- `config/examples/improvement-recognition-metrics.example.json`

## 정책

`config/arkaon-fundamental-learning-gates.json`

## 운영 연결

Render·Netlify·Workspace: `docs/70-operational-connect-rollout.md` (학습 HOLD와 **분리**).
