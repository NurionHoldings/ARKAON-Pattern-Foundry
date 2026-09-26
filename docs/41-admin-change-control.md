# ARKAON 관리자 변경 통제·Reflection Bridge (Pattern Foundry #050)

조회일: 2026-09-17  
상태: NARANG_RIDER `feat/084-admin-change-control` clean-room analog.

## 역할

#048 경험·운영 감사 제안과 #049 성찰학습 상태기계를 **승인→미리보기→부분반영** 루프로
연결합니다. Foundry는 플랫폼 저장소를 직접 변경하지 않으며, 승인된 범위의 **반영 의도만**
기록합니다.

```text
experience finding → reflective case seed → shadow metrics
  → eternian-review inbox → operator-decision → reflective-lessons append
```

## 변경 통제 단계

| 단계 | 의미 |
|------|------|
| DRAFT | 제안 등록 |
| PREVIEWED | diff 미리보기 완료 (preview-only) |
| ETERNIAN_REVIEWED | 에테르니언 검토 digest 기록 |
| OPERATOR_APPROVED | 운영자(인석형) 범위 승인 |
| PARTIALLY_APPLIED | 승인 범위 반영 **의도** 기록 (intent-only) |
| ROLLED_BACK | rollback token으로 의도 철회 |

## inbox 3단계와의 대응

| inbox | reflection | change control |
|-------|------------|----------------|
| research | OBSERVED…HYPOTHESIS | DRAFT |
| eternian-review | SYNTHETIC_SHADOWED | PREVIEWED → ETERNIAN_REVIEWED |
| operator-decision | ETERNIAN_REVIEWED → OPERATOR_DECIDED | OPERATOR_APPROVED → PARTIALLY_APPLIED |

`operator-decision`은 오케스트레이터가 직접 쓰지 않습니다. 에테르니언 digest가 있는
패킷만 `promote_to_operator_decision()`으로 수동 승격합니다.

## 경계

- 최대 권한: `IMPROVEMENT_PROPOSAL` + intent-only partial apply
- `automatic_merge_or_deploy`, `production_change_allowed`, `automatic_learning` 금지
- preview 없이 eternian review 기록 금지 (정책 기본값)
- 승인 없이 partial apply 금지
- 회원·주문·위치·결제·정산·본인확인 자료 change control 진입 금지

## 구현

```text
src/apf/admin_change_control.py     # preview, partial-apply intent, rollback
src/apf/reflection_bridge.py        # #048 → #049 → inbox 연결
config/arkaon-admin-change-control.json
state/change-control/               # change proposal JSON
knowledge/reflective-lessons/       # operator 결정 후 append-only 교훈
tests/test_admin_change_control.py
tests/test_reflection_bridge.py
```

## 콘솔 API

- `GET /v1/console/inbox` — research / eternian-review / operator-decision 패킷 목록
- `GET /v1/console/change-proposals` — change proposal 목록
- `GET /v1/console/change-proposals/{id}` — proposal 상세·preview scope
- `POST /v1/console/change-proposals/{id}/preview` — preview-only diff digest
- `POST /v1/console/change-proposals/{id}/operator-approval` — 운영자 범위 승인
- `POST /v1/console/change-proposals/{id}/partial-apply` — intent-only 부분반영 + rollback token

## 운영

오케스트레이터 실행 시 experience audit finding마다 reflection bridge가
`inbox/eternian-review/*-reflection.json`과 `state/change-control/change-refl-*.json`을
생성합니다. 실제 플랫폼 코드·운영환경 반영은 인석형 승인·미리보기·시험계획 확인 후
검토 브랜치에서만 수행합니다.
