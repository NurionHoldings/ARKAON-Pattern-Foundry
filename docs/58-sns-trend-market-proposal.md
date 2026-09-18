# 58. SNS 클릭 급등·트렌드·시장 개척 제안

- 명세 ID: APF-SNS-TREND-001
- 상태: IMPLEMENTED / PROPOSAL_ONLY

## 목표

SNS 분석을 통해 **클릭이 폭증하는 종목·콘텐츠 각도**를 모니터링하고,
트렌드를 분석한 뒤 **시장 개척 제안**을 inbox에 생성한다.

## 입력 (원문 금지)

`knowledge/sns-digests/*.json`의 `trend_items`:

```json
{
  "item_id": "limited-drop-countdown",
  "category_tag": "commerce-hype",
  "content_angle_tag": "scarcity-countdown",
  "click_velocity_bin": "surge",
  "engagement_bin": "high"
}
```

- `click_velocity_bin`: `surge` | `explosive` | `very-high` 등 **bin만** (raw 클릭 수 X)
- URL·@handle·해시태그·게시물 원문 **금지**

## 파이프라인

```text
SNS Watch (#056) manifest/surface digest
  → trend summary (surge count, category tags)
  → SNSTrendAnalyzer (#058)
  → inbox/research:
      * {run_id}-sns-trend-analysis.json
      * {run_id}-sns-market-{item_id}.json  (MARKET_PIONEERING proposal)
  → SNSAttentionAnalyzer (#059) — surge item 관심 요인 분해
  → knowledge/shorts-production-assets/, inbox/research/sns-attention-*
  → 우편함 (#053) → 승인 → 이행 큐
```

## surge 감지

`config/arkaon-sns-trend.json`의 `surge_velocity_bins`에 해당하는 item은
`CLICK_SURGE` / trend report / market proposal 대상.

## 시장 개척 제안 필드

- `suggested_market_scope` — 예: `DOMESTIC_CREATOR_COMMERCE`
- `user_message` — operator-facing advisory (자동 배포 없음)
- `proposal_kind`: `MARKET_PIONEERING`

## 경계

- automatic_implement / production_change **false**
- 경쟁사 문구·게시물 복제 금지
- 승인 전 Intent 변경·배포 없음
