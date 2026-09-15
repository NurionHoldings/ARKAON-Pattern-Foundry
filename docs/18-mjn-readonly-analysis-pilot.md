# MJN 읽기 전용 분석 파일럿 (#030)

## 판정

MJN `main`의 고정 커밋을 첫 자체 플랫폼 분석 대상으로 사용했다. 분석 결과는 세 개의
추상 패턴 후보이며 모두 `CANDIDATE / ETHERNIAN_REVIEW_REQUIRED`다. 구현 자산 또는
`OWNED_ASSET`으로 승격하지 않았다.

## 범위와 근거

- 대상: `NurionHoldings/mjn`의 고정 commit/tree
- 관찰 범위: principal·ownership, 거래 상태전이·idempotency, 결제·정산·audit 경계
- 증거: 저장소·커밋·경로·Git blob identity로 구성한 canonical source identity와 그
  SHA-256 참조만 저장
- 제외: 원문 코드와 문구, 고객정보, 자격증명, 비밀, 내부 가격 및 계약정보

MJN과 Pattern Foundry는 동일 소유자의 first-party 시스템이다. 이번 위임은 분석만
허용하며 코드 재배포 라이선스로 해석하지 않는다. 따라서 source repository는 읽기
전용이고, clean-room 산출물에는 추상 명세와 provenance reference만 남는다.

## 후보

1. `principal-ownership-recheck`: 인증 principal과 현재 권한·resource ownership을 사용
   시점에 재검증하고 요청 입력으로 범위를 넓히지 않는 경계.
2. `transactional-idempotent-transition`: retry와 동시성에서 동일 intent는 같은 결과를
   재생하고 다른 intent의 key 충돌과 복수 승자를 차단하는 상태전이.
3. `financial-sot-audit-chain`: 금액과 지급 상태를 신뢰된 SoT에서 파생하고, 의존 전이
   직전에 재검증하며 불변 snapshot과 actor-scoped audit 증거를 보존하는 경계.

후보는 에테르니언 검토 전까지 공용 패턴, 독립 구현 또는 소유 자산이 아니다.

## 재현·감사

`knowledge/pilots/mjn-030.json`이 read-only manifest다. `validate_readonly_manifest()`는
canonical identity의 SHA-256을 다시 계산하고 authorization, provenance, clean-room,
review 및 promotion 잠금을 fail-closed 검증한다. 민감정보가 발견되는 경우 값을
반출하지 않고 violation code만 보고한다.

역할 기록: `RESEARCH → ANALYZE → ARCHITECT → BUILD → TEST → AUDIT`.
