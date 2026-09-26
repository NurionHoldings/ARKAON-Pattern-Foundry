# 67. Billing API entitlement (실연동)

- 명세 ID: APF-BILLING-ENTITLEMENT-001
- 상태: IMPLEMENTED

## 목표

Co-Creation 등 유료 capability gate를 **billing SoT API**로 검증한다. digest 프로토타입은 dev·fallback으로 유지한다.

## 정책

`config/arkaon-billing-entitlement.json`

| 필드 | 설명 |
|------|------|
| `mode` | `DIGEST` \| `BILLING_API` \| `DIGEST_THEN_API` |
| `billing_api_base_url` | credential-free HTTPS base (예: `https://billing.example.com`) |
| `verify_path` | verify endpoint path (기본 `/v1/entitlements/verify`) |
| `api_token_env` | service bearer token env (기본 `ARKAON_BILLING_API_TOKEN`) |
| `capability` | 검증 capability (기본 `co_creation`) |
| `allow_digest_fallback` | API 실패·미설정 시 digest 허용 (`BILLING_API` 모드) |

## Billing SoT contract

```http
POST {billing_api_base_url}{verify_path}
Authorization: Bearer {service_token}
Content-Type: application/json
```

```json
{
  "tenant_id": "uuid",
  "principal_id": "uuid",
  "platform_id": "NARANG_RIDER",
  "entitlement_token": "64-hex digest or billing-issued token",
  "capability": "co_creation"
}
```

### Response

| HTTP | body | 결과 |
|------|------|------|
| 200 | `{ "entitled": true, "status": "ACTIVE" }` | 허용 |
| 200 | `{ "entitled": false }` | 거부 |
| 402 / 403 / 404 | — | 거부 |
| 401 | — | 거부 (token misconfig) |
| 기타 / timeout | — | 거부 (`DIGEST_THEN_API`는 digest fallback 가능) |

`entitled` 필드가 없으면 `status`가 `ACTIVE`, `TRIAL`, `PAID`일 때 허용한다.

## 운영 설정

```powershell
$env:ARKAON_BILLING_API_TOKEN = "<billing-service-token>"
```

`config/arkaon-billing-entitlement.json`:

```json
{
  "mode": "BILLING_API",
  "billing_api_base_url": "https://billing.your-platform.example",
  "allow_digest_fallback": false
}
```

## Digest fallback (dev)

```text
sha256("{tenant_id}|{principal_id}|{platform_id}|paid")
```

`DIGEST_THEN_API` + `allow_digest_fallback: true` — API token·URL 미설정 또는 API 오류 시 digest로 dev 진행 가능.

## 관련

- `docs/65-conversational-co-creation.md` — chat intake entitlement gate
- `docs/66-co-creation-phase3-reference-urls.md` — phase-3 billing hook
- `src/apf/billing_entitlement.py` — verifier implementation
