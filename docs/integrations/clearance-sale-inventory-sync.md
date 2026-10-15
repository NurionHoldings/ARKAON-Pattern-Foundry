# Clearance-sale automatic inventory synchronization — ARKAON packet

Source: https://github.com/NurionHoldings/Clearance-sale/blob/feat/seller-categories-pg-architecture/docs/inventory-auto-sync.md

User direction: seller operates original storefront and Clearance-sale-hosted storefront in parallel; inventory must synchronize automatically. Hosted checkout remains authoritative for Clearance-sale purchases.

## Intent_DNA delta
JOURNEY: source store authorization -> variant/SKU mapping -> inventory sync -> atomic reservation or allocated stock -> order -> fulfillment/return -> reconciliation.
OBJECT: InventoryConnection, VariantMapping, StockSnapshot, Reservation, EventInbox, ReconciliationRun.
OWNER: explicit single stock SoT per seller/variant; Clearance-sale owns its order/payment records.
INVARIANT: no oversell claim without atomic shared reservations; signed/idempotent webhooks, no cross-seller access, fail-closed on stale stock, no automatic restock from refund alone.
RISK: concurrent sales, stale webhooks, partial API failures, duplicated events, wrong variant mapping.

## ARKAON deliverables
1. Inventory capability registry for seller-authorized platforms: atomic reserve, webhooks, stock write, variants, polling, limits.
2. Incremental adapter generation in isolated sandbox with signed specs and tenant-scoped credentials references only.
3. Seller SKU matching UI and explicit source-of-truth selection; warn on ambiguous mapping.
4. Durable sync inbox, version-aware updates, reservation/compensation state machine, reconciliation and stock drift alerts.
5. Race tests across original and hosted store; failover to dedicated stock allocation where shared atomic reservation unavailable.
6. ETERNIAN audit packet with proofs and rollback; operator release approval required.

Status: instruction stored; no autonomous ingestion, running sync service or live inventory connection is claimed.
