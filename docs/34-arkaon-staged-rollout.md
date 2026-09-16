# ARKAON 단계적 롤아웃 (Pattern Foundry)

조회일: 2026-09-16
상태: NARANG RIDER `rollout.py` 아날로그 이식. live 배포는 **BLOCKED**.

## 원칙

릴리스는 REGISTERED → SHADOW → PILOT → REGIONAL → NATIONAL 순으로만 승격한다.
SHADOW는 공개 규칙 fallback을 유지한 채 관측만 한다. PILOT은 지사 정확도 통과와
에테르니언·지사 운영자의 독립 승인이 필요하다. 같은 사람이 두 역할을 겸할 수 없다.

지역 승격은 선택한 모든 로컬 허브가 PILOT을 통과해야 한다. 전국 승격은 전국 정확도
판정과 에테르니언·운영자의 독립 승인이 필요하다. kill switch는 릴리스와 모든 지사를
PAUSE하고, 한 지사 롤백은 다른 지사를 끄지 않는다.

출력 권한은 ADVISORY / EXPLANATION / FORECAST만 허용한다. 배차 실행권은 없다.

## 추적성

| 요구사항 | 구현 | 시험 |
|---|---|---|
| Shadow + fallback | ArkaonRolloutController.start_shadow | test_release_starts_in_shadow_with_public_fallback |
| 독립 승인 | promote_pilot | test_failed_accuracy_or_same_person_approval_blocks_pilot |
| 전국 판정 | promote_national | test_national_promotion_requires_national_verdict_and_independent_approval |
| Kill switch | kill_switch | test_kill_switch_pauses_release_and_every_branch |
