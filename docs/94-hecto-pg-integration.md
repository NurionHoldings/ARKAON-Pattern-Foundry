# 헥토 PG 공통 결제 모듈 — 플랫폼 적용 안내

기준: 2026-11-07 공식 개발자센터, main a26baa71e93f1971151c4bb93e537444e95850a1에서 독립 분리.
상태: **sandbox 연동 코드·오프라인 시험 구현**, 실 PG 테스트베드·계약·인증·운영 전환 미완. main API에 자동 장착하거나 실제 결제를 실행하지 않았다.

## 분석과 적용 방식

각 플랫폼 화면이 직접 금액·비밀키를 만들지 않는다. 플랫폼 서버의 주문 DB가 가격/구매자/상품을 결정하고 이 어댑터가 결제창용 암호화 필드를 생성한다. 브라우저는 FORM POST로 헥토 결제창을 연다. 서버 noti가 해시·상점·주문·금액을 확인하고 별도 HTTPS 거래조회로 정상 원거래를 확인한 후에만 PAID와 PAYMENT_VERIFIED outbox를 한 트랜잭션으로 저장한다. 브라우저 복귀는 조회 화면만 담당한다.

공식 신용카드 FORM은 `method=card`, 노티/조회는 `CA`다. SDK 개요의 CA 예시와 실제 배포 SDK의 card 검사가 상이하므로 FORM 규격을 선택했다. 실제 SDK 코드는 조사만 했고 복사/배포하지 않았다. AES-256/ECB/PKCS7(128bit block padding)은 공급자 프로토콜 호환에만 사용한다. 신규 내부 데이터 암호화 규약으로 권장하는 것이 아니다.

조회 API의 `outStatCd=0021`은 조회 호출 성공일 뿐이다. 실제 거래 `outRsltCd=0000`, 취소금액 0, 상점/조회번호/금액/수단/요청 해시 echo 일치가 필요하다. echo는 새 응답 서명이 아니므로 HTTPS 인증을 유지하며 리다이렉트를 허용하지 않는다. 노티 해시가 bizType/method/trdNo 모두를 보호하지 않으므로 별도 거래조회 없이 PAID로 전환하지 않는다.

## 파일과 실행 경로

| 파일 | 기능 |
|---|---|
| src/apf/hecto_pg.py | FORM 생성, 암호화/해시, 노티 파싱/검증, 영속 sandbox 원장·중복 방지·outbox |
| src/apf/hecto_pg_http.py | 고정 테스트베드 endpoint 거래조회, 시간제한·응답크기 제한·리다이렉트 차단 |
| src/apf/hecto_pg_routes.py | 장착형 FastAPI router. 주문 생성/소유자 조회/노티 |
| src/apf/hecto_pg_config.py | 활성화한 플랫폼만 로드, 상점별 환경변수 키 분리 |
| examples/hecto_pg/integration.py | 호스트 서버 설치 함수와 필수 인증/주문 hook |
| examples/hecto_pg/checkout.js | 동일 출처 인증·CSRF 요청 후 최상위 FORM 이동 |
| examples/hecto_pg/platforms.example.json | 기본 비활성 플랫폼 설정 예시 |
| tests/test_hecto_pg.py | 실제 돈을 사용하지 않는 암호/원장/조회·API 계약 회귀 |

API prefix `/v1/payments/hecto/{platform}`:

- POST `/checkout`: `business_order_id`만 허용. 가격/구매자/키/임의 return URL 필드 거부.
- GET `/orders/{payment_id}`: 인증된 주문 소유자에게만 PENDING/PAID 반환.
- POST `/noti`: UTF-8 form만 수신. 중복 필드·16KiB 초과 거부, 모르는 추가 필드는 허용. 커밋 후 공백 없는 `OK`, 검증 실패 `FAIL`.

동일 business order의 재생성은 409로 막아 중복 청구를 방지한다. 결제창 10분 만료·재시도용 새 attempt와 취소/실패 상태 전이는 후속 구현이 필요하다. 결제창을 닫았다고 PAID/취소로 간주하지 않는다.

## 플랫폼별 적용

| 플랫폼 예시 | 확인할 서버 원본 | 결제 후 작업 |
|---|---|---|
| ARKAON | 사용자·제작 주문·확정 견적 | outbox 소비 후 제작 이용권/작업 시작 |
| 다판다 | 상품·재고·배송 주문 | 재고/주문 DB 트랜잭션과 결속 |
| 더아리랑 | 상품/예약·서비스 주문 | 예약 확정 또는 구매 권한 |
| AI법친 | 사용자·서비스 이용 주문 | 서비스 이용권 부여 |

위 이름은 설정 예시이며 각 저장소를 수정하거나 실제 사이트에 연결했다는 의미가 아니다. 다른 플랫폼도 같은 adapter에 플랫폼 ID와 주문/인증 hook을 추가한다. 서로 다른 판매 주체의 MID를 임의 공유하지 않는다. 계약/상점 등록은 헥토와 확정한다. NURION_PG의 하위사업자/정산 기능은 이 일반 가맹점 수납 모듈과 별도다.

