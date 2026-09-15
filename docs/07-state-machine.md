# 07. 분석·검증·승인 상태머신

- 명세 ID: APF-LIFECYCLE-001

## AnalysisTarget

DRAFT → AUTHORIZATION_PENDING → AUTHORIZED → INGESTING → READY → SUSPENDED → ARCHIVED

PROHIBITED 또는 권한 만료 시 READY에서 SUSPENDED로 강제 전이한다.

## AnalysisRun

QUEUED → INTENT_SCOPING → ANALYZING → ABSTRACTING → VALIDATING → REVIEW_PENDING → COMPLETED

분기:
- 모든 실행상태 → HOLD
- 기술오류 → FAILED
- 권한철회 → CANCELLED
- 예산소진 → PARTIAL_REVIEW
- 오염탐지 → QUARANTINED

## PatternCandidate

DRAFT → EVIDENCE_CHECKED → VALIDATED → REVIEW_PENDING → APPROVED → PUBLISHED

반대 전이:
- REVIEW_PENDING → CHANGES_REQUESTED
- 어느 승인 전 상태 → REJECTED
- PUBLISHED → DEPRECATED → REVOKED
- PUBLISHED → SUPERSEDED

## Gate

- AUTHORIZE: 유효 권한·등급·범위
- INTENT: Intent_DNA completeness ≥ 0.85 또는 명시적 HOLD
- EVIDENCE: 주장별 증거 연결 100%
- CONTAMINATION: 치명 finding 0
- SECURITY: HIGH/CRITICAL 미해결 0
- SEMANTIC: 적용·제외·실패 조건 완비
- APPROVAL: 위험등급별 승인 충족
- RELEASE: immutable hash와 semver 생성

## 승인정책

LOW/MODERATE는 사람 1명. HIGH는 도메인 승인자+보안 승인자. CRITICAL 및 권한·결제·정산·개인정보는 도메인+보안/개인정보+사업책임자 중 최소 2개 독립 역할이 승인한다.

## 전이 계약

모든 전이는 expected_revision, actor, reason, evidence_refs, occurred_at, idempotency_key를 요구한다. Guard 실패는 상태를 바꾸지 않고 AuditEvent를 남긴다. 임의 상태 건너뛰기와 승인자 본인의 후보 작성·단독승인을 금지한다.
