# #028 실전 관측 원장·파일럿 준비

## 목적

합성 파이프라인 검증과 실제 업무 효율 증거를 분리한다. `SYNTHETIC_PIPELINE_ONLY`는 배관과 안전 게이트 검증에만 쓰고, 실제 효율 판정에는 에테르니언이 관측·서명한 `PILOT_OBSERVATION`만 사용한다.

## 신뢰 경계

- 아르카온 worker는 작업 영수증을 만들지만 개입·재작업·시작·종료 수치를 직접 보고하지 않는다.
- 원장은 다음 순번·직전 해시·관측 초안을 담은 불변 challenge만 발급한다. 원장 밖의 에테르니언 관측자가 Ed25519 개인키로 challenge 전체를 서명해 attestation envelope을 만든다.
- 원장은 신뢰 공개키만 보유하며 envelope만 받는다. 따라서 원장이나 worker를 가진 호출자는 에테르니언 서명을 생성할 수 없다.
- 원장에는 제한된 enum, 안전한 식별자, 불투명 증거 참조와 안전검사를 통과한 실행 영수증 메타데이터만 저장한다. 업무 원문을 받는 필드는 없다.
- 식별자와 증거 참조는 `learning_safety`로 검사하며 PII, secret, URL·경로형 원문을 거부한다.

## 무결성 규칙

각 사건은 순번, 직전 해시, 정규화 payload 해시와 관측자 서명을 가진다. 추가 시점과 평가 직전에 아래를 fail-closed로 재검사한다.

1. 순번과 해시체인 연속성
2. 이벤트 ID 중복
3. 실행 영수증 재사용
4. 관측시간 역행
5. 관측자·키 경계
6. payload 해시와 서명
7. trial의 `START → (REWORK | INTERVENTION)* → FINISH` 경계
8. stale challenge, attestation replay, 초안 변조, 잘못된 키, 순번 이탈

## 캠페인 변환과 판정

원장은 사건을 trial 단위로 묶어 시간, 재작업 횟수, 에테르니언 개입 횟수를 파생하고 `TrialEvidence`로 변환한다. baseline/current의 동일 scenario·role 쌍이 없으면 캠페인이 거부된다. 모든 역할의 충분한 paired sample이 없으면 `EvidenceBenchmarkCampaign`의 역할 커버리지·표본수 게이트 때문에 실제 효율 PASS가 될 수 없다. 임계값은 `BenchmarkThresholds`로 주입하며 원장에 성과 수치를 하드코딩하지 않는다.
