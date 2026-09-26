# ARKAON 가동 전 준비 점검 (Pattern Foundry #082)

조회일: 2026-09-17  
상태: NARANG `#082-predeployment-readiness` clean-room analog.

## 역할

PC/Foundry 가동·등록 플랫폼 연결 **전** mandatory check를 실행합니다.

- shared-policy, resource-limits, platforms registry
- admin change control, public surface, research watch, reflective learning, experience audit 정책
- inbox/state 디렉터리 준비

실패 시 orchestrator run이 **fail-closed**로 중단됩니다. 자동 deploy는 없습니다.

## 구현

```text
src/apf/predeployment_readiness.py
config/arkaon-predeployment-readiness.json
state/predeployment-readiness/
tests/test_predeployment_readiness.py
```

## 콘솔

`GET /v1/console/predeployment` — 최근 readiness report 요약.
