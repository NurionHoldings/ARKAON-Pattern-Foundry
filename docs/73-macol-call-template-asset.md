# #073 마컬 전화응대 템플릿 자산 초안

상태: 독립 템플릿 생성기와 수동 브라우저 통화·메뉴 동기화 앱 초안. 010 발신 감지·발신자 화면 자동 표시·실제 회선 연동 미구현. [마컬 제품 기준](https://github.com/NurionHoldings/macol/blob/main/README.md)을 참고한다.

`apf.call_template.CallTemplateRequest`를 입력하여 `build_call_template`로 재현 가능한 초안 자산을 생성한다. 개인 소개, 용건 선택, 자료 목록, 통화 요청 또는 메시지 남기기 메뉴가 포함된다. 내용과 소유자 ID에 묶인 SHA-256 식별자를 제공하며, 자산은 항상 `DRAFT`, `NOT_CONNECTED`로 시작한다.

메뉴는 양쪽 참가자에게 같은 위치를 보여주는 `shared_navigation` 계약을 포함한다. 실제 동기화 서버에서는 참가자 인증과 메뉴 접근 권한을 확인한 뒤 이벤트를 양쪽에 전달한다. 다운로드는 참가자별 명시적 실행, 양식 편집은 필드별 역할 검사, 충돌은 명시적 검토, 재접속은 세션 재인증이 필요하다. 이 파일은 이 정책을 실행하는 서버를 대신하지 않는다.

## 사용 예

```python
from apf.call_template import CallTemplateRequest, build_call_template

draft = build_call_template(CallTemplateRequest(
    tenant_id="example", owner_id="owner-1", slug="intro",
    display_name="예시 사용자", introduction="안녕하세요.",
    purpose_prompts=["소개 요청", "상담"], material_titles=["소개서"],
))
assert draft.telephony_state == "NOT_CONNECTED"
```

## 후속 구현 경계

- 소유자 확인, 저장소의 tenant 격리, 버전 변경과 공개 승인.
- 실시간 공동 세션의 인증·이벤트 순번·중복/역순 처리, 필드 충돌, 두 기기 증거.
- 음성 통화 구현 및 010/보이는 ARS 실회선 연결은 별도 실증. 브라우저 초안은 통신망 자동 팝업의 증거가 아니다.
- 에테르니언의 독립 검사 후에만 검증 상태를 갱신한다.

## 제품 목표: ARKAON 제작 → 웹 게시 → 마컬 보이는 전화응대

ARKAON에서 개인별 템플릿을 만들고, 소유자 승인 뒤 공개 웹 주소에 게시한다. 같은 게시 버전을 마컬 통화 세션의 화면으로 사용하며, 메뉴와 양식 변경은 양측 화면에 동기화한다. 게시 URL과 통화방 초대 URL은 서로 다른 수명과 권한을 가진다. 공개 URL에 통화 토큰이나 개인의 입력 내용을 넣지 않는다.

전화 진입은 지원 범위별로 구분한다.

1. 지원 앱·전화 앱 또는 검증된 번호 연동이 통화 이벤트를 제공할 때 발신자에게 화면을 즉시 표시한다. 단말·OS·앱 버전별로 실제 자동 표시율을 측정한다.
2. 자동 표시가 불가능하면 통화 맥락에서 URL SMS를 제공할 수 있는지 메시지의 성격, 전송 근거, 번호 수집·사용 범위, 수신 거부 처리, 발송사업자 정책을 법률·운영 검토로 확정한다. 단순 연결 유지나 무응답을 수신 동의의 근거로 기록하지 않는다. 광고성 콘텐츠는 별도의 수신동의 요건을 적용한다. 우선 시험 단계에서는 명시적 메뉴 선택 후 일회용 링크를 발송한다.
3. SDK가 설치·허용된 Android에서는 앱이 화면을 자동 표시할 수 있다. 앱이 없는 단말에 일반 URL SMS만 도착한 경우에는 브라우저 자동 실행을 전제로 하지 않고, 링크를 누르면 만료 가능한 통화 세션으로 진입한다. iOS는 알림·링크 선택 흐름을 별도 검증한다. 문자 거절·전송 실패·데이터 불능 시 음성 안내 또는 일반 전화로 돌아간다.

실회선 연결 규격이 확정되기 전에는 `publication_state=DRAFT`, `telephony_state=NOT_CONNECTED`를 유지한다. 게시 기능, 음성 안내/선택, 메시지 발송, 일회용 링크, 실회선 통화 식별자, 통화 종료 및 삭제 정책은 각각 테스트 및 감사 후에 구현한다.

## 독립 앱 초안 생성 (마컬 저장소 불필요)

```bash
python -m apf.macol_export \
  --request knowledge/communication/macol-standalone-request-example.json \
  --output /tmp/example-macol-app
cd /tmp/example-macol-app
python -m pip install -r requirements.txt pytest httpx
python -m pytest -q
```

`apf.macol_export`는 패키지 내부에 포함된 MACOL 브라우저 실험실의 FastAPI 서버, 프로필 화면, 설치형 웹앱 자산, Dockerfile, CI, 시험 코드를 새 디렉터리로 복제하고 입력 소유자의 이름·소개·용건을 반영한다. 기존 경로에는 덮어쓰지 않는다. 템플릿 초안과 콘텐츠 digest는 `template.json`에 남는다. 생성물은 새 계정 인증이나 010 전화망을 자동으로 개설하지 않으며 게시·배포도 자동 수행하지 않는다.

### 2026-09-25 실기기 보고: FAIL (전화망 연결과 화면 자동 표시)

수신 010 번호와 발신 010 번호로 일반 전화 앱의 발신 시험을 수행했다. 사용자가 후속 확인한 결과 **일반 음성통화는 정상, 발신자 화면 표시는 FAIL**이다. 두 번호는 공개 코드·문서에 기록하지 않는다. 발신자 Android용 시험 앱은 제작되었지만 설치·권한 설정·알림 터치를 요구하므로 제품 성공 기준을 충족하지 않는다.

### 2026-09-25 제품 기준 잠금: 발신자 사전 조치 0건

발신자는 마컬을 설치하거나 가입하지 않고, 통화 권한을 허용하거나 문자·알림을 누르지 않는다. 기존 전화 앱에서 평소처럼 등록 010 번호로 발신할 때 음성통화와 동시에 상대 템플릿이 자동으로 열리고 메뉴 선택이 수신자 화면에 즉시 동기화되어야 한다. 어떤 설치·클릭이 필요해도 제품 완료는 FAIL이다. 앱 기반 시험판을 운영 성공 증거로 승격하지 않는다.

이를 실현할 통신사/기본 전화 앱의 네이티브 연동 또는 IMS Data Channel 연동의 국내 실제 지원 여부를 확인한다. 사업자와의 번호 등록·전화 이벤트 전달·단말 통화 화면 표시·양측 세션 동기화 계약이 없는 현재 상태는 `NETWORK_INTEGRATION_BLOCKED`다. 기술 실증 조건과 사업자 문의 항목은 마컬 저장소의 `docs/no-caller-setup-network-path.md`를 기준으로 한다.
