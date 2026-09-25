# 69. 이름@ 개인 페이지 독립 코어

`apf.name_at`는 승인된 프로필만 게시·검색 가능한 독립 코어다. 이미지 최대 3개,
영상 1개를 첨부할 수 있다. `name_at_service`는 계정·초안·파일 업로드·미리보기·게시,
공개 HTML, `이름@` 선택 페이지, 사이트맵과 robots.txt를 제공한다. 이미지는 실제
형식 검사 후 재저장해 메타데이터를 제거한다. 영상은 ffprobe로 코덱·크기·길이를
검사한다. 저장 위치는 운영 환경의 영속 볼륨이다.

별도 계정은 12자 이상의 비밀번호를 scrypt로 해시하고 HTTPS 쿠키와 CSRF 토큰으로
관리한다. 이메일·실명 신원 인증이나 사칭 신고 처리는 아직 없다. 이름은 사람별로
독점하지 않으며 `이름@` 조회에서 동명이인을 모두 반환한다.
수정 초안은 다시 승인받아야 하며 철회 즉시 내부 검색·사이트맵에서 빠진다.

게시 시 네이버·빙 IndexNow에 공개 프로필과 `이름@` 선택 페이지를 전송하고,
구글 Search Console Sitemap API에 사이트맵을 제출한다. 검색 전송 응답은 `received`,
설정 누락은 `setup_required`, 실패는 `failed`로 기록한다. 수집·색인·상위 노출을
의미하지 않는다. 다음은 공식 사이트 등록 신청과 심사가 필요한 `manual_review`로 표시한다.
플랫폼 도메인의 소유 확인과 다음 최초 신청은 운영자가 공식 계정에서 완료해야 한다.

## Railway 배포 준비

`Dockerfile`과 `railway.json`은 `/health` 경로를 확인한다. 운영에서는 PostgreSQL의
`DATABASE_URL`, `APF_CONSOLE_SESSION_SECRET`, `APF_ENV=production`이 기존 API에
필요하다. 이름@에는 `APF_NAME_AT_ENABLED=1`, `APF_NAME_AT_ORIGIN=https://실제도메인`,
`APF_NAME_AT_DATA=/data`, `APF_NAME_AT_SECRET`(32자 이상)이 필요하다. Railway
영속 볼륨을 `/data`에 연결하지 않으면 운영 배포하면 안 된다. 수평 확장은 SQLite
단일 볼륨을 공유할 수 없으므로 현재 1개 인스턴스로 제한한다.

IndexNow를 사용하려면 영숫자 키 `APF_NAME_AT_INDEXNOW_KEY`를 설정한다. 키 파일은
`/{key}.txt`로 제공된다. 구글 서비스 계정 JSON은 비밀 변수
`APF_NAME_AT_GOOGLE_SERVICE_ACCOUNT_JSON`에 입력하고 Search Console 속성에
해당 계정을 권한자로 추가한다. 필요하면 `APF_NAME_AT_GOOGLE_PROPERTY`를 지정한다.
다음은 [공식 검색등록](https://register.search.daum.net/)에서 플랫폼 도메인을 신청한다.
공개 도메인과 계정 소유 확인 전에는 전송 성공이나 검색 노출을 완료로 표시하지 않는다.

## 아직 남은 운영 조건

신원 확인·사칭 신고, 요청 제한, 미사용 미디어 정리, 저장소 백업/복구, 외부 검색
색인·순위의 실제 확인, 다음 등록 심사 결과 확인 및 ARKAON 대화형 생성 연동은
운영 출시에 앞서 별도 구현·검증이 필요하다. 현재 서비스는 코드 수준의 배포 준비만
마쳤으며 라이브 Railway 서비스와 검색엔진 계정은 연결되지 않았다.

기존 `PRODUCT_IMPLEMENT_HOLD`와 운영 전 검증 게이트는 이 모듈로 해제되지 않는다.
