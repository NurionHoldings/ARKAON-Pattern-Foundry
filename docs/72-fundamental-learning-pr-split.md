# 72. 학습 게이트 PR 분리 (HOLD)

## 배경

- **PR #105** · **#115** · **#116**: CI Green, **미병합**
- #105에는 로고·Google IAM·Render/Netlify 연결 준비와 학습 평가기가 **한 브랜치**에 공존
- **전체 HOLD 해제·일괄 병합 금지** — 학습 평가기만 검증하려고 배포 연결 HOLD를 풀면 안 됨

## 권장 분리

| PR 범위 | 포함 예 | 제외 |
|---------|---------|------|
| **학습·게이트 only** (main 대상 신규 PR) | `fundamental_learning_*`, `lesson_work_trace`, `config/arkaon-fundamental-learning-gates.json`, `docs/71`, `docs/72`, `orchestrator/arkaon-fundamental-learning-gates.py`, tests | `render.yaml`, `netlify/*`, `google_workspace_iam`, 로고 prototype |
| **연결·배포 prep** (#105 등) | Render/Netlify/IAM, `docs/70`, `services/*` | 학습 게이트 (선택: 머지 순서는 학습 PR 먼저 검토 가능) |

## cherry-pick 예시 (운영자)

```bash
git checkout -b feat/fundamental-learning-gates-strict main
git cherry-pick <commits touching learning gates only>
```

## 판정 (인석형 검토 반영)

**「기억 누적 기반 + 평가 틀 구현, 실효성 검증은 보갔 필요」** — `efficacy_validation: NEEDS_HARDENING`  
Stage 5 `CANDIDATE_EVIDENCE` ≠ 실패 환류 완료.
