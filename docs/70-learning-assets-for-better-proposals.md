# 70. North Star — 학습 자산은 더 나은 제안을 위함

- 명세 ID: APF-NORTHSTAR-PROPOSAL-001
- 상태: ACTIVE

## 원칙

> **아르카온의 모든 학습 자산은 결국 보다 나은 제안을 하기 위함이다.**

학습은 목적이 아니라 수단이다. pattern·lesson·observation·Intent_DNA·self-evolution snapshot은 **Co-Creation 및 operator proposal의 품질**을 높이기 위해 존재한다.

## 학습 자산 → 제안

| 학습 자산 | 제안에 기여하는 것 |
|-----------|-------------------|
| Landing structure pattern | template section · evidence_table |
| Cross-platform learning | pattern token · cross-platform 근거 |
| Reflective lesson | 채택/기각 교훈 · copy angle |
| Intent_DNA | 분야 정렬 · domain brief |
| Reference URL feel | structural style (verbatim X) |
| Self-evolution analysis | 사용자 feature offer · assistant_pitch |
| SNS · research · market watch | inbox proposal (operator gate) |

## 제안 품질 score

`config/arkaon-proposal-quality.json` · `src/apf/proposal_quality_score.py`

가중 합산 (0.0–1.0):

| 구성 | weight | full score at |
|------|--------|---------------|
| landing patterns | 0.40 | 3 artifacts |
| cross-platform learning | 0.30 | 3 artifacts |
| reflective lessons | 0.20 | 2 artifacts |
| self-evolution analyses | 0.10 | 1 artifact |

기본 `minimum_proposal_quality_score`: **0.2**

## Gate 연결

### Co-Creation experience gate

`conversational_co_creation.chat()`:

1. `count_experience_artifacts >= minimum_experience_artifacts`
2. `proposal_quality_score >= minimum_proposal_quality_score`

실패 코드:

- `INSUFFICIENT_EXPERIENCE` — artifact 부족
- `INSUFFICIENT_PROPOSAL_QUALITY` — score 미달 (보강 후에도 미달 시)

proposal JSON에 `proposal_quality_score_at_intake` 기록.

### Replenish → re-propose 루프

`src/apf/proposal_quality_replenish.py` · `config/arkaon-proposal-quality.json`

품질 gate 실패 또는 **사용자 불만 + 자산 부족** 시, 제안을 거절하기 전에 **추가 분석으로 학습 자산을 보강**한 뒤 같은 요청에서 **재제안**한다.

`INSUFFICIENT_EXPERIENCE`(phase-1 artifact 부족)는 replenish로 우회하지 않는다 — 최소 학습 선행 조건은 유지.

| trigger | 조건 |
|---------|------|
| `GATE_FAIL` | score 또는 artifact gate 미달 |
| `USER_DISSATISFACTION` | 불만 표현 + score가 `replenish_user_dissatisfaction_score_ceiling`(기본 0.55) 미만 또는 핵심 카테고리 공백 |

보강 우선순위 (gap ratio 낮은 순, 최대 `max_actions_per_replenish`):

1. landing structure pattern
2. cross-platform learning supplement
3. reflective lesson
4. self-evolution analysis

proposal JSON 추가 필드:

- `proposal_quality_replenished`
- `proposal_quality_replenish_trigger`
- `proposal_quality_replenish_digest`

저장: `state/proposal-quality/replenish/{digest}.json`

Preview feedback(W3) 응답에 `proposal_quality_replenish` 블록 포함.

### Orchestrator

매 run 완료 시:

- `ProposalQualityScorer.evaluate_and_persist()`
- `state/proposal-quality/latest.json`
- run report에 `proposal_quality` 블록 포함

## Console API

| Method | Path | 설명 |
|--------|------|------|
| GET | `/v1/console/proposal-quality` | 최신 score · breakdown |
| GET | `/v1/console/proposal-quality/replenish` | 최근 replenish 기록 |
| POST | `/v1/console/proposal-quality/replenish` | operator 수동 보강 (platform_id, message) |

## 경계

- score는 **제안 허용 gate**이지 자동 배포 허가가 아님
- operator · eternian · IMPLEMENT_HOLD 불변
- verbatim copy · secret · PII 학습 금지 (`docs/51`, `docs/06`)

## 관련

- `docs/51` — 1→2단계 학습·제안
- `docs/65` — Co-Creation
- `docs/69` — self-evolution · user proposal
- `docs/40` — reflective learning
