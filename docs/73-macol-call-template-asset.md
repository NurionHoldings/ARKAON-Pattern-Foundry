# #073 마컬 전화응대 템플릿 자산 초안

상태: 독립 코어 / 실통화·실시간 동기화·배포 미구현. [마컬 제품 기준](https://github.com/NurionHoldings/macol/blob/main/README.md)을 참고한다.

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
