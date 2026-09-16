# #032 사용자 매개 인증요청·외부 자산획득 게이트

## 목적

공개자료만으로 합법적 분석이 불충분하고 사용자가 정당한 접근권한을 가진 경우, ARKAON은
`AUTH_REQUIRED` 요청을 만든다. 아이디나 비밀번호를 요청하는 것이 아니다. 로그인은 반드시
서비스의 공식 `browserAuth`, OAuth 또는 승인된 connector 화면에서 사용자가 직접 수행한다.
ARKAON에는 자격증명 대신 수명이 짧은 opaque grant reference만 전달된다.

요청에는 공식 canonical origin, 목적, 최소 scope, 읽기 전용 여부, 예상 자산 유형, 공개자료가
불충분한 이유, 약관·라이선스, 위험, 만료시간, correlation ID를 명시한다. 에테르니언 preflight는
공식 도메인, 인증수단 allowlist, 최소권한, 출처 권한, robots/약관/라이선스, 자산화 가능성,
개인정보·secret 경계를 모두 통과해야만 요청을 사용자에게 보여준다.

요청 전체는 canonical JSON의 SHA-256 fingerprint로 고정된다. preflight는 호출자가 넘긴 boolean을
신뢰하지 않는다. 게이트 밖의 에테르니언 signer가 요청 fingerprint, 7개 판정, expiry, nonce를
Ed25519로 서명한 불변 attestation만 받는다. 게이트에는 신뢰 공개키만 있어 자체 승인을 만들 수
없으며, 변조·다른 요청·다른 키·만료·nonce 재사용은 모두 차단된다.

## 상태와 불변조건

`REQUESTED → ETHERNIAN_PREFLIGHT_PASSED → WAITING_USER_AUTH → GRANTED → COLLECTED →
ETHERNIAN_ASSET_REVIEW → READY_TO_REPORT`

어느 단계에서든 거부·만료·철회는 각각 `DENIED`, `EXPIRED`, `REVOKED`로 닫힌다.

- grant는 audience·scope·purpose에 묶이고 요청보다 먼저 만료한다.
- grant는 단일 목적·단일 사용이며 재생, 만료, 철회, scope 변경은 fail-closed다.
- MFA, CAPTCHA, 동의, 유료구매, 권한확대는 boolean 재승인으로 통과할 수 없다. 공식
  browserAuth/OAuth/connector mediator가 요청 fingerprint, 정확한 action 목록, grant reference,
  expiry, nonce를 Ed25519로 서명해야 한다.
- request, grant, 두 attestation의 만료 판정은 게이트에 주입된 동일 clock을 사용한다.
- 수집 후 provenance, license, SHA-256 content hash만 감사정보로 남긴다.
- 에테르니언 자산 검토 전에는 보고할 수 없고, 검토 후에도 `OWNED_ASSET` 자동승격은 없다.
- 요청·grant·영수증·감사코드에 secret/개인정보가 탐지되면 값을 보존하거나 되풀이하지 않고 차단한다.

외부 사이트 로그인, CAPTCHA 우회, 결제 실행, 사용자 계정 변경은 이 구현의 범위 밖이다.
