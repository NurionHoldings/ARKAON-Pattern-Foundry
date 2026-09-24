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

## 후속 관찰: 저장소 권한·소스 연결

- GitHub의 기존 Railway App 설치는 `Only select repositories`였으며 `mjn`, `aibaeby`가 이미 선택되어 있었다. 사용자가 추가 승인을 한 뒤 `NurionHoldings/ARKAON-Pattern-Foundry`만 더해 총 3개가 됐다. 기존 두 저장소를 제거하거나 `All repositories`로 바꾸지 않았다.
- 이 App은 metadata 읽기와 actions·administration·checks·code·commit statuses·deployments·pull requests·workflows 읽기/쓰기 권한을 요청한다. 아르카온은 저장소 추가 직전 **권한의 종류와 범위**를 화면에 밝혀야 한다.
- Railway의 `Connect Repo` 목록에서 대상 저장소를 다시 확인하고 대기 중인 앱 서비스에 소스 연결을 추가했다. 서비스는 여전히 `production`에서 생성 대기 상태이며 `Wait for CI` 설정 전 `Apply 3 changes`, 설정 후 `Apply 4 changes`로 표시됐다. **Deploy를 누르지 않았다.**
- Railway는 연결 즉시 `main`을 production 브랜치로 선택하며 변경 시 자동 배포를 안내했다. `Wait for CI`를 켰지만 Railway 화면이 업데이트된 GitHub 권한 수락 필요를 안내했다. 이 기능의 실제 효력은 아직 검증되지 않았으며 CI 통과 후 배포를 허용하는 조건일 뿐, readiness 잠금이나 자동 배포 자체를 대체하지 않는다. 브랜치 분리 동작은 설정 손상 가능성 때문에 진행하지 않았다. 따라서 **대기 변경을 적용하면 안 된다.**
- `New Environment`에는 production 복제와 빈 환경 선택지가 있었다. 새 환경은 생성하지 않았다. 복제는 서비스·변수·구성을 복사하므로 비용·데이터 범위를 확인해야 한다.
- 앱 전용 볼륨, 필수 서비스 변수, OAuth callback, DB 마이그레이션과 테넌트, 백업 복구는 아직 확인되지 않았다. 화면에 `Could not load public networking`이 보였으므로 공용 도메인도 검증하지 못했다.

## 추가 재사용 규칙

GitHub App을 승인해도 Railway의 서비스 소스 연결과 서비스 생성·배포는 각각 별도 상태다. `Wait for CI`만 켜져 있으면 안전한 배포 잠금으로 오판하지 않는다. 대기 변경 수와 자동 배포 브랜치를 보여 주고, readiness가 false일 때 Apply/Deploy를 금지한다. 브랜치 연결을 변경할 때 기존 설정 영향이 불확실하면 중단하고 정확한 변경 범위를 다시 확인한다.

## 아르카온 안내 화면에 연결

`GET /v1/console/railway-guidance`는 owner 인증 후 이 플레이북과 현재 저장소 readiness를 읽어 단계별 행동, 필요한 증거, 중단 조건을 제공한다. `/console/railway-setup`은 이를 보여 주면서 과거 관찰 날짜와 재조회 필요성을 분명히 표시한다. 플레이북을 바꾸면 안내 화면의 판단 자료도 함께 바뀌며, readiness 읽기에 실패하면 진행을 중단한다. 실시간 조회와 빈 서비스 생성 경로는 아래 별도 API를 사용한다.

## Railway API 연결 구현

- 서버 환경에 `APF_RAILWAY_PROJECT_TOKEN`, `APF_RAILWAY_PROJECT_ID`, `APF_RAILWAY_ENVIRONMENT_ID`를 설정하면 owner 전용 `GET /v1/console/railway-live`가 공식 GraphQL API에서 토큰의 프로젝트·환경 범위를 먼저 대조하고, 프로젝트의 서비스 목록을 재조회한다. 토큰은 응답에 포함되지 않는다. 현재 운영 환경에 이 토큰이 설치됐다는 증거는 없다.
- `APF_RAILWAY_ACTION_SECRET`(32자 이상)과 영속적인 `APF_RUNTIME_ROOT`가 추가로 구성돼야 빈 서비스 생성 미리보기가 열린다. 한 번의 확인 토큰은 5분 유효하며 소유자·프로젝트·환경·서비스 이름을 묶는다. 실행 시 SQLite 원장에 1회 사용을 먼저 기록하고, Railway 생성 응답 뒤 서비스를 다시 읽어 확인한다. 응답이 불확실하면 같은 토큰으로 재시도하지 않고 공급자 화면을 재조회한다.
- **현재 `deployment=false`에서는 생성 API가 423으로 거부**된다. 실시간 조회와 미리보기는 안전하게 가능하지만 실제 생성은 현재 잠금에 걸린다. 자원 생성은 Railway 과금 대상일 수 있다. GitHub 소스·DB·볼륨·변수·도메인·마이그레이션·배포는 이 경로에서 만들지 않는다.
- Railway는 프로젝트 토큰을 프로젝트 내 단일 환경으로 제한한다. `serviceCreate`가 연결된 토큰에 허용되는지 실환경 검증이 필요하며, 거절될 경우 더 넓은 토큰으로 자동 대체하지 않는다. 다중 고객용으로 넓히려면 프로젝트 선택 OAuth, 암호화 토큰 저장·갱신·철회 및 비용·범위별 추가 승인 흐름을 별도 구현한다.