## 호스트 연결 방법

1. `platforms.example.json`을 호스트의 비공개 설정으로 복사한다. 전체 enabled 및 대상 항목 enabled를 명시적으로 true로 지정한다.
2. 항목마다 merchant_name, noti_url, next_url, cancel_url을 지정한다. 콜백은 고정 HTTPS URL이며 query/사용자정보/fragment를 금지한다. noti_url은 위 실제 router 주소와 정확히 일치시킨다.
3. 환경변수에 발급된 sandbox MID/hash key/AES key(UTF-8 32byte)를 설정한다. 키는 채팅·브라우저·저장소에 넣지 않는다.
4. 호스트 인증 코드에서 checkout 권한+CSRF 검사, 주문 소유자 조회, 서버 가격 조회 함수를 작성해 integration.install에 전달한다. 권한 hook 없는 실행 가능한 공개 demo는 제공하지 않는다. body나 임의 헤더를 사용자 신원으로 신뢰하지 않는다.
5. SQLite 파일은 영속 로컬 디스크에 놓는다. 서버리스 /tmp 또는 다중 인스턴스 공동 파일용이 아니다. 운영 다중 인스턴스는 기존 PostgreSQL에 원장·unique constraint·outbox를 이식해야 한다.
6. outbox 소비자는 결제 ID를 고유키로 이용권/재고 처리를 멱등 수행한다. 소비자와 ACK/재시도 워커는 플랫폼별로 추가해야 하며 여기서는 자동 제작/배송을 시작하지 않는다.
7. Netlify 정적 화면은 인증된 서버와 동일 출처 proxy를 구성한다. 쿠키 기반이면 실제 세션 CSRF 정책과 결속한다. 토큰을 JS/URL에 넣어 우회하지 않는다.

기존 billing_entitlement의 DIGEST 모드는 결제 증명이 아니다. 이 PR은 그 정책을 바꾸지 않는다. 실제 서비스 이용권은 검증 원장·billing SoT API에 연결해야 하며 결제 전 제작 시작을 허용해서는 안 된다.

## 구현 범위와 운영 전 남은 것

구현: 일반 카드 결제창(원화), 서버 노티 검증·거래조회, sandbox 원장·단일 outbox 생성, 플랫폼/소유자 격리.
미구현: 계좌이체/가상계좌 입금 처리, PZ 간편결제 노티, 빌키/정기 청구, 취소·부분취소·환불 실행/정산, outbox 소비, PostgreSQL 이식, 각 플랫폼의 실제 로그인/주문 연결, 헥토 테스트베드 왕복·모바일 실화면. 지원하지 않는 노티를 결제 완료로 인정하지 않는다. 일반 카드창에서 간편결제로 전환해 PZ가 오는 경우도 자동 인정하지 않으므로 실제 공개 전 별도 구현·검증 또는 제공자 계약 설정으로 제한해야 한다.

운영 환경은 Merchant 생성 단계에서 차단한다. 운영 전환에는 다음이 필요하다: 계약·수단별 심사, 플랫폼별 허용 MID/도메인, HTTPS 수신 endpoint/방화벽, 환불·실패·대사 경로, 테스트베드 왕복, 독립 검토 및 사용자 운영 승인. 이후 소액 실결제와 취소를 별도 승인 범위로 시행한다. 키나 계약이 없다고 가짜 성공을 반환하지 않는다.

## 검증

`python -m pytest tests/test_hecto_pg.py -q`
`python -m pytest -q`
`ruff check src tests examples/hecto_pg/integration.py`

모든 PG 응답 fixture는 TEST_DOUBLE. 실제 헥토 연결·상점 승인·운영 완료 증거가 아니다. 같은 세션의 자체 재검토를 별도 독립 감사로 표기하지 않는다.

## 공식 근거

- https://developers.hectofinancial.co.kr/docs/pg
- https://developers.hectofinancial.co.kr/docs/api/pg/getting-started/00-preparation
- https://developers.hectofinancial.co.kr/docs/api/pg/credit-card/01-card-payment
- https://developers.hectofinancial.co.kr/docs/api/pg/credit-card/03-card-noti
- https://developers.hectofinancial.co.kr/docs/api/pg/getting-started/02-noti
- https://developers.hectofinancial.co.kr/docs/api/pg/transaction-management/01-realtime-inquiry
- https://developers.hectofinancial.co.kr/docs/api/pg/credit-card/09-card-cancel
- https://developers.hectofinancial.co.kr/docs/api/pg/sdk/01-sdk
- 실제 SDK 확인: https://tbnpg.settlebank.co.kr/resources/js/v1/SettlePG_v1.2.js
