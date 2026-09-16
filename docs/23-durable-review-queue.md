# Durable review queue (#035)

`DurableReviewRepository` is the restart-safe boundary between acquisition jobs and
Ethernian review. It uses Python's `sqlite3` module and does not execute collection or
authentication.

## Persistence boundary

The database stores tenant/job/principal bindings, request and job fingerprints, job state,
append-only event metadata, command receipts, review decisions, license obligations, content
hashes, and opaque `quarantine:<uuid>` references. It must never store captured response bodies,
DOM, HAR, source maps, credentials, passwords, cookies, authorization headers, session values,
or tokens. Persisted metadata is allow-structured and scanned fail closed.

The quarantined bytes remain in an independently controlled evidence vault. A reference is not
authority to read that vault.

## Schema and migration

Migration 1 is applied idempotently on repository construction:

- `durable_jobs`: tenant-scoped snapshot and unique `(tenant_id, idempotency_key)`.
- `durable_events`: ordered append-only hash chain scoped to a job.
- `command_receipts`: unique command/result record per tenant and job.
- `review_tasks`: RIGHTS, COLLECTION, or ORIGINALITY review and unique used nonce.
- `candidate_manifests`: hashes, opaque references, obligations, and the fixed status
  `CANDIDATE_NOT_OWNED_ASSET`.

All writes that change a job or close a review run under `BEGIN IMMEDIATE`. Job updates use a
conditional `WHERE version = expected_version`; therefore only one concurrent writer can win.
The event insertions and snapshot update commit or roll back together.

## Recovery integrity

Every load recomputes the complete event chain from `GENESIS` and checks sequence, previous hash,
job fingerprint, event body, head, count, state, and version against the bound snapshot hash.
Receipts must point to a matching event/state/version. Missing, inserted, reordered, edited, or
transplanted events fail loading. Expired open reviews are transitioned to `EXPIRED` during load.
Review tasks, command receipts, and candidate manifests each carry an immutable hash bound to the
job fingerprint and the relevant event head. Their fields are rehashed on every load; closed
reviews additionally require the original signed decision to verify again. Candidate manifests
are insert-only.

An integrity failure is a quarantine signal for the service layer. The repository does not try to
repair or silently accept suspicious state.

## Ethernian decisions

A review task can close only with a valid Ed25519 attestation. The signature binds task, job,
request, tenant, principal, stage, evidence fingerprint, decision, expiry, and nonce. The
repository receives only the public key. Wrong-key, altered, expired, cross-task, cross-job, and
replayed attestations fail closed.

Approval closes only that review gate. It does not promote a candidate or skip an orchestrator
transition. Candidate manifests can only use `CANDIDATE_NOT_OWNED_ASSET`; ownership remains an
explicit later governance action outside this component.
