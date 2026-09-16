# Public Pattern Catalog — 30 candidates

`knowledge/patterns/candidates/` contains exactly 30 substantive candidates derived only
from implemented ARKAON modules and tests. They are not production promotions and are not
owned assets. Every package remains `ETHERNIAN_REVIEW_REQUIRED`.

The validator recomputes source/test evidence hashes, package hashes, semantic fingerprints,
catalog coverage, and uniqueness. Promotion requires an external Ed25519 signature bound to
the catalog revision, exact package and evidence/test digests, policy, expiry, and one-time
nonce. Runtime code contains a public key only. Test signing is labelled `TEST_VECTOR` and
cannot be interpreted as a production decision.

The reuse proof runner requires at least three separately approved public patterns and rejects
all candidates before promotion. A public-pattern approval never changes `owned_asset=false`.

Readiness: catalog candidates and verification harness are implemented. Thirty external
Ethernian decisions and a production reuse proof remain pending; no promotion is claimed.
