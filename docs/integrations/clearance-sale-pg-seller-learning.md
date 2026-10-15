# CLEARANCE_SALE learning packet — seller categories and competitive PG

Status: PROPOSED / review-only
Target: https://github.com/NurionHoldings/Clearance-sale/tree/feat/seller-categories-pg-architecture
Evidence:
- `config/marketplace-policy.json`
- `docs/seller-contract-workflow.md`
- `docs/pg-connector-contract.md`

## User-directed category order
1. 의류 (clothing)
2. 모자 (hats)
3. 신발 (shoes)
4. 운동복 (sportswear)
5. 특정 스포츠 동호회 용품 (club-gear)
6. 라이더용품 (rider-gear)

## Intent_DNA impact
- WHO: third-party sellers self-register and log in; operators administer seller/commission/payment agreements.
- JOURNEY: onboarding, verification, contract, PG eligibility, approval, authenticated listing and moderation.
- OWNER: legal seller of record; seller-specific commission contract and effective-dated PG allocation.
- INVARIANT: no seller self-approval; no client-authoritative prices or payment status; immutable contract snapshots and ledger idempotency.
- CONSTRAINT: provider-neutral PG architecture, contractual eligibility, payment-provider security and privacy.
- EVOLUTION: new provider via isolated adapter and capability manifest without changing core order/ledger semantics.

## ARKAON tasks
1. Analyze only changed target files and relevant Intent_DNA axes. Validate canonical schema; preserve proposed state.
2. Propose authenticated seller registration and RBAC backed by database with ownership and CSRF/session protections.
3. Propose seller contract and commission versioning plus signed-evidence chain.
4. Compare candidate PG capabilities, costs, payouts, escrow, refund and marketplace eligibility; never assume all providers offer split settlement.
5. Generate test plans for webhook replay, concurrent checkout, inventory reservation, refund/chargeback, payout idempotency and provider outages.
6. Report gaps with evidence, risk, confidence, candidate patch and rollback; queue for ETERNIAN final audit and operator approval.
7. Do not autonomously merge, deploy, use credentials or ingest live payment data.

This is a durable instruction/evidence packet, not proof that a running ARKAON agent consumed it.


## Binding clarification — seller-owned PG choice
- Seller selects one of the platform's approved PG providers; ARKAON must **not** design operator-assigned PG routing as the default.
- Platform provides technical connectors between each seller's approved merchant account and the chosen PG, subject to PG agreement and API capabilities.
- Track connection lifecycle, per-seller ownership checks, provider/merchant credentials references, and active status. Keep actual secrets outside Foundry.
- For each order, snapshot selected PG and merchant account; later PG switching only affects new attempts. Existing refunds and reconciliation stay with original PG.
- Direct-sale platform inventory uses the platform's separate merchant PG connection. Multi-seller orders must not be collapsed into an unsupported single-PG transaction.
- Compare providers fairly; platform commissions and PG merchant fees are separate contracts. Audit unauthorized operator overrides and seller account hijack risks.
- Add tests for seller choice persistence, merchant isolation, invalid connections, provider change during checkout, refund to original PG, and suspended merchant handling.
