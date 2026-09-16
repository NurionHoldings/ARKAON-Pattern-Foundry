# #033 권한 기반 소재 수집·복제·개선

## 목적

좋은 분석 기술을 도구 이름만으로 제한하지 않는다. 아르카온은 소유·허가·라이선스 증거가 있는 코드와 소재를 조건에 맞게 재사용할 수 있고, 공개 관찰물은 기능과 구조를 추출해 독립적으로 개선할 수 있다. 난독화된 코드의 정적 분석도 허용한다. 판정 기준은 **권리, 개인정보·비밀정보, 접근통제 우회 여부, 결과물의 사용 방식**이다.

## 권리와 이용 경로

`USER_OWNED`, `EXPLICIT_PERMISSION`, `PERMISSIVE_LICENSE`, `ATTRIBUTION_LICENSE`, `COPYLEFT_LICENSE`, `PUBLIC_OBSERVATION`, `UNKNOWN`을 구분한다. 권리 증거는 SHA-256 참조, 권리자, 사용·수정·재배포 허용 여부와 표시·소스공개 의무를 포함한다.

- `LICENSED_REUSE`: 사용·수정·재배포 권한을 모두 기계 검증하고 provenance와 의무를 결과 후보에 승계한다. 실제 코드·소재 재사용이 가능하다.
- `ADAPTIVE_REIMPLEMENTATION`: 격리된 임시 사본에서 기능·구조를 추출한다. 안전성·성능·구조·사용성 중 하나에 evidence digest와 서로 다른 before/after 지표 또는 서명 검토에 포함되는 평가가 필요하다. 문자열로 차원 이름만 주장할 수 없으며 120자 이상의 원문 연속 조각이 유입되면 격리한다.
- 공개 관찰만으로 직접 재사용하거나 권리가 불명확하면 `ETHERNIAN_REVIEW`로 보낸다.

저작자 표시 라이선스는 `ATTRIBUTION`, 카피레프트 라이선스는 `SOURCE_DISCLOSURE` 의무가 빠지면 권리 증거 생성 단계부터 실패한다. 어떤 후보도 자동으로 `OWNED_ASSET`이 되지 않는다.

## 수집과 분석

- HTTPS origin allowlist를 사용하고 모든 redirect와 최종 capture origin을 다시 검증한다.
- robots 및 이용약관 자세를 기록한다. 이 자세 전체는 수집정책 attestation에 서명 결합된다. 일반 충돌은 검토로 보내고, 직접 권한 증거와 그 권한의 우선 적용이 명시된 경우에는 진행할 수 있다.
- 요청 횟수, 총 바이트, content type을 요청 fingerprint에 고정한다.
- HAR, DOM, 허가된 공개 source map을 다룬다. 쿠키, 인증 헤더, 세션 저장소, query secret, 토큰, 이메일과 전화번호는 분석 전에 제거한다.
- JS는 tokenize와 식별자 독립 구조 요약, CSS·HTML은 정적 구조 정규화를 수행한다. 외부 코드는 실행하지 않는다.

## 금지 경계

개인정보·자격증명·비공개 소스·영업비밀 취득과 로그인, 페이월, DRM, CAPTCHA, 암호화, 접근통제 우회, 토큰 탈취, anti-bot 회피는 거부한다. 이는 난독화된 공개·허가 코드의 정적 분석과 구분된다.

## 승인 무결성

요청의 URL, origin, 이용 경로, 목적, content type, 예산, 만료 및 위험 플래그는 canonical fingerprint에 결합된다. 권리 평가, 수집정책, 최종 독창성 검토에는 에테르니언의 Ed25519 서명 attestation이 필요하다. 수집정책 서명에는 robots·약관·명시권한 우선 여부·접근허가 여부가, 최종 서명에는 후보 content hash·이용 경로·개선증거 fingerprint가 포함된다. attestation은 요청·권리 증거·단계·판정·nonce·만료에도 결합되어 바꿔치기, 다른 키, 만료, replay를 차단한다. 파이프라인에는 공개키만 주입되므로 아르카온은 스스로 승인할 수 없다.

## 상태

`REQUESTED → RIGHTS_EVALUATED → COLLECTION_POLICY_PASSED → CAPTURED → SANITIZED → NORMALIZED → LICENSE_ORIGINALITY_REVIEW → ASSET_CANDIDATE`

예외 상태는 `ETHERNIAN_REVIEW`, `DENIED`, `QUARANTINED`, `EXPIRED`다.

## 검증 범위

권리 유형별 reuse, 표시·소스공개 의무, 불명 권리 검토, robots/약관 충돌, redirect 이탈, 예산·content type, HAR·DOM·URL 비밀 및 개인정보 제거, source map 권한, 난독화 정규화, 우회 요청 차단, 실질 개선, 대형 원문 조각 누출, 서명 변조·다른 키·만료·replay를 자동 테스트한다.
