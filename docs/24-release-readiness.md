# Pattern Foundry v0.1 release-readiness runbook (#036)

This certification is a **local release-readiness record**, not evidence of production
deployment. The harness performs no network collection and holds no private signing key.

## Local certification

1. Check out the exact revision to be certified and keep the worktree clean.
2. Run the full test suite and Ruff. Run the SQLite migration against a new database and
   verify the resulting schema version.
3. Produce one immutable artifact for every check in `MANDATORY_CHECKS`. Each artifact is
   a digest-bound result signed by the independent CI/reviewer artifact key and bound to
   revision, build, policy and schema versions.
4. Run the sealed `CanonicalVectorSuite`; arbitrary caller callbacks are rejected. Its five
   deterministic executors call the real #032–#035 APIs and an ephemeral SQLite store:
   no-auth licensed reuse, user-mediated authenticated adaptive reimplementation,
   reviewer-required, deny, and expiry/recovery. Every transition trace, event head, actual
   candidate and license obligation is hashed. `prepare` executes the suite twice.
5. Send the prepared canonical manifest to the offline release signer. Give the harness only
   the signed attestation and the release public key. Call `accept`, archive the canonical JSON,
   then verify its signature and every referenced artifact digest after restore.

An unsigned manifest, a plain `PASS` flag, a skipped vector, or a digest without its valid
binding cannot open the gate. All candidates must remain `CANDIDATE_NOT_OWNED_ASSET`.

## Keys and rotation

- Keep artifact and release private keys in separate operator stores. Runtime configuration
  contains public keys only; never store private keys or credentials in fixtures or manifests.
- Rotate by provisioning new public-key identifiers, completing an overlap verification,
  revoking the old identifier, and recording the rotation as a separately signed artifact.
- A lost, exposed, or unexpectedly used key immediately invalidates the affected build.

## Backup, restore, and incidents

- Back up the durable review database, canonical manifests, check artifacts, public keys and
  revocation ledger as one versioned set. Captured raw material and secrets are not included.
- On restore, verify backup digest, SQLite integrity/schema migration, job/event hash chains,
  candidate hashes, manifest signature, artifact signatures and the revocation ledger before
  resuming work.
- On suspected tampering, credential leakage, rights dispute or signature replay: stop intake,
  quarantine affected jobs/candidates, revoke grants and signing keys, preserve hash evidence,
  investigate, rotate, and recertify. Never silently repair an accepted record.

## Authentication and license operations

Authentication remains user-mediated through official browserAuth/OAuth/connector flows.
The system may request the user to sign in but may not retain a password, bypass MFA/CAPTCHA or
access controls, or autonomously authenticate. Grants are opaque, scoped and expiring.
Attribution, notice, redistribution and source-disclosure obligations are carried into the
vector result and must be satisfied before any later release decision.

## Explicit limits

v0.1 does not autonomously crawl live sites, bypass authentication or access controls, defeat
DRM, or promote a candidate into an owned asset. It certifies local control behavior only.
Production hosting, secrets infrastructure, live connector configuration, monitoring, disaster
recovery drills, legal approval and deployment authorization remain deployment-only work.
