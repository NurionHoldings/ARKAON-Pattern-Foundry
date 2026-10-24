# 70. 운영 연결 롤아웃 순서 (HOLD)

상태: **PRODUCT_IMPLEMENT_HOLD** — 아래 순서는 검토·승인 후 콘솔에서 실행한다.  
코드 근거: `docs/netlify-fastapi-proxy.md`, `render.yaml`, `config/examples/arkaon-google-iam-principal-map.example.json`

## 1. PostgreSQL 콘솔 검토 저장소 (코드)

- [x] `create_app()` → `review_store_config.console_review_store_from_config`
- [ ] CI postgres job 또는 `TEST_DATABASE_URL`로 live proof Green (`DURABLE_REVIEW_ADAPTER`)

## 2. Render API 서비스

- [ ] `render.yaml` 검토 후 Web Service + PostgreSQL + `/var/data` 디스크 생성 (`autoDeploy: false` 유지 가능)
- [ ] Secrets: `APF_CONSOLE_SESSION_SECRET`, `DATABASE_URL`, `APF_ETERNIAN_REVIEW_PUBLIC_KEY_B64`, Google OIDC, `APF_IAM_PRINCIPAL_MAP_JSON`
- [ ] 직접 origin에서 `/health` 200 확인

## 3. Google Workspace OAuth

- [ ] OAuth 웹 클라이언트, redirect `https://arkaonfoundry.netlify.app/console/auth/callback`
- [ ] `APF_GOOGLE_WORKSPACE_DOMAINS`, IAM 매핑 확정 (예시 JSON만 저장소에 있음)

## 4. Render 인증·가드 검증

- [ ] `/v1/targets`, `/openapi.json`, `/console/dev/session` → production에서 404
- [ ] Workspace 로그인 → 세션·CSRF 쿠키

## 5. Netlify `APF_API_ORIGIN`

- [ ] Functions 범위에 Render HTTPS origin 설정 (TOML 금지 — Netlify UI)
- [ ] 동일 출처 `/health`, `/console` 프록시 동작

## 6. 사이트·우편함 검증

- [ ] `python scripts/check_site_foundry_connectivity.py --site https://arkaonfoundry.netlify.app`
- [ ] 비로그인 `/console` → 로그인, 콘솔 접근, dev session 차단
- [ ] **우편함(inbox/archive) 상태 변경 없음**

## 로컬·스테이징 점검 명령

```bash
python orchestrator/arkaon-postgres-live-proof.py --dry-run
python scripts/check_local_api_connectivity.py --base-url https://localhost:8443 --insecure-local
python scripts/check_site_foundry_connectivity.py --site https://arkaonfoundry.netlify.app
```
