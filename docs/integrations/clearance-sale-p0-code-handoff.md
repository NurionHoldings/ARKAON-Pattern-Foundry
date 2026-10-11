# Clearance-sale P0 first implementation handoff

2026-10-12 first implementation added to Clearance-sale draft PR #1:
- `backend/core.py`: SQLite schema, seller registration and approved-seller principal, password PBKDF2 hashing, opaque session token hash, seller-scoped product and variant CRUD primitives, atomic stock reservation/release, idempotency key, audit events.
- `tests/test_core.py`: tests for seller approval, cross-tenant access, stock over-reservation, idempotency and invalid inputs.

GitHub paths:
https://github.com/NurionHoldings/Clearance-sale/blob/feat/seller-categories-pg-architecture/backend/core.py
https://github.com/NurionHoldings/Clearance-sale/blob/feat/seller-categories-pg-architecture/tests/test_core.py

IMPORTANT: code was committed through GitHub connector. Tests have not yet been executed in a verified runtime. No web API, buyer auth, PG payment, stock external sync, push delivery, migrations, production secrets or deployed backend. Do not report any test as PASS without a recorded run.

## Immediate ARKAON review tasks
1. Run `python -m unittest discover -s tests -v` in a clean checkout and capture environment and results.
2. Audit session security, brute-force rate limiting, role checks, authorization, DB transaction isolation, SQLite WAL/concurrency, idempotency lifecycle and audit provenance. Fix defects through PRs.
3. Introduce migration tooling and a secure HTTP API (CSRF/session cookie or token strategy, origin controls, throttling, TLS deployment assumptions) before exposing endpoints.
4. Define and test seller approval admin process and seller/PG provider distinct principals.
5. Implement reservation expiry, commit/compensation, order and verified PG sandbox flows only after ownership/ledger tests.
6. Evaluate Postgres concurrency for production and avoid implying SQLite local test is production-grade.
7. Return ETERNIAN audit packet with exact test run, changed SHA, findings and HOLD/PASS recommendation.

No merge/deploy without operator approval. This handoff document is not evidence that a running autonomous agent consumed it.
