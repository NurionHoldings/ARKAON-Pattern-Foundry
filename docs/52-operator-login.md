# 운영자 로그인 연결

기존 Foundry HttpOnly 서명 세션에 운영자 비밀번호 발급 경로를 연결한다.
정적 관리자·우편함 화면은 `/v1/console/access` 204 확인 전 잠긴다.
실제 `/console` 및 `/v1/console/mailbox`는 owner/operator만 허용하며,
APF_OPERATOR_TENANT_ID 설정 시 해당 tenant만 허용한다.

운영 Foundry 서버에 필요한 환경변수:
- APF_ENV=production (기존 배포의 환경 변수 명칭은 api 설정을 확인)
- APF_CONSOLE_SESSION_SECRET: 기존 운영 서명키 유지
- APF_OPERATOR_TENANT_ID: 기존 운영 tenant UUID
- APF_OPERATOR_PRINCIPAL_ID: 기존 운영자 principal UUID
- APF_OPERATOR_PASSWORD_HASH: 신뢰한 PC에서 `python scripts/operator_password_hash.py` 실행 결과

평문 비밀번호와 해시는 Git/채팅/브라우저 저장소에 넣지 않는다.
로그인은 Foundry의 HTTPS `/console/login`에서 직접 진행한다. 로그인 후 원래 관리자/
우편함 페이지로 돌아와 인증 다시 확인을 누른다. 로그인은 최대 1시간 유효하며,
API의 `/console/logout` POST는 기존 X-CSRF-Token 검증 후 쿠키를 제거한다.
브라우저 로그아웃은 도난 토큰의 서버 측 폐기를 뜻하지 않는다.

API와 웹은 같은 사이트의 서브도메인(예: api.아르카온.com) 또는 같은 출처 프록시로
제공해야 SameSite=Strict 세션이 작동한다. 서로 다른 사이트인 netlify.app/render.com
사이의 인증을 위해 쿠키 보안을 낮추지 않는다. CORS는 정확한 웹 출처와 credentials를
운영 서버에서 허용해야 한다. 비밀번호는 정적 웹에서 수집하지 않는다.

로그인 시도는 프로세스 전체에서 분당 5회 제한한다. 현재 단일 인스턴스용이며,
다중 인스턴스에서는 공통 저장소 또는 앞단의 전역 제한이 추가로 필요하다.
환경변수 미설정은 503으로 닫는다. 개발 세션은 운영에서 계속 비활성이다.
서버 배포·환경변수·동일 사이트 도메인 연결 전에는 운영 인증 완료로 표기하지 않는다.
