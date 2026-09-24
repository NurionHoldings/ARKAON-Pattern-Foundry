# Railway 생성 경험 자산 — 2026-09-24

## 관찰 범위와 상태

- 실제 화면: Railway 워크스페이스 `NurionHoldingsInSuk's Projects`, 프로젝트 `capable-surprise`, 환경 `production`.
- `Postgres` 서비스는 Online이고 `postgres-volume`이 붙어 있다. DB 화면에는 당시 테이블이 표시되지 않았다. 이 화면만으로 마이그레이션이나 테넌트 생성 완료를 판정하지 않는다.
- `ARKAON-Pattern-Foundry` 앱 서비스는 `Apply 1 change`에 묶인 **생성 대기** 상태다. 앱의 활성 배포, GitHub 소스, 앱 전용 `/data` 볼륨, 서비스 변수가 확인되지 않았다. `6 variables added by Railway`는 Railway 기본 변수이며 APF 필수 변수를 뜻하지 않는다.
- 소스 연결 메뉴에는 `NurionHoldings/mjn`, `NurionHoldings/aibaeby`만 보였고 대상 저장소는 없었다. Railway GitHub App 설정을 열자 GitHub 로그인 화면이 나타났다. 저장소 범위 선택·설치 완료·소스 연결 성공은 관찰하지 못했다.
- PR #71은 draft, `PRODUCT_IMPLEMENT_HOLD`, `deployment=false`다. CI 성공과 Postgres Online은 운영 배포 승인이나 백엔드 검증의 대체 증거가 아니다.

## 아르카온이 다음에 안내할 순서

1. **결과물 우선**: 현재 시안·미리보기와 가능한 범위를 보여 준다. 운영 준비를 원하는지 사용자가 선택하도록 한다.
2. **현재 상태 재조회**: 프로젝트·환경·서비스와 PR 헤드 SHA·CI·readiness를 읽는다. 화면 캡처를 현재 상태의 영구 사실로 취급하지 않는다.
3. **GitHub App 접근**: 승인된 저장소 `NurionHoldings/ARKAON-Pattern-Foundry` 하나만 선택한다. 실제 GitHub 권한 화면에서 저장소 범위와 요청 권한을 확인한다. 범위가 넓어지면 멈춘다. 로그인 정보와 일회용 코드는 안전한 인증 창에서만 다룬다.
4. **소스 선택**: 검토된 branch/SHA를 선택하고 자동 배포 여부를 확인한다. draft PR이나 `deployment=false` 상태에서 운영 환경의 Deploy를 누르지 않는다.
5. **앱 설정**: 앱 전용 영속 볼륨 `/data`와 1 replica, DB 변수 참조, 런타임 경로, 정확한 빌드·시작 명령, `/health`를 확인한다. Postgres 볼륨은 앱 파일 저장소가 아니다. 비밀값은 공급자 콘솔에만 입력한다.
6. **DB 준비**: 승인된 범위에서 마이그레이션과 테넌트를 명시적으로 만들고 원장·재시작 영속성·백업 복구를 증거로 남긴다. `/health`는 프로세스 확인일 뿐 DB 준비 증거가 아니다.
7. **소유자 인증**: HTTPS 도메인과 GitHub OAuth callback을 정확히 맞추고 소유자 성공·비소유자 거부를 검증한다.
8. **운영 활성화**: PR 병합·readiness 잠금 해제·정확한 운영 범위 승인 후 별도로 수행한다. 준비 화면의 `확인했어요`는 공급자 API 결과 검증이 아니다.

## 재사용 규칙

이 기록은 특정 사용자의 화면 관찰에서 얻은 **절차적 경험**이다. 저장소 권한, 토큰, DB URL, 비밀번호, 쿠키를 학습 자산에 넣지 않는다. 상태는 관찰 시점에만 유효하며 재사용 시 Railway 및 GitHub를 다시 조회한다. 실패나 보류도 기록하고 자동으로 권한을 넓히거나 배포 잠금을 풀지 않는다.
