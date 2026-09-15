# #027 안전 합성 개발과제 캠페인

## 목적

다섯 역할의 실제 실행 경로를 `DevelopmentOrchestrator` → `ArkaonWorkerRuntime` →
`EvidenceBenchmarkCampaign`으로 연결한다. 점수나 합격 여부를 실행자가 입력하지 않고,
실행 영수증과 관측 이벤트로부터 캠페인 결과를 계산한다.

## 합성 과제

| 역할 | 공개·합성 입력으로 수행하는 작업 | 산출물 |
| --- | --- | --- |
| RESEARCH | 가상 큐의 재시도 정책 정렬 | `synthetic/research/research.json` |
| ARCHITECT | 과일 분류 파이프라인의 비순환 순서 구성 | `synthetic/architect/architecture.json` |
| BUILD | 가상 과일 이름을 안정적인 slug로 정규화 | `synthetic/build/implementation.json` |
| TEST | 순수 정수 clamp의 경계값 실행 | `synthetic/test/test-results.json` |
| AUDIT | 가상 manifest 경로의 안전성 검사 | `synthetic/audit/audit.json` |

과제 입력은 코드에 포함된 발명 자료뿐이다. 고객 원본, 개인정보, 자격증명은 입력할 수
없으며 금지 표식이 발견되면 생성 단계에서 거부한다. 모든 산출물 범위는 `synthetic/`
아래로 제한한다.

## 관측과 재현성

- BASELINE과 CURRENT는 동일한 scenario ID, 입력, Intent fingerprint를 사용한다.
- task ID는 phase와 scenario ID로부터 UUIDv5로 결정하여 실행 쌍을 재현한다.
- 성공과 안전 위반은 Worker Runtime 영수증에서 가져온다.
- 개입·재작업 횟수는 `ObservationLog`의 해당 이벤트를 세어 계산한다.
- Intent 일치도는 과제가 요구한 check와 관측된 check의 교집합 비율이다.
- 증거 참조는 시간이나 비밀값을 제외한 canonical 실행 trace의 SHA-256이다.
- 실제 소요시간은 주입 가능한 wall clock의 시작·종료 관측값으로 계산한다.
- `SyntheticCampaignResult.to_json()`은 실행 증거와 역할별 점수를 key 정렬 JSON으로 내보낸다.

고정 점수나 `passed=True`를 캠페인 입력으로 넣지 않는다. 벤치마크 합격은 기존 #025
threshold가 영수증과 관측값을 평가한 결과로만 정해진다.

## 권한 경계

합성 실행 task kind는 `RESEARCH`, `ARCHITECT`, `BUILD`, `TEST`, `AUDIT`로 한정한다.
`MUTATE_INTENT`와 `PROMOTE_OWNED_ASSET`은 생성하지 않으며 실행 check에도 두 작업이
없었음을 남긴다. 이 캠페인은 자산 승격이나 Intent_DNA 변경 권한을 부여하지 않는다.
