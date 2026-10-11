# Clearance-sale seller mobile sales/stock notification — ARKAON task packet

Source: https://github.com/NurionHoldings/Clearance-sale/blob/feat/seller-categories-pg-architecture/docs/seller-mobile-notifications.md

User requirement: seller must be able to receive near-real-time notifications on phone for at least Clearance-sale sales and inventory status.

Intent_DNA: JOURNEY paid order/stock change -> verified event -> durable outbox -> tenant-scoped push/in-app -> seller dashboard; OBJECT seller devices, notification preferences, delivery attempts, stock thresholds; INVARIANT seller isolation, verified payments, idempotent delivery, no buyer PII in lock-screen alerts; RISK delayed/offline push, token leakage, notification spam, duplicate webhook, stale stock.

ARKAON proposals:
1. Implement mobile-first seller dashboard with accurate paid/cancelled/refunded sales and stock freshness.
2. Add authenticated PWA Web Push device registration and opt-in, revoke/logout flow and real-time in-app channel.
3. Emit server-side payment/inventory events transactionally; durable delivery, deduplication, retries and dead-letter monitoring.
4. Configure seller low-stock thresholds and stock-sync-failure warnings.
5. Optional SMS/Kakao approved-provider fallback after policy, costs and consent review.
6. Test cross-tenant isolation, duplicate events, notification permission denied, stock outages, device revocation, and reconciliation. Provide evidence for ETERNIAN audit and operator approval.

No claim of currently functioning push service; this packet only records scope.
