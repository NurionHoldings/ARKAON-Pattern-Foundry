# 12. 실행계획과 설계 잠금

- 명세 ID: APF-PLAN-001
- 상태: DESIGN_COMPLETE / IMPLEMENT_HOLD

## 단계

### M0 Governance Lock
책임·경계, 정보등급, 승인정책, 공개저장소 정책, 위협모델 승인.

### M1 Contract Core
AFP JSON Schema, Package Schema, 상태전이, Intent_DNA fingerprint의 reference implementation과 contract tests.

### M2 Evidence & Tenant Foundation
IAM, tenant 격리, authorization, immutable snapshot, audit/outbox. 보안테스트가 Green일 때만 다음 단계.

### M3 Intent Engine
Seed extraction, evidence routing, contradiction detector, budget controller, incremental graph. 합성 corpus로 검증.

### M4 Analysis & Pattern Studio
구조지도, 후보추출, validation, approval, registry, hybrid search.

### M5 Owned-platform Pilot
MJN→노가다뉴스→부업장터. 원본은 별도 비공개 환경에 보관하고 이 저장소에는 공용화 승인본만 반영.

### M6 Reuse Proof
부업장터의 신규 기능 하나에 Package를 적용하고 기획시간·누락·재작업을 baseline과 비교.

## 우선 플랫폼 유형 5개

1. 거래·작업 중개형
2. 콘텐츠·미디어 발행형
3. AI 전문지원형
4. 커머스·주문형
5. 커뮤니티·관계형

## 기능모듈 10개 목표

Identity/Principal, Consent/Authority, Role-Permission, Workflow/State Machine, Listing/Matching, Order/Trade, Payment/Settlement Boundary, Content Workflow, Notification/Outbox, Audit/Approval.

## Definition of Done

API/DB/UI/test 명세 구현, 전체 traceability, 치명 finding 0, tenant escape 0, 공용혼입 0, 고위험 이중승인, 복원훈련 통과, 3개 플랫폼 분석, 30 Package, 10 Module, 1개 재사용 proof, 기획시간 50% 절감.

## 브랜치·품질정책

main은 승인된 문서와 Green 결과만 유지한다. 구현부터 feature branch→PR→독립검토→CI Green→squash merge를 사용한다. schema migration은 upgrade/downgrade, PostgreSQL 통합, 순서독립 회귀를 필수화한다.

## 다음 Gate

코드 구현 전에 APF-SCOPE-001, APF-DOMAIN-001, APF-PROTOCOL-001, APF-INTENT-001을 LOCK하고 threat-model.md, ADR, JSON Schemas, OpenAPI를 작성·검증한다.
