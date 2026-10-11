# Clearance-sale scope override — hosted seller shops ONLY

User decision: Clearance-sale hosts seller-specific storefronts, product details, cart, order and checkout itself. The platform marketplace home shows a subset of seller goods and 'more' opens an internal shop route `/shops/{seller_slug}`.

**This supersedes earlier external storefront integration proposals.** Do not build seller-site plugins, external checkout enforcement, cross-domain referral tracking, or external seller-site upload. Earlier documents are historical options, not current requirements. Seller onboarding no longer requires consent to modify external stores; require acceptance of hosted-shop/PG/commission contracts instead.

Preserve PG-provider marketplace: PG firms register and publish reviewed offerings, sellers choose an eligible PG, and ARKAON analyzes PG APIs and proposes common server-side connectors with sandbox evidence. Distinguish seller and platform-direct merchant accounts. Enforce seller_id tenancy, separate multi-seller payments, verified PG payment, immutable commission snapshot and ledger reconciliation.

Required incremental implementation proposals: shared multi-tenant storefront engine, seller signup and dashboard, product/variant/inventory CRUD, cart/checkout/order, PG onboarding and seller choice, contract administration, security and finance tests. Route code PR and evidence to ETERNIAN final audit; operator approves release. Production remains HOLD until verified.

Source: https://github.com/NurionHoldings/Clearance-sale/blob/feat/seller-categories-pg-architecture/docs/decision-hosted-seller-stores.md
Status: stored decision and ARKAON handoff; agent runtime execution not verified.
