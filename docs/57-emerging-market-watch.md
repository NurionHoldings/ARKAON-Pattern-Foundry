# 57. 신규 시장 등장·변화 감지

- 명세 ID: APF-MARKET-WATCH-001
- 상태: IMPLEMENTED / RESEARCH_PACKET_ONLY

## 목표

변화 감지에 유리한 **신규 시장·세그먼트·수요·규제** 신호를 정기적으로 수집한다.
기사·홍보문 **원문 저장 없이** structural tag와 digest만 축적한다.

## 정기 실행

| 채널 | KST 시각 |
|------|----------|
| Emerging Market Watch | **3·9·15·21시** |
| SNS Watch (#056) | 0·6·12·18시 |
| Hourly collector (#055) | 22시 `EMERGING_MARKET_SIGNALS` 주제 |

## change_kind

| 값 | 의미 |
|----|------|
| `NEW_MARKET_SEGMENT` | segment_tags 변화 (신규 시장/카테고리) |
| `DEMAND_SHIFT` | demand_tags 변화 |
| `REGULATORY_SIGNAL` | regulatory_tags 변화 |
| `NOVELTY_RISE` | novelty/velocity bin 상승 |
| `BASELINE` | 최초 관측 |

## 입력

- `knowledge/market-digests/*.json` — sanitize된 시장 digest
- `PUBLIC_HTTPS_INDEX` — W3C TR, OpenAPI 등 **공식 standards index**

## 출력

- `inbox/research/{run_id}-market-{watch_id}.json`
- `state/emerging-market-watch/digests.json`

## 운영

1. 새 시장 후보 발견 시 `segment_tags`만 digest에 append
2. `config/emerging-market-sources.json`에 scope 등록
3. research packet → reflective lesson → capability gap 연동 (#052)

## 금지

- 기사·리포트 원문 저장
- paywall·비공개 API
- automatic_learning / production_change
