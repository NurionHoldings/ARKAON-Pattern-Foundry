# Netlify to FastAPI same-origin connection

`netlify/functions/foundry-proxy.mjs` handles `/health`, `/console`,
`/console/*`, and `/v1/*`. It forwards those API paths to the HTTPS origin in
`APF_API_ORIGIN`, forwards the session cookie and CSRF header, preserves
upstream cookies and security headers, and disables caching. Browser requests
remain on the Netlify origin, so cross-origin cookies and credentialed CORS are
not needed.

## Netlify configuration

Add `APF_API_ORIGIN` in the Netlify site's environment settings with the
**Functions** scope. Do not put it in `netlify.toml`: TOML variables are not
available to function runtime. Set it only after a separately hosted FastAPI
service has a public HTTPS origin, for example `https://foundry-api.example.com`
(no path, query, username, or password).

The function returns HTTP 503 for missing, non-HTTPS, loopback, and IP-address
origins. It blocks `/console/dev/session` even if the upstream is misconfigured.
FastAPI must independently run in production mode and enforce session and CSRF
checks. Do not add wildcard CORS or expose the session secret in client-side
environment variables.

Store these values in the **API host's** secret/configuration manager:

- `APF_ENV=production`.
- `APF_CONSOLE_SESSION_SECRET`: a randomly generated secret.
- `DATABASE_URL`: the production PostgreSQL connection string.
- Leave `APF_ENABLE_DEV_SESSION` unset or set it to `false`.

## Verification before enabling deployment

1. Run `node --test tests/test_netlify_foundry_proxy.mjs`.
2. Use `netlify dev` with a non-production API origin to verify function routing.
3. Deploy only a non-production branch preview after the API host and secrets
   have been prepared.
4. Verify `/health` returns HTTP 200 and `/console` plus
   `/v1/console/mailbox` return HTTP 401 before login.
5. Verify the authenticated browser session sets `HttpOnly; Secure;
   SameSite=Strict` for `apf_console_session`, keeps the CSRF cookie readable,
   and sends `X-CSRF-Token` for state-changing requests.
6. Confirm FastAPI returns 404 for `/console/dev/session` in production, then
   test the registered mailbox item through the authenticated console without
   changing its state.

This change configures the proxy only. It does not provision or deploy a
FastAPI host, set secrets, create an IAM login flow, or approve production
deployment. Keep `PRODUCT_IMPLEMENT_HOLD` in effect until those items are
reviewed and explicitly authorized.
