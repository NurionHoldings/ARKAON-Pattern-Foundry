# 노가다뉴스·부업장터 메타데이터 파일럿 (#041)

## 판정

노가다뉴스와 부업장터의 사용자 제공 구상 및 공개 아키텍처 메타데이터만 대상으로
결정적 읽기 전용 분석 어댑터를 구현했다. 실제 저장소 연결과 코드 분석은 실행하지
않았으며 두 manifest에 `NOT_RUN_UNAVAILABLE`로 기록했다. 따라서 이 단계는 자체 플랫폼
완전 분석이나 재사용 증명이 아니라 **메타데이터 파일럿 구현**이다.

두 파일럿의 모든 결과는 `ETHERNIAN_REVIEW_REQUIRED`인 패턴 후보일 뿐이다. Intent_DNA
변경, 플랫폼 쓰기, `OWNED_ASSET` 승격은 계속 금지된다.

## 노가다뉴스 후보

- 출처 검증을 상태와 증거로 결합하는 provenance 원장
- 초안 검토와 발행을 분리하는 2단계 승인
- 정정 이력까지 보존하는 편집 상태전이

## 부업장터 후보

- 제공자·참여자 조건을 함께 지키는 벌거리 matching
- 참여부터 검증·정산까지 이어지는 수익기회 lifecycle
- 사용자 확인을 넘지 않는 ARKAON 위임 경계
- 완료 증거와 신뢰된 금액 근거를 요구하는 정산

## MJN과의 비교

MJN #030의 원본을 복사하지 않고 검토 대기 중인 추상 후보 이름과 행동 경계만 비교했다.
노가다뉴스에서는 evidence-bound approval과 auditable transition을, 부업장터에서는
principal/ownership 재검증, idempotent transition, financial SoT audit chain을 비교
대상으로 기록했다. 이 비교는 공용 패턴 승격 또는 실제 재사용을 증명하지 않는다.

## 안전·재현 경계

manifest는 플랫폼 신원, 사용자 선언 소유관계, 권한 증거 해시, 허용 surface, 금지
항목, 업무흐름과 그 canonical hash를 포함한다. validator는 다른 플랫폼, 권한 또는
workflow로 바꿔치기하거나 저장소 연결·코드 분석을 실행했다고 주장하는 입력을
fail-closed 처리한다. 개인정보·비밀·자격증명·세션·토큰·쓰기 권한은 수집 범위가
아니다.
