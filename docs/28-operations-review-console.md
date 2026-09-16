# 28. 운영·검토 콘솔

- 단계: #040
- 상태: SQLITE_DURABLE_ADAPTER_IMPLEMENTED / POSTGRES_LIVE_PROOF_HOLD

## 구현 범위

`/console`은 한국어 반응형 운영 화면이며 대상, 검토, 후보, 준비상태를 한 화면에
배치한다. 모든 콘솔·콘솔 API 경로는 서명된 HttpOnly 세션으로 tenant와 principal을
확정한다. 상태 변경 요청은 SameSite 쿠키와 CSRF 토큰을 함께 확인한다. 브라우저에는
원문 수집물, 자격증명, 세션 토큰, 개인정보를 표시하거나 Web Storage에 저장하지 않는다.

개발 환경의 `/console/dev/session`은 `APF_ENABLE_DEV_SESSION=true`를 명시한 경우에만
활성화되는 로컬 경계다. 운영 환경에서는 노출되지
않으며 `APF_CONSOLE_SESSION_SECRET`이 없으면 애플리케이션 시작부터 실패한다. 운영 배포
전에는 이 개발 경로 대신 조직 IAM이 검증한 principal로 서버 측 세션을 발급하는 경로가
필요하다.

## 검토 불변조건

- 화면 입력은 검토 상태를 직접 변경하지 않는다.
- 승인·거부 제출은 참조 문자열이 아니라 전체 `ReviewAttestation`을 받는다.
- tenant, principal, URL task, job, request, stage, evidence, 만료, nonce를 정확히 결합한
  Ed25519 외부 서명만 기존 durable repository를 통해 반영한다.
- 후보는 `OWNED_ASSET`으로 표시되거나 자동 승격되지 않는다.
- Intent_DNA 변경과 MJN 쓰기 기능은 없다.

## #040 영속 어댑터

`/console/api/reviews`, `/console/api/candidates`와 버전 API는 tenant와 principal로 범위를
제한한다. SQLite 실데이터를 읽으며 검토 레코드·후보 manifest의 기존 해시 무결성 검사를
우회하지 않는다. 후보 응답은 candidate/job hash, 라이선스 의무와
`CANDIDATE_NOT_OWNED_ASSET` 상태만 반환한다. 원문, 격리 위치, 서명, 키는 반환하지 않는다.
페이지 순서는 고정되며 limit은 1~100이다. 저장소 연결·무결성 확인 실패는 빈 성공 대신
503으로 닫힌다. `ConsoleReviewStore`는 backend-neutral tenant-scoped 계약이고 현재 구현은
`DurableReviewRepository` SQLite 어댑터다.

## 현재 제한

PostgreSQL 검토·후보 schema/adapter의 실제 연결 및 CI 증거는 아직 없다. 운영에서는
`DurableReviewRepository` 인스턴스와 신뢰된 공개키를 애플리케이션 조립부에서 명시적으로
주입해야 한다. 조직 IAM 세션 발급, PostgreSQL live proof, 화면의 상세 목록 렌더링이 남아
있으므로 전체 운영 콘솔 완료나 배포 준비 완료로 표현하지 않는다.
