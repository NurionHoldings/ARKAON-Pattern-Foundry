# 59. SNS 관심 집중 요인·쇼츠 제작 자산

- 명세 ID: APF-SNS-ATTENTION-001
- 상태: IMPLEMENTED / PROPOSAL_ONLY

## 목표

SNS **클릭 폭증** 항목에 대해 쇼츠·영상 **본문/원문이 아닌** “관심을 집중시키는 요인”을
구조적으로 분해하고, 추후 제작에 재사용할 **추상 자산**으로 축적한다.

## 콘텐츠 vs 관심 요인

| 구분 | 저장 여부 | 예 |
|------|-----------|-----|
| 콘텐츠 본문 | 금지 | 캡션 원문, 영상 파일, URL |
| 콘텐츠 각도 | 허용 (태그) | `scarcity-countdown`, `beat-sync-hook` |
| 관심 요인 | 허용 (구조) | `scarcity-framing`, `0-1s` hook, `beat-drop` |

## attention_factors 스키마

`trend_items[]`에 선택 필드:

```json
"attention_factors": {
  "primary_driver": "scarcity-framing",
  "secondary_drivers": ["countdown-visual", "motion-contrast-open"],
  "hook_window_bin": "0-1s",
  "curiosity_mechanism": "open-loop",
  "trust_mechanism": "limited-stock-badge",
  "pacing_bin": "fast-cut",
  "caption_role": "headline-overlay",
  "audio_cue_tag": "tick-or-beat",
  "pattern_interrupt": "sudden-zoom",
  "cta_timing_bin": "open",
  "visual_contrast_bin": "high-motion-open",
  "social_proof_frame": "sold-out-digest"
}
```

- bin/태그만 사용 (raw 클릭 수·조회수 X)
- manifest에 없으면 `content_angle_tag` **heuristic** (`factor_source: angle-heuristic`)

## 파이프라인

```text
SNSTrendAnalyzer (#058) surge_items
  → SNSAttentionAnalyzer (#059)
  → knowledge/shorts-production-assets/{platform}-{item_id}.json
  → state/sns-attention/latest.json
  → inbox/research:
      * {run_id}-sns-attention-analysis.json
      * {run_id}-sns-attention-{item_id}.json
  → 우편함 (#053) → 승인 → 제작 참고
```

## production_guidance

각 자산은 operator-facing **제작 가이드** 한 줄 요약을 포함한다.
예: *Lead with 'scarcity-framing' inside hook window 0-1s. Pacing: fast-cut; …*

## evolution domain 연동

`reuse_domains` 예: `VIDEO_TEMPLATE_EFFECTS`, `SIGNATURE_MOTION`, `CAPCUT_STYLE_BRIDGE`

## 경계

- `automatic_implement_allowed` / `production_change_allowed` **false**
- 게시물·영상 원문/파일 저장 금지
- 승인 전 Intent 변경·자동 배포 없음
