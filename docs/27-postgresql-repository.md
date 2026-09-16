# PostgreSQL Repository 및 실연결 게이트 (#038)

## 구현 범위

핵심 AnalysisTarget API는 `TargetRepository` 계약으로 메모리와 PostgreSQL 어댑터를
교체한다. 운영 환경은 `DATABASE_URL`이 없으면 시작을 거부하며 메모리 저장소로 조용히
대체하지 않는다. 공개 요청은 tenant를 자동 생성하지 않고 운영자가 사전에 provision한
tenant만 사용한다.

PostgreSQL 어댑터는 모든 조회·변경에 `tenant_id`를 포함하고, 상태 변경은
`WHERE revision=:expected_revision` compare-and-swap으로 한 요청만 성공시킨다. 생성은
`(tenant_id, name)` 고유키와 정규 JSON fingerprint를 결합한다. 동일 재시도는 기존 결과를
돌려주고 같은 키의 다른 내용은 충돌로 거부한다. 권한 및 증거 ID는 JSONB 타입 제약으로
보존하고 DB `timestamptz now()`를 UTC로 반환한다.

## 마이그레이션과 트랜잭션

`src/apf/migrations.py`는 적용 원장을 사용해 순서대로 upgrade하고 역순 downgrade한다.
모든 upgrade에는 대응하는 `.down.sql`이 필요하다. 생성은 PostgreSQL READ COMMITTED와
고유 제약의 대기/가시성 규칙을 사용하며, 갱신은 단일 원자적 CAS 문장이다.

## 검증 상태

- 결정적 MemoryRepository 계약 및 API 회귀: PASS
- 운영 DSN 누락 fail-closed: PASS
- PostgreSQL CI service와 실연결 테스트: 구성됨
- 실제 PostgreSQL upgrade/downgrade, JSONB, tenant FK, 동시 생성 및 동시 CAS: 테스트 작성됨
- 현재 실행 환경의 PostgreSQL 실연결: **NOT RUN** (`TEST_DATABASE_URL`, psql, docker 없음)

따라서 #038 구현은 완료 후보이나 `POSTGRES_LIVE_PROOF`는 CI 또는 별도 PostgreSQL 환경에서
실제로 Green이 되기 전까지 닫혀 있다. 이 문서는 연결 성공을 주장하지 않는다.
