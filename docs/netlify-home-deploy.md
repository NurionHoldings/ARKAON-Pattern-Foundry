# ARKAON Netlify 홈 화면 배포

저장소 루트의 `netlify.toml`이 `python tools/build_netlify_site.py`를 실행하고
`dist/`를 게시한다. `netlify-site/`에는 모바일 대응 홈 화면, 로고·명함 가격과
제작 과정 안내가 포함된다. 폰트·사진 등 외부 자산에 의존하지 않는다.

## 백엔드 연결

운영 Python API를 별도 서비스에서 HTTPS로 준비한 경우 Netlify 빌드 환경 변수
`ARKAON_API_ORIGIN=https://<API 도메인>`을 설정한다. 빌드 과정이
`/inspection/*`을 같은 사이트 경로에서 API로 프록시한다. 비밀값 또는 경로를
URL에 넣지 않는다. 이 값이 없으면 홈 화면은 정상 게시되지만 체험 시작 버튼을
표시하지 않고 연결 준비 상태를 안내한다.

체험 백엔드에는 `APF_DEMO_INSPECTION_ID`, 별도의 32자 이상
`APF_DEMO_SESSION_SECRET`가 필요하다. 로고·명함 미리보기는 Python API에서
생성한다. Netlify의 정적 파일만으로 시안 생성, 계정·결제, 결과물 인도를 제공할
수 없다. API의 `/ready`가 200인지, `/inspection` 로그인·미리보기·청구서 초안이
같은 도메인에서 동작하는지 배포 후 확인한다.

기존 `nurionpg` Netlify 사이트는 다른 서비스 이름이다. 이 저장소를 해당 사이트에
덮어쓰지 말고 ARKAON용 사이트와 도메인에 연결한다.

## 게시 전 확인

- Draft PR 체인을 검토하고 최종 코드를 통합한다.
- Netlify 사이트의 Git 저장소·브랜치, `netlify.toml`, 게시 폴더 `dist`를 확인한다.
- 백엔드 운영 DB, 볼륨, OAuth, 결제 검증 API와 비밀값을 설정한다.
- 데스크톱·모바일 첫 화면, 체험 프록시, 로그인 쿠키, 결제 권한 및 파일 인도를
  실제 사이트에서 검증한다.

홈 화면을 게시하는 것과 전체 제작 서비스의 운영 승인 상태는 별도로 판단한다.
