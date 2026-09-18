# 61. 학습 방해 self-limit · 수정 요청 (에테르니언/범)

- 명세 ID: APF-LEARNING-IMPEDIMENT-001
- 상태: IMPLEMENTED / REQUEST_ONLY

## 목표

학습 과정에서 **아르카온 자신의 기능·정책 제한**이 학습을 방해할 때,
자동 수정 없이 **에테르니언**과 **범(운영자)**에게 **수정을 요청**한다.

## 감지 대상 (예)

| limit_kind | 설명 | 주 담당 |
|------------|------|---------|
| `BOUNDED_RESOURCE_LIMITS` | run/inbox/파일/타임아웃 cap | 범 + 에테르니언 |
| `BOUNDED_ACCUMULATION_POLICY` | lesson·축적 상한 | 범 |
| `COLLECTION_RESPONSE_TOO_LARGE` | fetch 바이트 cap | 범 + 에테르니언 |
| `COLLECTION_FETCH_FAILED` | 소스 fetch 실패 | 범 + 에테르니언 |
| `HOURLY_COLLECTION_FAILURES` | hourly cycle 실패 | 범 |
| `HOURLY_TOPIC_ZERO_YIELD` | 주제별 수집 0건 | 범 + 에테르니언 |
| `HOURLY_TOPIC_SOURCE_GAP` | domain 소스 미등록 | 범 |
| `COLLECTION_DISABLED` | collector off | 범 |

### 학습 저장능력 (`LEARNING_STORAGE`)

| limit_kind | 설명 | 주 담당 |
|------------|------|---------|
| `STORAGE_PATH_NOT_WRITABLE` | state/knowledge/inbox 쓰기 불가 | 범 |
| `STORAGE_COLLECTION_STATE_MISSING` | SQLite dedup store 없음 | 범 |
| `STORAGE_REFLECTIVE_RECORDING_DISABLED` | lesson 기록 플래그 off | 범 + 에테르니언 |
| `STORAGE_MAILBOX_BACKLOG` | 우편함 PENDING 과다 | 범 + 에테르니언 |

### 업무개선프로그램 (`BUSINESS_IMPROVEMENT_PROGRAM`)

| limit_kind | 설명 | 주 담당 |
|------------|------|---------|
| `IMPROVEMENT_PROGRAM_CONFIG_MISSING` | experience audit 설정 없음 | 범 |
| `IMPROVEMENT_PROGRAM_AREA_GAP` | evolution domain ↔ audit area 미매핑 | 범 + 에테르니언 |
| `IMPROVEMENT_PROGRAM_OUTCOME_CAP` | IMPROVEMENT_PROPOSAL 상한 | 범 + 에테르니언 |
| `IMPROVEMENT_PROGRAM_GAP_REPORT_CAP` | capability gap report cap | 범 |
| `IMPROVEMENT_PROGRAM_PATTERN_PROMOTION_BLOCKED` | pattern 승격 경로 차단 | 에테르니언 |

## 파이프라인

```text
LearningImpedimentEngine
  → state/learning-impediment/latest.json
  → inbox:
      * {run_id}-learning-impediment-research.json
      * {run_id}-learning-impediment-eternian.json   (에테르니언 검토)
      * {run_id}-learning-impediment-beom.json       (범 operator-decision)
  → 우편함 (#053) → 사용자 승인 → fulfillment (에테르니언/범)
```

## modification_request 필드

- `target`: `ETERNIAN` | `BEOM`
- `category`: `SELF_LIMIT` | `LEARNING_STORAGE` | `BUSINESS_IMPROVEMENT_PROGRAM`
- `modification_summary`: 추상 수정안 (원문·코드 복제 없음)
- `user_message`: 담당자-facing 안내

## 경계

- `automatic_implement_allowed` / `production_change_allowed` **false**
- 요청 ≠ 자동 패치; 승인·이행은 #053 흐름
- DUPLICATE_CONTENT 등 정상 dedup은 방해 요인 아님

## 구현

```text
config/arkaon-learning-impediment.json
src/apf/learning_impediment.py
src/apf/learning_impediment_bridge.py
tests/test_learning_impediment.py
```
