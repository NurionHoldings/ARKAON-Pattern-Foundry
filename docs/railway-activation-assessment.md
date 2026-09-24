# Railway activation evidence review — 2026-09-24

## PR chain and CI

The feature branch sequence is PR #58 → #59 → #60 → #61 → #62 → #63 → #64 → #65 → #66 → #67 → #68 → #69 → #70 → #71. They remain draft and unmerged. GitHub showed PR #61 as dirty because its parent branch had changed the console pattern candidate hash after the child was cut. Its head was merged with the updated parent while retaining the child's current tree, which contains the correct console evidence hash for its console source. Its prior lint failure (legacy percent formatting in `logo_reference.py`) had already been fixed in the head. CI run 184 passed test, PostgreSQL integration and Windows audit jobs on the reconciled PR #61 SHA `2f7b1a21aacb57f80fa583e564f7e7a4aa3ae34d`.

The exact head of each PR #58–#60 and #62–#70 had a successful pull-request CI run when checked. PR #71 CI also passed for the owner-only Railway guide implementation SHA `fc53234ee5d03a9c4f97bf5e301d2a6f974f6335`; its most recent documentation revision requires a fresh run. These CI runs are not evidence of deployment on Railway, actual owner OAuth, persistent volume or backup recovery. GitHub mergeability is recalculated after parent changes and must be rechecked before every individual merge. No PR was merged in this review.

## Deployment and activation evidence matrix

| Requirement | Evidence at review | State |
| --- | --- | --- |
| Deployment lock | `knowledge/readiness/v0.1-readiness.json`: `PRODUCT_IMPLEMENT_HOLD`, `deployment=false` | HOLD |
| Railway DB | Screenshot: Postgres Online and `postgres-volume` | Observed only |
| App service | Railway staged one pending service creation; source commit and build unverified | HOLD |
| App volume | No separate app volume at `/data` observed | HOLD |
| Config | No live proof for `DATABASE_URL` reference, runtime/foundry roots, production environment and OAuth settings | HOLD |
| Migration | `apf.migrations.upgrade` is implemented and PostgreSQL CI passes; no Railway migration ledger evidence | HOLD |
| Tenant | `PostgresRepository.provision_tenant` exists; Railway tenant row not verified | HOLD |
| Owner login | GitHub OAuth implementation exists in PR #71; no live approved account login or non-owner denial proof | HOLD |
| Backups | No Railway Postgres or app-volume restore exercise | HOLD |
| URL observation | Static public HTTPS observer exists in PR #70; no Railway egress smoke proof | HOLD |
| Product gaps | Readiness matrix still lists review adapter/detail rendering, owned-platform connection, candidate promotion and reuse proof as missing | HOLD |

## Safe next actions

1. Review PR #58–#71 in dependency order, confirm each latest CI and preserve review decisions. Do not merge while the repository's own PR gate remains on hold.
2. Specify the authorized release scope separately from the broader product readiness matrix. If limited staging is approved, document what is exposed, whom it serves, its data lifecycle and what remains disabled. Do not silently flip the production deployment lock for staging.
3. Before a live release, verify selected Railway GitHub branch and SHA, app volume, database reference, configured secrets in Railway, database migration and tenant, signed-in owner and rejected non-owner, backup recovery, and rollback.
4. Record explicit activation approval and only then update the applicable readiness state with evidence. The click-through guide cannot perform this transition.

The owner console guide at `/console/railway-setup` is a human-readable execution aid. A button labeled “확인했어요” means the operator claims to have checked the linked screen. It is not a Railway API verification or service provisioning call.
