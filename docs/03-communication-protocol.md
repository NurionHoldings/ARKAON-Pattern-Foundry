# 03. 에테르니언↔아르카온 교신 프로토콜

- 명세 ID: APF-PROTOCOL-001
- 프로토콜: AFP/0.1
- 형식: JSON, UTF-8, JSON Schema 검증

## 원칙

자연어는 payload의 보조 설명으로만 사용한다. 모든 작업은 WorkContract, 결과는 ResultContract로 교환한다. 멱등성, 상관관계, 기한, 권한, 예산, 증거를 명시한다.

## Envelope

```json
{
  "protocol": "AFP/0.1",
  "message_id": "uuid",
  "correlation_id": "uuid",
  "causation_id": "uuid|null",
  "idempotency_key": "string",
  "sender": {"type":"ARKAON","principal_id":"uuid","version":"0.1.0"},
  "receiver": {"type":"ETERNIAN"},
  "tenant_id": "uuid",
  "classification": "INTERNAL",
  "created_at": "RFC3339",
  "expires_at": "RFC3339",
  "schema": "work-contract/0.1",
  "payload": {}
}
```

## WorkContract 필수값

- task_type: EXTRACT_INTENT_DNA, ANALYZE_DOMAIN, EXTRACT_PATTERN, CHECK_CONFLICT, REVIEW_PUBLICATION
- target_snapshot_id와 허가된 artifact_ids
- objective와 명시적 non_goals
- input facts/evidence references
- required_outputs와 acceptance_criteria
- risk_class: LOW, MODERATE, HIGH, CRITICAL
- analysis_budget: max_seconds, max_tokens, max_artifacts, max_depth
- stop_conditions
- authority_scope
- previous_decisions와 locked_contracts

## ResultContract 필수값

- status: COMPLETED, PARTIAL, HOLD, REJECTED, FAILED
- observed_facts[], inferences[], unknowns[]
- intent_dna_ref
- artifacts_produced[]
- findings[]
- confidence score와 근거
- budget_consumed
- recommendation
- evidence_trace[]
- next_action
- content_hash

## 교신 순서

1. 아르카온이 허가와 Snapshot을 검증한다.
2. Intent_DNA가 없거나 stale이면 EXTRACT_INTENT_DNA 계약을 발행한다.
3. 에테르니언이 DNA와 최소 분석계획을 반환한다.
4. 아르카온이 예산·권한·잠금계약을 Gate 검사한다.
5. 승인된 분석계약만 실행한다.
6. 에테르니언은 사실·추론·미확인을 분리해 반환한다.
7. 아르카온이 schema, hash, evidence completeness를 검증·저장한다.
8. 실패 또는 불확실성 임계 초과 시 HOLD/ESCALATE한다.

## 오류

- INVALID_SCHEMA: 재시도 금지, 계약 수정
- AUTHORITY_DENIED: 즉시 HOLD
- SOURCE_STALE: 새 Snapshot 요구
- BUDGET_EXCEEDED: PARTIAL 저장 후 승인 요청
- EVIDENCE_GAP: 추론을 공식 사실로 승격 금지
- CONFLICT_WITH_LOCK: 변경영향 보고 후 REOPEN 대기
- CONTAMINATION_FOUND: 격리 및 공용화 금지

자동 재시도는 transient 오류에 한해 최대 2회, 지수 backoff와 동일 idempotency_key를 사용한다.
