# Netlify to FastAPI same-origin connection

`netlify/functions/foundry-proxy.mjs` exposes `/health`, `/console`,
`/console/*`, and `/v1/console/*`. It forwards those paths to the HTTPS
origin in `APF_API_ORIGIN`, forwards session and CSRF headers, preserves
upstream cookies and security headers, and disables caching. Browser requests
stay on the Netlify origin, so cross-origin cookies and credentialed CORS are
not needed.

The proxy intentionally does not expose other `/v1/*` endpoints. The target
API currently relies on a tenant header and does not use the console session
dependency. Keep it outside the public proxy until it has its own authentication
and authorization controls.

## Netlify configuration

Add `APF_API_ORIGIN` in the Netlify site's environment settings with the
**Functions** scope. Do not put it in `netlify.toml`: TOML variables are not
available to function runtime. Configure it after a separately hosted FastAPI
service has a public HTTPS origin, for example
`https://foundry-api.example.com` (no path, query, username, or password).

Netlify documents that function runtime variables need the Functions scope, and
that variables in `netlify.toml` are not available to functions:
https://docs.netlify.com/build/functions/environment-variables/

The function returns HTTP 503 for missing, non-HTTPS, loopback, and IP-address
origins. It blocks `/console/dev/session` even if the upstream is misconfigured.
FastAPI must independently run in production mode and enforce session and CSRF
checks. Do not add wildcard CORS or expose the session secret in client-side
environment variables.

## API host prerequisites

The current app is not ready to be deployed as a stateless container without
additional work. The console reads and writes repository-relative `state/`
and `inbox/` files, while its persistent review adapter needs explicit
PostgreSQL wiring. Provision durable storage and initialize it from a reviewed
data snapshot; do not copy the live operator workspace into a public deployment
without a data review.

The API host must set these values through its secret/configuration manager:

- `APF_ENV=production`.
- `APF_CONSOLE_SESSION_SECRET`: a randomly generated secret.
- `DATABASE_URL`: a production PostgreSQL connection string.
- `APF_ENABLE_DEV_SESSION=false` or leave it unset.
- IAM OIDC issuer/client settings and an explicit principal-to-tenant/role
  allowlist, once the organization identity provider is selected.

The FastAPI code currently has a development-session endpoint and signed
sessions, but the operations doc records that organization IAM session
issuance is still required. Do not enable the console until that login path
exists and is tested. The session endpoint must create the existing secure,
HttpOnly session cookie only after validating the IAM authorization response
and mapping an allowed identity to a server-managed tenant and role. Do not
accept tenant, principal, or role assignments from browser-supplied login data.

## Preproduction verification

1. Run `node --test tests/test_netlify_foundry_proxy.mjs` and the complete CI suite.
2. Test proxy routing with a non-production API origin.
3. In the API deployment, confirm `/console/dev/session` returns 404 and that
   no browser-controlled fields can select tenant or role.
4. Before login, verify proxied `/console` and an authenticated console API
   return 401. Complete IAM login and verify the cookie is
   `HttpOnly; Secure; SameSite=Strict`; verify state-changing calls require
   the CSRF token.
5. Verify the registered mailbox item through a read-only authenticated query,
   confirming its state is unchanged.
6. Enable a Netlify preview only after API, IAM, database, and reviewed data
   initialization are ready. Production deployment and promotion remain on
   `PRODUCT_IMPLEMENT_HOLD` pending explicit approval.

This change only narrows the proxy and documents prerequisites. It does not
provision a host, configure Netlify secrets, implement organization IAM, mutate
mailbox state, or deploy the site.
