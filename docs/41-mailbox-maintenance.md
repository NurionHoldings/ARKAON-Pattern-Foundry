# #054 우편함 소비·아카이브 운영

이 도구는 우편함의 자동 승인이나 변경 이행을 하지 않는다. 기본 실행은 읽기 전용 계획이며,
`--apply-archive`를 명시한 경우에만 `FULFILLED`·`COMPLETED`·의미상 중복 패킷을
날짜별 `archive/mailbox`로 이동한다.

수정·학습방해·자기개선 요청을 먼저 선별하고 회당 최대 30건을 출력한다. 출력된 `deliver`
목록은 검토 대상일 뿐 승인 목록이 아니다.

중복 판정에는 payload/scope digest 또는 플랫폼+요약 등 강한 식별 근거가 필요하다.
식별 근거가 부족한 패킷은 서로 같다고 추정하지 않으며, 읽을 수 없는 JSON은 `invalid`로
보고하고 이동하지 않는다.

관리 명령은 저장소 위치를 자동 인식한다.

```powershell
.\orchestrator\manage-mailbox.ps1 status
.\orchestrator\manage-mailbox.ps1 plan
.\orchestrator\manage-mailbox.ps1 archive
```

- `status`: 개수와 이번 처리 대상만 표시
- `plan`: 전체 세부 계획 표시, 파일 이동 없음
- `archive`: 아카이브 후보만 날짜별 폴더로 이동

모든 실행 결과는 `state/mailbox-maintenance-latest.json`에 저장한다. relay receipt가 이미
존재하는 자기개선 요청은 다시 deliver하지 않고 아카이브 후보로 분류한다.

운영 불변조건:

- 자동 approve·merge·deploy 금지
- pattern promotion 플래그 변경 금지
- `maximum_outcome` 변경 금지
- 원본은 삭제하지 않고 저장소 내부 archive로 이동
