# ARKAON work order: Clearance-sale competitive gap audit and implementation sequence

Evidence and source of truth: https://github.com/NurionHoldings/Clearance-sale/blob/feat/seller-categories-pg-architecture/docs/competitive-gap-audit-2026-10.md

Official comparison: Shopify multi-location inventory/notifications, Cafe24 multichannel sync, Amazon Seller Central mobile operations, Mirakl seller onboarding/catalog mapping/commission and payout. Use linked official documentation in the source audit; verify API capabilities and current terms before coding.

## Instructions to ARKAON
1. Read actual Clearance-sale source and produce a **file/route/test-based** gap matrix. Do not confuse static demo, docs and config with operational services.
2. Inspect ARKAON central orchestrator, Intent_DNA schema, existing workspace onboarding and audit queues; integrate via supported existing mechanisms, not a parallel invented control plane.
3. Lock product boundaries: hosted-only seller shops and hosted checkout; optional authorized source-shop content reconstruction and inventory sync; PG companies as marketplace participants and seller-controlled PG choice; mobile sales/stock alerts.
4. P0 work first: secure authentication/tenant RBAC, transactional inventory reservation, server-verified PG sandbox and financial ledger, seller/PG onboarding, shipping/returns, compliance and trust/safety.
5. Deliver a narrow, testable implementation PR per milestone with migrations, threat cases, positive/negative tests, rollout/rollback and evidence. No self-approval, no auto-merge, no live PG charges.
6. Route high-risk work to ETERNIAN audit. HOLD until operator approval and CI evidence; report blockers and unsupported vendor capabilities without claiming success.

## Milestone acceptance packet
- Diff and impacted Intent_DNA axes; ownership and trust boundaries.
- Tests for cross-tenant access, idempotency, webhook forgery/replay, concurrent stock sales, refund reconciliation and notification duplication.
- Source/license provenance for seller-shop reconstruction and separate seller approval.
- Demonstrated local or CI results, not estimated pass counts.
- Production preflight checklist and explicit operator sign-off.

Status: work-order document stored in draft branch. Does not prove an autonomous ARKAON agent has executed the work.
