# 12. 실행계획과 설계 잠금

- 명세 ID: APF-PLAN-001
- 상태: PARTIAL_IMPLEMENTATION / PRODUCT_IMPLEMENT_HOLD

이 문서의 최초 `DESIGN_COMPLETE / IMPLEMENT_HOLD`는 더 이상 전체 저장소의 구현 상태를
정확히 표현하지 못한다. #013~#042의 안전·증거·파일럿·검토·PostgreSQL 대상 어댑터,
운영 UI shell 및 SQLite durable console adapter는 구현되었지만 제품
Definition of Done은 충족되지 않았다. 기계 판독 기준은
`knowledge/readiness/v0.1-readiness.json`이다.

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

현재 #037은 #031 후보의 외부 서명 검토 증거만 수락한다. 승인 결과도
`APPROVED_FOR_PATTERN_PROMOTION`에서 멈추며 Intent_DNA 변경, MJN 쓰기, `OWNED_ASSET`
승격을 허용하지 않는다.

다음 제품 게이트는 PostgreSQL 실연결 CI Green 증거, PostgreSQL 검토·후보 어댑터와
운영 UI 상세 렌더링,
노가다뉴스·부업장터의 실제 저장소 연결 분석, 30개 후보의 외부 서명 개별 승격, 실제 플랫폼
재사용 proof 순서다. #042는 정확히 30개 증거결합 후보와 검증·승격·재사용 proof harness를
구현했지만 외부 승격서명과 운영 재사용 증명은 만들지 않았다. #041은 제공된 메타데이터 기반 파일럿까지만 구현했으며 실제
저장소 연결은 `NOT_RUN_UNAVAILABLE`이다. 이 항목이 끝나기 전 `IMPLEMENT_HOLD`를 해제하거나 v0.1 제품 완료로
표현하지 않는다.
