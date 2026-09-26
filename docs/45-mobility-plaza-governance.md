# ARKAON 모빌리티 광장 거버넌스 (Pattern Foundry #079)

조회일: 2026-09-17  
상태: NARANG `#079-mobility-plaza-governance` clean-room analog. #046 foundation 위 정책 심사층.

## 역할

- consent TTL·공지 TTL·forbidden labor control 검증
- occupancy가 dispatch 입력·식별자 노출이 아님을 확인
- 플랫폼 `config/mobility-plaza.json` 금지 플래그 감사
- 실패·주의 finding → `inbox/eternian-review/*-plaza-gov.json`

## 경계

- 배차·감시·상시추적·가용성 추론 금지 (#046 불변조건 유지)
- ARKAON 조언 advisory-only
- production dispatch from plaza 금지

## 구현

```text
src/apf/mobility_plaza_governance.py
src/apf/mobility_plaza_bridge.py
config/arkaon-mobility-plaza-governance.json
state/plaza-governance/
tests/test_mobility_plaza_governance.py
```
