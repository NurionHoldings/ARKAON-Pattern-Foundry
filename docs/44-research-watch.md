# ARKAON Research Watch (Pattern Foundry #085)

조회일: 2026-09-17  
상태: NARANG `#085-research-watch` clean-room analog.

## 역할

공개 manifest·정책 파일 digest를 주기적으로 비교해 **변경 감지** → `inbox/research` RESEARCH_PACKET 생성.

성찰학습(#049)·Reflection Bridge(#050)의 **외부 관찰 입력** 자동화에 사용합니다.

## 경계

- maximum_outcome: `RESEARCH_PACKET`
- automatic_learning / production_change / competitor_copy 금지
- LOCAL_MANIFEST watch만 v0.1 구현 (HTTPS fetch watch는 collector 정책과 병행 예정)

## 구현

```text
src/apf/research_watch.py
src/apf/research_watch_bridge.py
config/arkaon-research-watch.json
config/research-watch-sources.json
state/research-watch/digests.json
tests/test_research_watch.py
```

## 오케스트레이터

매 run 시작 시 `ResearchWatchRegistry.detect_changes()` → 변경·초기 baseline 시 research inbox packet.
