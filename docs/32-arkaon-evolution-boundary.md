# ARKAON 진화 경계 (Pattern Foundry)

조회일: 2026-09-16
상태: NARANG RIDER `arkaon.py` 아날로그 이식. 운영 활성화·머지·배포는 **BLOCKED**.

## 원칙

ARKAON은 수요예측, 설명, 코드·시험 초안, 패턴 후보 분석을 제안할 수 있다. 배차 배제,
보수 삭감, 계정 정지, 보험 차별, 민원 자동기각, 책임 자동판정, 보복 배차, 직접 머지,
직접 배포, 비밀정보 접근, 소유자산 자동 승격은 금지된다.

프로파일 도메인은 `ARKAON_PATTERN_FOUNDRY`로 고정한다. 금지 권한은 전부 잠겨 있어야 하며
일부만 나열하면 프로파일 생성이 거부된다.

## 절차

1. 에테르니언이 HMAC 서명 지침을 발급한다. 허용 경로는 `src/`, `tests/`, `docs/`,
   `knowledge/`, `config/`, `api/`, `schemas/` 아래만 가능하고 비밀·워크플로 경로는 거부된다.
2. ARKAON은 지침 범위 안에서 변경 초안만 등록한다. `may_merge_or_deploy`는 항상 false다.
3. 진화 후보는 평가점수≥80, 프라이버시·공정·보안 게이트를 통과한 뒤 에테르니언 심사와
   운영자 승인을 독립적으로 받아야 활성화된다.
4. 활성 후보는 사유와 함께 롤백할 수 있다.

## 추적성

| 요구사항 | 구현 | 시험 |
|---|---|---|
| 금지 권한 전부 잠금 | ArkaonProfile | test_profile_must_lock_every_forbidden_authority |
| 제안만 가능 | ArkaonDevelopmentCoordinator | test_arkaon_can_propose_but_cannot_merge_or_deploy |
| 이중 승인 | ArkaonEvolutionRegistry | test_evolution_requires_all_gates_independent_review_and_operator_approval |
