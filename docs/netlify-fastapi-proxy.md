# Netlify to FastAPI same-origin connection

`netlify/functions/foundry-proxy.mjs` exposes `/health`, `/console`,
`/console/*`, and `/v1/console/*`. It forwards those paths to the HTTPS
origin in `APF_API_ORIGIN`, forwards session and CSRF headers, preserves
upstream cookies and security headers, and disables caching. Browser requests
stay on the Netlify origin, so cross-origin cookies and credentialed CORS are
not needed.

An unauthenticated `/console` request is redirected by the Netlify function to
the public `/console/login` page. That page starts Google Workspace OIDC. The
callback returns through the same Netlify origin and sets the existing
`HttpOnly; Secure; SameSite=Strict` console session and CSRF cookies.

## Public route controls

The proxy intentionally does not expose other `/v1/*` endpoints. Production
FastAPI also returns 404 for `/v1/targets`, `/v1/targets/*`, and API schema
routes. The target API relies on a tenant header and has no user authorization,
so it must remain disabled in production until a separate authenticated API
design is approved.

The proxy path filter is not an origin firewall. These production checks are
also enforced by FastAPI because callers can address the public API origin
directly. The development session endpoint is disabled in production by
`ConsoleSecurity` and blocked at the Netlify proxy.

## Render API service

The branch includes a Docker image that binds to Render's `PORT`. A practical
initial host is a Render Web Service with managed PostgreSQL and a persistent
disk mounted at `/var/data`. Set `APF_FOUNDRY_ROOT=/var/data`; console routes
and stores use this root for `state/` and `inbox/` data.

Render documents public web services with custom domains, TLS, secrets,
health-check paths, and persistent disks. A persistent disk preserves data
under its mount path, but is attached to only one service instance. Treat this
as a single-instance console until state is moved to shared durable services
and multi-instance behavior is validated:
https://render.com/docs/web-services
https://render.com/docs/disks

Create a reviewed data snapshot under the mounted root before enabling the
service. Do not copy the live operator workspace or alter mailbox statuses.
`create_app()` wires `ConsoleReviewStore` from `DATABASE_URL` and Eternian review
public key configuration (see `docs/27-postgresql-repository.md`). Run PostgreSQL
live proof and review adapter checks before pointing production traffic at review
APIs.

## Render environment values

Set values in the Render service's environment and secret manager:

- `APF_ENV=production`.
- `APF_ENABLE_DEV_SESSION=false`.
- `APF_CONSOLE_SESSION_SECRET`: generate a random secret.
- `APF_FOUNDRY_ROOT=/var/data`.
- `DATABASE_URL`: private connection string for the production PostgreSQL service.
- `APF_ETERNIAN_REVIEW_PUBLIC_KEY_B64`: urlsafe Ed25519 public key for review attestations.
- `APF_CONSOLE_PUBLIC_ORIGIN=https://arkaonfoundry.netlify.app`.
- `APF_GOOGLE_OIDC_CLIENT_ID`: the Google OAuth web-client ID.
- `APF_GOOGLE_OIDC_CLIENT_SECRET`: the Google OAuth web-client secret.
- `APF_GOOGLE_WORKSPACE_DOMAINS`: comma-separated exact Workspace domain allowlist.
- `APF_IAM_PRINCIPAL_MAP_JSON`: server-managed email-to-principal mapping.

Example mapping shape (replace placeholders; these are not credentials):

```json
{
  "operator@example.org": {
    "tenant_id": "00000000-0000-4000-8000-000000000001",
    "principal_id": "00000000-0000-4000-8000-000000000002",
    "role": "operator",
    "google_sub": "optional-stable-google-subject"
  }
}
```

Only mapped, verified Workspace identities in an allowed `hd` domain receive a
session. Tenant, principal, and role come from the server map; browser input
cannot choose them. Google requires the OAuth redirect URI to match exactly.
Register:

`https://arkaonfoundry.netlify.app/console/auth/callback`

If the Netlify site later uses a custom domain, update both
`APF_CONSOLE_PUBLIC_ORIGIN` and the Google OAuth client's authorized redirect
URI. Google recommends validating the signed ID token, issuer, audience,
expiry, nonce, and Workspace `hd` claim:
https://developers.google.com/identity/openid-connect/openid-connect
https://developers.google.com/identity/protocols/oauth2/web-server

## Netlify function configuration

After the API service has a public HTTPS origin, set `APF_API_ORIGIN` on the
Netlify site with the **Functions** scope. For example:

`https://arkaon-api.onrender.com`

Do not put this variable in `netlify.toml`; Netlify documents that TOML
variables are unavailable to function runtime. Do not set it until the API
origin exists and the direct-origin route gates above are verified:
https://docs.netlify.com/build/functions/environment-variables/

## Site integration

`services/services.js` defaults to same-origin `/health` and `/console` when
`localStorage` override is blank. `probeApi` treats `/console` 302/401 as
reachable when `/health` is not yet 200 (for example before `APF_API_ORIGIN`
is set, `/health` may return 503). Rollout order: `docs/70-operational-connect-rollout.md`.
Render blueprint draft: `render.yaml`.

## Preproduction verification

1. Run the full CI suite and container smoke test.
2. Configure a non-production Render service, reviewed data snapshot, database,
   and Google OAuth client. Keep `APF_ENABLE_DEV_SESSION=false`.
3. Confirm direct API `/health` is 200; `/v1/targets`,
   `/v1/targets/<id>`, `/openapi.json`, and
   `/console/dev/session` are 404 in production mode.
4. Set Netlify `APF_API_ORIGIN` with Functions scope and verify proxied
   `/health`, the 302 sign-in redirect, and `/console/login`.
5. Complete Google Workspace login; verify only an allowlisted identity gets
   the session cookies and state-changing requests require the CSRF token.
6. Read the registered mailbox item through an authenticated, read-only query
   and confirm its status is unchanged.

This branch change does not create Render resources, set environment secrets,
register a Google OAuth client, configure Netlify, modify mailbox state, or
deploy the production site. Keep `PRODUCT_IMPLEMENT_HOLD` until all checks and
the remaining frontend and PostgreSQL wiring are reviewed.
