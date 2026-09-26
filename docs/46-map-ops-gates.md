# ARKAON 지도 운영 게이트 (#071–#076)

조회일: 2026-09-17  
상태: NARANG map ops 브랜치 clean-room analog.

## 게이트

| Phase | Gate ID | 내용 |
|-------|---------|------|
| #071 | MAP_KNOWLEDGE_071 | provisional provider knowledge, production BLOCKED, HTTPS docs |
| #072 | MAP_SANDBOX_072 | map adapter sandbox — network/secret deny |
| #073 | DEVICE_AUTH_073 | bounded device auth, no continuous tracking |
| #074 | ETA_SHADOW_074 | predicted vs observed ETA advisory-only |
| #075 | MAP_RESILIENCE_075 | offline instruction without auto-select/coords |
| #076 | MAP_RELEASE_076 | competency profile BLOCKED, zero_tolerance |

FAIL/ADVISORY → `inbox/eternian-review/*-map-ops.json`. PASS 시 패킷 없음.

## 구현

```text
src/apf/map_ops_gate.py
src/apf/map_ops_bridge.py
config/arkaon-map-ops-gate.json
config/map-competency-profile.json
config/map-provider-knowledge.provisional.json
state/map-ops-gate/
tests/test_map_ops_gate.py
```

## 오케스트레이터

매 run 시작 시 Foundry-level map ops gate 1회 실행.

기본 ETA shadow(600→720, Δ120s)는 tolerance 900s 이내라 **PASS**이며 inbox 패킷이 없다.

### ADVISORY 데모

```bash
py -3.11 tools/demo_map_ops_advisory.py
py -3.11 orchestrator/arkaon-orchestrator.py --demo-map-ops-advisory
```

600s 예측 vs 3600s 관측(Δ3000s)으로 `ETA_SHADOW_074` **ADVISORY** → `inbox/eternian-review/*-map-ops.json`.
