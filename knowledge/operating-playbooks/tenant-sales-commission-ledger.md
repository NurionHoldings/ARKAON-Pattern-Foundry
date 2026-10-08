# Tenant sales and commission ledger

Status: operational design knowledge proposed from the `addon-polo` implementation. This playbook is guidance, not a locked policy or automatic authorization to change production systems.

## Operating pattern

1. Register each tenant, contract commission rate, tax treatment, sales channel and authorized user.
2. Normalize every source into a canonical, append-only event ledger. Preserve the source event ID, order ID, tenant, channel, timestamp, actual paid amount, product tax, discount, payment method and settlement reference.
3. Use a unique source event key and file digest for idempotency. Validate an entire import batch before writing it; reject invalid batches without partial financial records.
4. Record cancellation and refund as signed reversal events linked to the original evidence. Never erase a posted transaction.
5. Reconcile by provider settlement batch and bank reference. A provider can combine many orders into one payout; do not assume one order equals one bank deposit.
6. Queue variances for an authorized person to investigate. Record the evidence and resolution in the audit trail; a detection rule must not silently correct a balance or transfer money.
7. Close by tenant and contract period. Snapshot the rate, commission basis, amount, separate commission VAT, included source events and collection status so a later contract edit cannot rewrite a prior statement.

## Source and access rules

- Prefer shared venue POS events, then seller-authorized official APIs/webhooks, then a seller-supplied CSV or supervised manual entry.
- Never request or store a seller's marketplace password, scrape an authenticated sales page, or assume API access is approved. Keep raw credentials in a dedicated secret manager if a reviewed adapter later needs them.
- Enforce tenant scope on every report and export. Finance roles may see payment reconciliation; tenant roles see only their own sales and statements. Minimize customer personal data because it is unnecessary for commission calculation.
- Keep audit evidence append-only and make access to tenant bank details narrower than access to aggregate settlement status.

## Commission and tax

- Treat the signed tenant contract as the authority for commission base, rate, exclusions, refund timing, rounding and close dates. Do not assume every venue charges on gross receipts or the same tax basis.
- Store actual paid amount after discounts and store product tax separately. Calculate the commission base using the contract and the tenant's verified taxable/exempt/mixed treatment.
- Calculate commission VAT as a separate line when applicable; never fold it into the commission rate. Validate the tax invoice and reporting treatment with the responsible accountant.
- Keep late refunds and closed-period corrections as auditable adjustments under an explicit carry-forward policy. Do not silently rewrite an issued statement.

## Settlement and money movement boundary

- Compare expected provider settlement, provider fee, actual bank credit and bank reference. Reconciliation is evidence about amounts; it is not evidence that funds should be held by the building owner.
- Do not pool, custody or redistribute tenant sales proceeds through this software. Preserve the direct seller-to-licensed payment provider payout flow. Any split settlement must be implemented by a licensed provider under reviewed contracts and regulatory requirements.
- A payout variance must remain visible until reviewed; alerts and proposed explanations are safe automation targets, money movement is not.

## Implementation evidence and limits

The `NurionHoldings/addon-polo` prototype demonstrates role-scoped access, PBKDF2 password storage, CSRF-checked mutations, append-only sale/refund events, CSV batch validation and idempotency, monthly statement snapshots, settlement CSV comparison, audit records, and SQLite online backup. It currently accepts manual and CSV source data. POS, marketplace, live-commerce and bank APIs are not connected; each requires source-owner authorization, a current official schema, credential handling and reconciliation tests.

This seed remains Pass 0 and propose-only. ETERNIAN review is required before any Intent_DNA lock, change to financial policy, connector activation, or production rollout.


## Connector onboarding and analysis assistant

- Keep one provider-neutral canonical event contract and implement each POS, commerce, PG and bank source as a replaceable adapter.
- Obtain official schema, account-owner permission, stable source IDs, sample sale/refund/settlement records, cursor/replay behavior, rate limits and sandbox evidence before enabling a live adapter.
- Keep provider credentials in deployment secret storage. Record only the secret reference in profiles; do not put credentials in the DB, logs or repository.
- Normalize partner records, validate integer amounts/date/status mapping, then reuse the existing import path so idempotency, tenant scope and audit rules still apply.
- Match separate PG and bank streams by settlement reference when available. Leave ambiguous matches in an operator review queue; do not silently infer or overwrite a payout.
- The in-app ARKAON analysis layer reports evidence-backed amount differences, unlinked references, impossible tax amounts and channels without rows in a selected period. A blank period is a collection check prompt, not proof of missing sales.
- The managed-app builder kit transfers these connector and analysis patterns to future inventory, booking, membership and reconciliation projects. Its validator/plan writer can prepare a full design packet; implementation stays within the repository's operator-authorized codegen and deployment gates.

The current add-on branch includes a provider catalog, JSON-to-canonical-CSV normalizer, partner intake form, read-only connector readiness view and role-scoped analysis page. Actual POS/marketplace/PG/bank API activation remains pending until partner agreements and sandbox data are available.
