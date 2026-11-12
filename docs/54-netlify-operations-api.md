# 기본 운영 API

별도 Google/Render 서버 없이 Netlify Functions에서 운영합니다. Python Foundry 전체 API를 대신하지 않습니다.

- GET `/api/operations/health`: 데이터를 노출하지 않는 공개 상태 확인. Blobs 실제 읽기 연결을 점검합니다. 우편함 데이터는 항상 관리자 인증이 필요합니다.
- GET `/api/operations/mailbox`: 관리자 인증 후 최신 검토 문서 최대 100건 조회.
- POST `/api/operations/mailbox`: 관리자 인증·같은 출처·공동 검토 확인 후 제목(2,000자)과 내용(8,000자) 저장. 요청은 32KiB 제한.

기존 `APF_ADMIN_PASSWORD`(16자 이상, Production Functions 범위)를 사용합니다. 세션 쿠키는 HttpOnly/Secure/SameSite=Strict, 만료 1시간이며 비밀번호 변경 시 무효입니다. 비밀번호 값은 코드에 넣지 않습니다.

제안은 사이트 내부 비공개 Blobs의 개별 JSON 문서로 보관합니다. 운영 저장소 `arkaon-review-documents`는 배포 후에도 유지됩니다. Preview는 배포 ID별 별도 저장소를 사용하며 운영 제안을 읽거나 쓰지 않습니다. 배포 문맥을 알 수 없으면 저장소 접근을 거절합니다.

우편함에서 사용자가 공동 검토 체크 후 저장 버튼을 눌러야 수집합니다. 자동 수집·자동 승인·자동 수정·코드 실행·자동 병합은 없습니다. 실행 권한은 항상 false이며 사용자 입력 status/권한은 채택하지 않습니다. 저장 실패는 성공으로 표시하지 않습니다. 문서는 불변이며 수정·삭제 API는 제공하지 않습니다.

일반 고객 계정·결제·권한·잔액 등 트랜잭션 데이터는 이 저장소에 넣지 않습니다. Foundry 원장 및 작업 실행, AI 공급자 호출은 별도 백엔드 연결이 필요합니다. 기존 API 주소가 있으면 우편함 조회는 기존 Foundry를 유지하며, 이 화면의 새 제안 등록은 기본 우편함에만 저장합니다.

검증: `node tests/operations_api.mjs`, `node tests/simple_operator_auth.mjs`, `node tests/static_services_security.cjs`, `python scripts/build_static.py`.
운영 검증은 관리자 입장 → API 연결 확인 → 공동 검토 제안 저장 → 우편함에서 재조회 순서입니다. 운영 데이터로 자동 테스트 문서를 만들지 않습니다.
