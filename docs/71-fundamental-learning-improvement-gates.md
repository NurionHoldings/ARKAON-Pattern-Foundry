# 71. 근본 학습 개선 5단계 게이트

상태: **MEMORY_FOUNDATION_ONLY** / **PRODUCT_IMPLEMENT_HOLD**  
운영 적용 완료로 표시하지 않음. **PR #105** 및 관련 학습·연결 PR은 **미병합**.

## 현재 위치

| 구분 | 상태 |
|------|------|
| 기억·스냅샷·교훈 저장 기반 | reflective learning, self-evolution compare, hourly learning **구현됨** |
| 실제 작업 연결·성능 입증 | **미완** — 본 문서 5단계 게이트 |

## 단계별 완료 판단

| 단계 | 완료 판단 기준 | Foundry 근거 |
|------|----------------|--------------|
| 1. 실제 학습 실행 확인 | 24시간 실행 기록에서 누락·오류 원인 확인 | `state/hourly-learning/`, `state/hourly-learning-current.json`, collector/startup state |
| 2. 교훈을 작업에 연결 | 실제 작업이 사용한 교훈과 결과 추적 | `lesson_work_trace.py` → `knowledge/lesson-work-traces.jsonl` |
| 3. 학습 효과 비교 | 학습자료와 **분리**한 과제 **20개 이상** 전후 비교 | `state/held-out-evaluation/tasks.json`, `arkaon_self_evolution_compare.py` |
| 4. 개선 인정 | 안전 실패·회귀 없이 **목표 실패 감소** | `state/held-out-evaluation/metrics.json` + CI Green + **인간 서명** |
| 5. 실패 환류 | 실패 원인 → 다음 학습과제 + **독립 검토** | `inbox/eternian-review`, `inbox/research`, learning impediment |

자동 평가는 **READY_FOR_REVIEW**까지 가능하며, 4단계 최종 **개선 인정**은 운영자·에테르니언 검토 없이 자동으로 내리지 않는다.

## CLI

```bash
py -3.11 orchestrator/arkaon-fundamental-learning-gates.py
py -3.11 orchestrator/arkaon-fundamental-learning-gates.py --dry-run
```

산출: `state/fundamental-learning-gates/<date>-<digest>.json`

## 정책

`config/arkaon-fundamental-learning-gates.json`

## 운영 연결 롤아웃과의 관계

Render·Netlify·Workspace 연결은 `docs/70-operational-connect-rollout.md`.  
본 5단계는 **학습·교훈·held-out 효과** 게이트이며, API 연결 완료와 별도로 진행한다.
