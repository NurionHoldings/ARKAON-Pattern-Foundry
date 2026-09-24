# Railway staging setup

This branch adds a Railway service command and owner-only GitHub OAuth login. Keep the PR in draft and follow the repository readiness gate before merging or production rollout.

## 초보 사용자 클릭형 진행 화면

로그인한 owner는 관리 화면의 **Railway 구축 안내**를 열어 7개 단계를 하나씩 확인합니다. 각 단계에서 Railway 또는 GitHub의 공식 설명을 새 탭으로 열 수 있습니다. 화면의 '확인했어요'는 사용자의 자가 확인이며 서비스 생성, 변수 설정, 배포, 상태 검증을 대신 수행하지 않습니다. 계정 비밀번호, PostgreSQL URL, OAuth Client Secret은 안내 화면에 입력받지 않습니다.

상태 배지는 서버의 `knowledge/readiness/v0.1-readiness.json`을 읽어 배포 잠금을 표시합니다. 읽기 실패 시 진행 불가로 표시합니다. 최종 단계에도 배포 실행 버튼을 두지 않았습니다. 실제 클릭 한 번으로 서비스를 생성하려면 Railway 계정 연결, 최소 권한 범위, 사용자별 실행 동의, Railway 응답 재조회, 중복 실행 방지, 비용 표시, 되돌리기 절차를 별도 PR에서 구현하고 검증해야 합니다.

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

5. Before enabling write operations, apply `apf.migrations.upgrade(engine)` to the Railway PostgreSQL connection and call `PostgresRepository.provision_tenant(UUID(APF_TENANT_ID), tenant_name)` as an explicit operator action. Do not use the test fixture's `downgrade(engine)` on live data. Neither operation is automatically triggered by the current `railway.toml`. Keep the persistent volume backed up. `/health` is a process health check and does not establish database or feature readiness.
6. After the readiness gate and PR review permit a deployment, verify `/health`, visit `/console/auth/github`, complete GitHub authorization, and inspect the authenticated console. The ordinary `/console` endpoint requires a signed session. The development session route is disabled when `APF_ENV=production`.

The Railway screenshot currently shows a staged service with no active deployment and no public domain. Clicking **Apply 1 change** or **Deploy** before the above setup would start an incomplete service.
