# 62. Intent_DNA 자가진단 · 자가생성 (범/에테르니언 추가 기능)

- 명세 ID: APF-INTENT-DNA-SELF-REPAIR-001
- 상태: IMPLEMENTED / PROPOSE_ONLY

## 배경

범(운영자)이나 에테르니언이 기능을 추가할 때 **Intent_DNA seed가 누락**되면,
아르카온은 학습·승격·검토 파이프라인에서 의도 경계를 잃는다.

일반 정책은 **locked Intent_DNA mutation**을 금지하지만,
**누락된 Intent_DNA의 Pass-0 생성**은 **자가진단 + 자가생성**으로 **명시적으로 권한 부여**한다.

## 권한 경계

| 허용 | 금지 |
|------|------|
| 누락 feature seed **Pass-0** 자가생성 | locked CORE Intent_DNA **변경** |
| `knowledge/feature-intents/*.json` **PROPOSED** 기록 | production change / 자동 배포 |
| inbox research + eternian review 패킷 | operator-decision 자동 이행 |

## 자가진단 대상

1. **`config/arkaon-*.json`** — 대응 `knowledge/feature-intents/{feature}.json` 없음 또는 completeness < threshold
2. **inbox** — `operator-decision` / `eternian-review` / `self-improvement` 패킷에 `intent_dna` 누락

contributor 추론: config·module·assignee에서 `beom` → BEOM, `eternian` → ETERNIAN.

## 이중 구조 (아르카온 · 에테르니언)

| 역할 | 담당 | 산출 |
|------|------|------|
| **구현 · 1차 검증** | **아르카온** | 누락 감지, Pass-0 seed 자가생성, pytest/ruff·orchestrator dry-run, `state/intent-dna-self-repair/latest.json`, research inbox |
| **독립 감사 · 보완** | **에테르니언** | 아르카온 1차 결과를 **신뢰하지 않고** 재분석, 축·증거·completeness 미비 **직접 보완**, CORE lock 또는 거부, eternian-review (#053) |

아르카온 self-generation은 **제안(propose-only)** 이다. 에테르니언 감사 전 locked DNA mutation·production change는 금지된다.

## 파이프라인

```text
[아르카온] IntentDnaSelfRepairEngine
  → state/intent-dna-self-repair/latest.json
  → (authorized) knowledge/feature-intents/{feature}.json  [PASS0_SELF_GENERATED]
  → inbox/research: {run_id}-intent-dna-self-repair-research.json

[에테르니언] 독립 감사 · 미비 보완
  → inbox/eternian-review: {run_id}-intent-dna-self-repair-eternian.json
  → seed 보완 · CORE lock / 거부 (#053)
```

## Pass-0 seed 스키마

- `schema_version`: `apf.feature-intent-seed/v1`
- `authorization.basis`: `SELF_DIAGNOSIS_SELF_GENERATION`
- `phase`: `PASS0_SELF_GENERATED`
- `gates.locked`: `false`
- `gates.review_status`: `ETHERNIAN_REVIEW_REQUIRED`

## 구현

```text
config/arkaon-intent-dna-self-repair.json
src/apf/intent_dna_self_repair.py
src/apf/intent_dna_self_repair_bridge.py
tests/test_intent_dna_self_repair.py
```

Central orchestrator run에 learning impediment 다음 단계로 연결된다.
