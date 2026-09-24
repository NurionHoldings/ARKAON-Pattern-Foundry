# Railway staging setup

This branch adds a Railway service command and owner-only GitHub OAuth login. Keep the PR in draft and follow the repository readiness gate before merging or production rollout.

## Railway service

1. Connect the GitHub repository to the existing Railway project and select the eventual merged branch. Add a PostgreSQL service.
2. Mount a persistent volume on the web service at `/data`. Use one replica while local artifacts are stored on this volume.
3. Generate an HTTPS Railway domain for the web service. Create a GitHub OAuth App with its Authorization callback URL set to `https://<your-domain>/console/auth/callback`. Enter the exact domain in `APF_PUBLIC_BASE_URL`.
4. Configure variables in Railway, using a reference to PostgreSQL's `DATABASE_URL`. Never commit or send secrets in chat:

| Variable | Value |
| --- | --- |
| `APF_ENV` | `production` |
| `DATABASE_URL` | Railway PostgreSQL service variable reference |
| `APF_RUNTIME_ROOT` | `/data/runtime` |
| `APF_FOUNDRY_ROOT` | `/data/foundry` |
| `APF_CONSOLE_SESSION_SECRET` | Unique random secret, at least 32 characters |
| `APF_GITHUB_OAUTH_CLIENT_ID` | GitHub OAuth App Client ID |
| `APF_GITHUB_OAUTH_CLIENT_SECRET` | GitHub OAuth App Client Secret |
| `APF_GITHUB_OWNER_ID` | Numeric GitHub user ID of the account permitted to sign in |
| `APF_TENANT_ID` | Stable tenant UUID |
| `APF_PUBLIC_BASE_URL` | Exact public HTTPS origin without a path |

5. Before enabling write operations, provision the tenant and database schema using the repository's migration and bootstrap procedure. Keep the persistent volume backed up. `/health` is a process health check and does not establish database or feature readiness.
6. After the readiness gate and PR review permit a deployment, verify `/health`, visit `/console/auth/github`, complete GitHub authorization, and inspect the authenticated console. The ordinary `/console` endpoint requires a signed session. The development session route is disabled when `APF_ENV=production`.

The Railway screenshot currently shows a staged service with no active deployment and no public domain. Clicking **Apply 1 change** or **Deploy** before the above setup would start an incomplete service.
