# #054 우편함 소비·아카이브 운영

이 도구는 우편함의 자동 승인이나 변경 이행을 하지 않는다. 기본 실행은 읽기 전용 계획이며,
`--apply-archive`를 명시한 경우에만 `FULFILLED`·`COMPLETED`·의미상 중복 패킷을
날짜별 `archive/mailbox`로 이동한다.

수정·학습방해·자기개선 요청을 먼저 선별하고 회당 최대 30건을 출력한다. 출력된 `deliver`
목록은 검토 대상일 뿐 승인 목록이 아니다.

```powershell
python -m apf.mailbox_maintenance --foundry-root .
python -m apf.mailbox_maintenance --foundry-root . --apply-archive
```

운영 불변조건:

- 자동 approve·merge·deploy 금지
- pattern promotion 플래그 변경 금지
- `maximum_outcome` 변경 금지
- 원본은 삭제하지 않고 저장소 내부 archive로 이동
