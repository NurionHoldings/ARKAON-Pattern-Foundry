# 66. Co-Creation 3단계 — URL 참조·GitHub·빌드

- 명세 ID: APF-CO-CREATION-PHASE3-001
- 상태: IMPLEMENTED / PROPOSE_ONLY

## URL 참조 (similar feel)

사용자가 제시한 **공개 HTTPS URL**에서 structural style profile을 추출한다.

| 입력 | 용도 |
|------|------|
| `reference_site_url` | 전체 템플릿 톤·섹션 rhythm |
| `feature_reference_urls` | 기능별 구현 feel (`hero`, `process`, `checkout`, `mypage`, `auth`, …) |

- verbatim HTML/CSS/문구 저장 **금지**
- `state/co-creation/reference-styles/` 에 bundle digest 저장
- template section `purpose`에 style tag + URL 근거만 반영

## GitHub secure onboarding

`POST /v1/console/co-creation/github-onboarding/start`

1. HTTPS console base URL 필수
2. GitHub signup / login 공식 URL 안내
3. OAuth authorize URL (client_id 설정 시)
4. state-bound callback path

## Phase-3 build (operator 승인 후)

`POST /v1/console/co-creation/build`

- `operator_approval_digest` 필수
- `state/co-creation/previews/` — tenant preview sandbox manifest
- `state/co-creation/scaffolds/` — template codegen scaffold (PENDING_REVIEW)
- automatic deploy **금지**

## Billing

`config/arkaon-billing-entitlement.json` — `docs/67-billing-api-entitlement.md`

- `DIGEST` — dev digest only
- `BILLING_API` — billing SoT HTTPS verify
- `DIGEST_THEN_API` — API 우선, digest fallback

## 4단계 (다음)

`docs/68-co-creation-phase4-roadmap.md` — scaffold manifest 이후 **codegen → tenant preview → staged deploy**.

## API 요약

```json
{
  "platform_id": "NARANG_RIDER",
  "message": "전자계약 funnel 템플릿",
  "reference_site_url": "https://zaksimspace.co.kr/",
  "feature_reference_urls": {
    "process": "https://zaksimspace.co.kr/",
    "mypage": "https://example.com/dashboard"
  },
  "payment_entitlement_digest": "<64-hex>"
}
```
