# ARKAON 통제된 성찰학습·교훈기억 (Pattern Foundry #049)

조회일: 2026-09-17  
상태: NARANG_RIDER PR #94 / `feat/087-arkaon-reflective-learning` (`dd8abd5`) clean-room analog.

## 상태기계

```text
외부 관찰 → 자기격차 발견 → 개선가설 → 합성 Shadow → 에테르니언 심사 → 운영자 결정 → 교훈기억
```

## 외부 관찰 시 기록

- 타 플랫폼이 해결한 사용자 문제
- 나랑라이더(등록 플랫폼)의 현재 역량
- 잘하는 부분 / 부족한 부분 / 근본원인
- 사용자 영향
- 정책·권한·법률경계 충돌
- 개선 전 Baseline vs 개선 후보 측정값

## 교훈기억 (채택만이 아님)

- 채택된 개선과 성공 원인
- 기각·보류·실패시험·성능·안전 회귀
- 예상과 실제 결과 차이
- 다른 플랫폼에도 재사용 가능한 추상 원칙

## 공유 가능 기억

공식 공개근거, 추상화된 정책, 합성시험 방법, 검토 완료 교훈, 일반화된 UX·보안·개발 패턴만.

## 금지

- 회원·주문·위치·결제·정산·본인확인 자료
- 자기 가중치·운영 Prompt·평가기준 변경
- 실패·기각·회귀 기록 삭제
- 자기 승인, 운영코드 자동 반영, 자동 병합·배포

## 구현

```text
src/apf/reflective_learning.py       # 상태기계·해시체인 이벤트
src/apf/reflective_lesson_store.py   # append-only knowledge 저장
config/arkaon-reflective-learning-policy.json
knowledge/reflective-lessons/          # 불변 교훈 JSON
tests/test_reflective_learning.py
```
