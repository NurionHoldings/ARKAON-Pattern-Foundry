# ARKAON 자산 조사·우선순위 (R-011)

조회일: 2026-09-17  
상태: 검색/조사를 통해 **가장 증거가 강한 자산**을 먼저 eternian·운영자에게 제시.

## 원칙

아르카온은 **수집·기억·구조화·인덱싱**(docs/01 R-011)을 담당하며, 무작위 승격이 아니라 **조사 신호를 점수화·순위화**해 최고 품질 후보를 먼저 검토하게 한다.

## 신호원

| 신호 | 의미 |
|------|------|
| RESEARCH_DELTA | research watch digest 변경 |
| PATTERN_CANDIDATE | 30개 후보 중 unique evidence anchor |
| OWNED_PILOT_GAP | 노가다뉴스·부업장터 live repo 미조사 |
| PROMOTION_PENDING | 외부 eternian 서명 대기 |
| SURFACE_SIGNAL | 공개 surface structural digest |

## 경계

- automatic_promotion / automatic_learning / production_change **금지**
- 순위는 **research inbox** 제안만; 승격·mutation은 eternian·operator 외부

## 구현

```text
src/apf/asset_investigation.py
src/apf/asset_investigation_bridge.py
config/arkaon-asset-investigation.json
state/asset-investigation/
GET /v1/console/asset-investigation
```

오케스트레이터 매 run: research watch 직후 조사·순위 → state + (score≥threshold) research packet.
