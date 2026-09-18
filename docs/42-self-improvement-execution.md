# Owner-approved self-improvement execution

The GitHub-to-PC approval path is fail-closed and content-addressed.

1. The owner commits `approvals/self-improvement/<request_id>.json` with the exact
   request and scope digest, approver, approval time, paths, and operations.
2. `GhApprovalSource` first resolves the commit that changed that receipt and then
   fetches the receipt at that exact commit. This prevents a content/commit race.
3. `record_approval` writes an idempotent local ledger entry. Reusing a request ID
   with any changed field is a conflict.
4. `run_in_approved_worktree` creates a detached worktree at an explicit base SHA,
   rejects unapproved scopes and operations, and permits only the test/lint command
   allowlist. It records content digests for stdout and stderr.

The runner does not merge, deploy, read secrets, or enable network access. The
result manifest must stop at `DEPLOYMENT_APPROVAL_PENDING` after ARKAON verification
and independent ETERNIAN audit/remediation evidence are recorded.

Invalid self-improvement packets are moved to
`quarantine/self-improvement/` with a `BLOCKED` sidecar receipt and a SHA-256 digest.
The relay then continues with later packets. No invalid packet is silently deleted.

Rollback is limited to reverting the feature commit. Quarantined source bytes and
their evidence receipts are retained for diagnosis and can be manually restored to
the inbox only after correction and a new scope validation.
