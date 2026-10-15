# Clearance-sale external storefront referral payment — ARKAON analysis packet

Target specification: https://github.com/NurionHoldings/Clearance-sale/blob/feat/seller-categories-pg-architecture/docs/external-storefront-checkout.md

Intent: Sellers display selected products on Clearance-sale; buyers may follow a link to the seller's existing store to browse more products. For eligible attributable purchases, sellers may opt into a compatible storefront plugin or hosted checkout that routes payment through their selected approved PG connector. This is a contractual, consent-based integration; not an unconditional ability to force payments on third-party websites.

## DNA delta
- JOURNEY: Clearance-sale click -> signed referral -> seller storefront -> integrated checkout -> verified PG payment -> referral commission accounting.
- OBJECT: StorefrontConnection, ReferralSession, AttributionPolicy, CheckoutHandoff, PaymentAttempt.
- OWNER: seller controls storefront and PG choice; platform owns attribution evidence and technical connector; PG confirms payment.
- INVARIANT: no covert installation, no forced redirects on unintegrated sites, no client-authoritative payment amounts, no double commission, no cross-seller data access.
- CONSTRAINT: storefront APIs, PG merchant agreements, user transparency, privacy, contract and rollback.
- RISK: token replay, false attribution, open redirect, bypass checkout, duplicate charges, disputed referral fees.

## ARKAON tasks
1. Inventory supported storefront platforms and official extension points, distinguish plugin / hosted checkout / track-only capabilities.
2. Propose per-platform signed plugins or adapters with explicit seller installation consent; do not modify external sites without authorization.
3. Implement and test signed short-lived referral tokens, server-side attribution, secure cart handoff and verified payment callback in isolated sandbox.
4. Evaluate PG compatibility, merchant-of-record, refund and commission obligations before live release.
5. Report technical limitations and estimated coverage honestly; issue PR and evidence for ETERNIAN review, then operator approval.
6. No automatic production upload, credential retrieval or deployment.


## Operator clarification — required seller undertaking and broad storefront analysis
- The seller's marketplace participation requires signed acceptance of a narrowly defined, enforceable referral-checkout integration obligation. Refusal blocks onboarding; acceptance alone never bypasses host platform policies or third-party rights.
- ARKAON must maintain a capability registry for storefront technologies and propose native adapter, hosted checkout, custom integration, hosted storefront or unsupported HOLD. Universal **analysis scope** does not imply universal implementation ability.
- Capture storefront ownership, API extensibility, legal/contract permissions, seller-authorized installation and test evidence. No covert checkout hijacking, credential collection or forced scripts.
- If integration is unsupported, seller remains unpublished until an approved compatible checkout/storefront alternative is accepted.
- Distinguish commercial contract acceptance from separately regulated privacy consents. Audit signing evidence, attribution window and order eligibility.
- Generate compatibility findings, minimal adapter patches, security tests and rollback plans for ETERNIAN review; do not self-deploy.
