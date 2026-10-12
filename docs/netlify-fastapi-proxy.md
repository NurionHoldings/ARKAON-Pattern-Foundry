# Netlify to FastAPI same-origin connection

`netlify.toml` rewrites `/health`, `/console`, `/console/*`, and `/v1/*` to the
`foundry-proxy` Netlify Function. The function forwards only those API paths to
the HTTPS origin configured in `APF_API_ORIGIN`. It forwards the session cookie
and CSRF header, preserves the upstream response cookies and security headers,
and disables caching. The browser therefore uses the Netlify origin for API
calls; cross-origin cookies and credentialed CORS are not needed.

## Netlify environment

After a separately hosted FastAPI service is ready, set these values in the
Netlify site's environment configuration before deploying the branch:

- `APF_API_ORIGIN`: the public HTTPS origin only, for example
  `https://foundry-api.example.com` (no path, query, username, or password).
- `APF_ENV=production`.
- `APF_CONSOLE_SESSION_SECRET`: a randomly generated secret stored only in the
  API host's secret manager.
- `DATABASE_URL`: the production PostgreSQL connection string stored only in
  the API host's secret manager.
- Leave `APF_ENABLE_DEV_SESSION` unset or set it to `false`.

The proxy rejects missing, non-HTTPS, loopback, and IP-address API origins with
HTTP 503. It also blocks `/console/dev/session` even if the upstream is
misconfigured. FastAPI must independently run in production mode and enforce
its own session and CSRF checks. Do not add wildcard CORS or expose the session
secret in Netlify's client-side environment variables.

## Verification before enabling deployment

1. Run `node --test tests/test_netlify_foundry_proxy.js`.
2. Deploy only a non-production branch preview after setting `APF_API_ORIGIN`.
3. Verify the preview's `/health` returns HTTP 200 and `/console` plus
   `/v1/console/mailbox` return HTTP 401 before login.
4. Verify the authenticated browser session sets `HttpOnly; Secure;
   SameSite=Strict` for `apf_console_session`, keeps the CSRF cookie readable,
   and sends `X-CSRF-Token` for state-changing requests.
5. Confirm the FastAPI host returns 404 for `/console/dev/session` in
   production, then test the exact registered mailbox item through the
   authenticated console without changing its state.

This repository change configures the proxy only. It does not provision or
deploy a FastAPI host, set secrets, create an IAM login flow, or approve a
production deployment. Keep `PRODUCT_IMPLEMENT_HOLD` in effect until those
items are reviewed and explicitly authorized.
