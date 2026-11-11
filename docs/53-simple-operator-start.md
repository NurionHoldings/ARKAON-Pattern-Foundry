# 비밀번호 하나로 간편 관리자 시작

구글 서버 준비와 관계없이 Netlify의 서버 함수가 비밀번호를 검증한다.
Netlify 프로젝트 > Environment variables에 아래 항목 하나를 등록한다.

- Key: APF_ADMIN_PASSWORD
- Value: 운영자가 직접 정한 16자 이상 512자 이하 비밀번호
- Scope: Functions
- Context: Production
- Secret으로 표시, 저장 후 Git 기반 재배포

비밀번호는 채팅·Git·공개 파일에 넣지 않는다. 별도 가입·아이디 입력은 없다.
관리자 또는 우편함 페이지의 비밀번호 입력 후 입장하기를 누른다.
세션은 Secure/HttpOnly/SameSite=Strict 쿠키로 1시간 유지한다.
로그아웃 또는 비밀번호 변경 후 새 배포로 기존 세션을 무효화할 수 있다.
시도 제한은 Netlify의 IP+도메인별 분당 15회 제한을 사용한다.

간편 인증은 정적 관리 도구 화면 진입용이다. 이 화면의 HTML은 공개 자산이며
비밀 정보가 들어 있지 않다. 브라우저에서 숨김 속성을 바꾸는 것은 데이터 권한이 아니다.
실제 Foundry 콘솔·우편함 API는 기존 서버 세션과 운영자 권한을 별도로 요구한다.
Foundry 미연결 상태에서는 우편함을 조회할 수 없으며 0건이라고 표시하지 않는다.
현재 Google Cloud 프로젝트나 자원을 삭제하거나 새로 만들 필요는 없다.
