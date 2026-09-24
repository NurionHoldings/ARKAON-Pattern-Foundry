# ARKAON 성과물 저장·계정·배포 연결 설계 v0.1

## 대상과 역할

아르카온이 만든 랜딩·템플릿·플랫폼마다 별도 `delivery_id`와 소유자, 테넌트, 산출물 종류, 검토된 버전 SHA를 기록한다. 하나의 ARKAON 자체 운영 배포와 각 고객 성과물의 배포를 구분한다.

| 종류 | GitHub | Railway | Netlify |
| --- | --- | --- | --- |
| 정적 랜딩·정적 템플릿 | 빌드 입력과 설정을 소유자 저장소에 기록 | 로그인·저장·결제 등이 필요할 때만 API 구성 | 검토용 draft preview, 승인 후 정적 사이트 공개 |
| 서버 기능이 있는 템플릿·플랫폼 | 프론트와 백엔드 코드·검토 기록 | 사용자 계정, 데이터베이스, 비밀값, API와 작업 서비스 | 사용자 화면과 정적 자산; API 주소 연결 |
| ARKAON 관리 콘솔 | 별도 운영 저장소 | 인증·승인·작업 실행 | 배포 대상으로 혼동하지 않음 |

Railway 계정 자체는 Railway가 관리한다. 여기서 말하는 ‘계정 관리’는 성과물 서비스의 최종 사용자 가입·로그인·역할·탈퇴와 세션 보안이다. 인증 제공자, 개인정보 수집 범위, DB 보존·삭제 정책이 정해지기 전에는 계정 기능을 ‘완료’로 표시하지 않는다. Netlify에 공개 화면을 올렸다고 Railway API나 사용자 계정이 동작한다고 표시하지 않는다.

## 클릭 기반 사용자 여정

1. **결과물 미리보기**: 홈·상세와 모바일·데스크톱을 검토하고 사용자가 버전을 확정한다. 산출물 유형별 빌드 명령·출력 경로를 제시한다.
2. **저장소 선택**: ‘GitHub 연결’을 누르면 GitHub App의 설치 화면으로 이동한다. 소유자가 대상 저장소만 선택한다. 아르카온은 사용자 선택을 다시 읽고 저장소 이름·범위·예상 파일을 화면에 보여준다. 명시적 ‘검토용 브랜치에 저장’ 클릭 후에만 파일을 쓴다. main 직접 쓰기와 자동 병합은 별도 승인이다.
3. **서버 필요 여부**: 정적 결과물이면 Railway 단계를 ‘필요 없음’으로 명확히 표시한다. 계정·DB·API가 필요하면 ‘Railway 연결’을 눌러 프로젝트 단위 OAuth 동의를 받고, 요청 권한과 예상 과금 자원을 설명한다. 서비스·DB·볼륨·변수는 한 작업씩 클릭 승인 후 만들고 Railway 응답을 재조회한다.
4. **관리자 및 회원 인증**: Railway의 서비스 변수에만 비밀값을 넣는다. 계정 제공자·리다이렉트·쿠키·CSRF·역할·테넌트 분리·탈퇴 경로를 설정하고, 비회원·다른 테넌트 접근 거부를 검사한다. GitHub OAuth 소유자 콘솔 로그인은 고객 플랫폼 회원 인증을 대체하지 않는다.
5. **배포 미리보기**: ‘Netlify 연결’을 누르면 Netlify OAuth 동의를 받은 뒤 대상 팀·사이트를 확인한다. 정적 빌드 결과를 draft deploy로 올리고 실제 URL에서 화면·접근성·API 호출을 검사한다. Git 자동 배포를 선택하면 연결된 브랜치로 push할 때 배포가 시작될 수 있음을 보여 준다.
6. **활성화**: 소유자에게 공개 URL, 비용, 연결 권한, 데이터 위치, 차단/되돌리기 방법을 한 화면에 보여 준다. 배포 잠금, CI, DB·볼륨·인증·복구 증거를 서버에서 재검사한 후 그 버전에 한해 ‘공개 적용’ 클릭을 허용한다. 배포 응답과 공개 URL을 재조회한 뒤 완료로 표시한다.

## 권한과 보안 계약

- **GitHub**: 고정 개인 토큰을 채팅에서 받지 않는다. 선택한 저장소에 설치된 GitHub App과 필요한 Contents 쓰기·Pull requests 쓰기 권한만 요청한다. 토큰은 짧게 발급하여 서버에서만 사용한다. 검토 브랜치와 커밋 SHA를 기록하고 예상치 못한 파일·비밀값을 차단한다.
- **Railway**: 공개 서비스에서는 Login with Railway의 선택 프로젝트 권한을 기본으로 삼고, 해당 작업에 필요한 권한만 요청한다. 프로바이더 OAuth 상태/PKCE, 만료·갱신·연결 해제, 암호화된 토큰 저장을 구현하기 전까지 자동 생성 버튼을 켜지 않는다. 사용자 클릭 하나가 서비스 생성·변수 변경·배포 같은 하나의 명시된 변경과 대응해야 한다.
- **Netlify**: 다중 사용자 연결은 Netlify OAuth2로 설계한다. 개인 액세스 토큰을 폼이나 채팅에 붙여 넣게 하지 않는다. draft 배포와 production 배포 권한을 분리하고, 공개 적용 전 사용자 확인을 받는다.
- **공통**: 모든 외부 쓰기는 소유자·테넌트·서비스 연결·작업 범위·미리보기 digest·CSRF·1회 nonce·만료·멱등키를 검증한다. 공급자 응답을 재조회해 `REQUESTED`와 `VERIFIED`를 분리한다. secret이나 토큰을 로그·PR·생성 코드·브라우저 저장소에 넣지 않는다. 권한 철회와 서비스별 연결 해제 화면을 제공한다. 재시도는 같은 작업 ID로 제한하고, 실패 시 앞서 만든 자원을 자동 삭제하지 않고 비용·상태·수동 정리 방법을 보여 준다.

## 구현 단계와 현재 경계

현재 `/console/railway-setup`은 소유자 전용 클릭형 수동 안내이고, 실제 GitHub 저장·Railway 생성·Netlify 배포 호출은 하지 않는다. 아래의 검증을 각각 별도 PR로 진행한다.

1. 산출물 패키저: 정적/서버 성과물의 출력 경로, 빌드 계약, 비밀값 검사, SHA manifest.
2. GitHub App 연결과 검토 브랜치 쓰기: 설치 범위·권한, 사용자 클릭, 커밋/PR read-back.
3. Railway OAuth 연결 및 계정·DB·볼륨·API 구성: 프로젝트 범위, 비용 확인, 운영 안전 검증.
4. Netlify OAuth 연결 및 draft 배포: 빌드 산출물, 소유자 확인, URL read-back, API 연동 점검.
5. 공개 승인·관측·되돌리기: 특정 SHA와 URL에 묶인 승인, 잠금 재확인, production 배포 검증.

각 단계는 실제 서비스 API 또는 안전한 test double에 대해 성공·거절·권한 철회·중복 클릭·부분 실패·비밀값 누출 방지 시험을 통과해야 한다. 외부 공급자 연결이 없는 상태에서는 `GUIDANCE_ONLY`를 유지한다.

## 근거

- GitHub App permissions: https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app
- Railway OAuth scopes: https://docs.railway.com/integrations/oauth/scopes-and-user-consent
- Railway Public API: https://docs.railway.com/integrations/api
- Netlify API OAuth: https://docs.netlify.com/api-and-cli-guides/api-guides/get-started-with-api/
- Netlify Git deploy behavior: https://docs.netlify.com/deploy/create-deploys/
