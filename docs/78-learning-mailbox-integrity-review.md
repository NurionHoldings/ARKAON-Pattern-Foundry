# 학습 결과 후속 점검: 우편함 무결성

2026-10-17 main 기준 점검. 저장소 inbox에는 JSON 패킷이 없으며,
PC 로컬 수집·예약 작업 실행 여부는 이 점검으로 확인할 수 없다.

## 확인한 근거와 보완

- `evidence/self-improvement/arkaon-abstract-instruction-self-diagnosis-v1.json`의
  AI-002는 `HOLD_SEPARATE_SCOPE`다. 승인 이해도 질문·화면은 구현하지 않는다.
- 기존 자기개선 요청 3건의 원장은 `OWNER_APPROVED`, 결과 증거는
  `DEPLOYMENT_APPROVAL_PENDING`이다. 증거의 상태만으로 원장을 승격하지 않는다.
- 우편함 공통 로더는 UnicodeError를 처리하지 않아 손상 인코딩 하나로
  나머지 요청 점검까지 중단할 수 있었다. 잘못된 파일을 invalid로 보고하고 원본은 유지한다.
- 전달완료 아카이브는 요청 ID만 대조했다. 이제 self-improvement 경로에서
  현재 패킷의 schema, 상태, propose-only 경계와 canonical scope SHA-256을 검증하고,
  receipt의 scope digest 및 비어 있지 않은 PR URL을 확인해야 아카이브한다.
- scope 충돌·변조·불완전 receipt는 invalid로 보고하고 이동하지 않는다.
  다른 연구 패킷은 같은 request_id라는 이유로 전달완료 처리하지 않는다.
- receipt schema가 다르거나 항목이 객체가 아니면 전달 증거로 사용하지 않는다.

## 검증 및 롤백

인코딩 손상 뒤 정상 파일 유지, scope·권한 변조, 잘못된/불완전 receipt,
동일 ID 연구자료, receipt schema 이상과 정상 relay-cycle 아카이브를 회귀시험한다.
검증은 운영 승인이나 배포 승인이 아니다. 자동 병합·배포·외부 학습 호출은 추가하지 않는다.
롤백은 본 PR을 revert한다. 이 변경은 DB migration이나 기존 패킷 포맷을 바꾸지 않는다.
독립된 아르카온 실행 및 에테르니언 이중 검증 증거를 생성한 것으로 간주하지 않는다.
