# 라이더 모빌리티 광장 기반계층 (Pattern Foundry)

조회일: 2026-09-16
상태: NARANG RIDER 기능이 막 시작된 시점에 추출한 **재사용 기반 계약**. 운영 광장·실시간 위치는 **BLOCKED**.

## 왜 넣는가

나랑라이더의 광장은 배차 대기열이 아니다. 지사에 묶인 휴식·대기·동료공지·안전권고·공동물류
공유지다. 시작 단계에서 이 경계를 고정하지 않으면 재실 인원, 대기시간, 거친 위치가 곧
가용성 추론·등급·보복 배차로 새기 쉽다.

## 기반 불변조건

1. 광장은 `branch_id`와 목적 집합으로만 등록된다. 목적 없는 광장은 거부한다.
2. 위치는 정밀도 3~5의 거친 셀만 허용한다. GPS·주소는 저장하지 않는다.
3. 가입은 명시적 동의와 12시간 이하 TTL이다. 탈퇴는 즉시 반영된다.
4. 공개 재실은 **인원 수**다. 식별자 목록이 아니고 배차 입력이 아니다.
5. 공지는 PII·좌표를 담을 수 없고 `dispatch_signal`은 항상 false다.
6. ARKAON 조언은 advisory-only다. 대기열, 감시, 유휴 제재, 오퍼 순위, 상시추적,
   가용성 추론은 금지 사용이다.

## 나랑라이더에 남기는 것

주문 수락, FIFO 배차, 정산, 실시간 내비, 기기 인증은 이 모듈에 넣지 않는다. 광장 가입이
라이더 가용 상태로 바뀌는 어댑터도 넣지 않는다.

## 추적성

| 요구사항 | 구현 | 시험 |
|---|---|---|
| 거친 셀만 | CoarsePlazaCell | test_precise_or_identity_cells_are_rejected |
| 동의·비식별 재실 | join / occupancy | test_join_requires_consent_and_occupancy_hides_identities |
| 공지 ≠ 배차 | post_notice | test_notice_is_not_a_dispatch_signal_and_strips_pii |
| 노동통제 금지 | assert_use_allowed | test_arkaon_advice_is_advisory_and_cannot_control_labor |
| 탈퇴 | leave | test_withdrawn_or_expired_membership_cannot_post |
