# Public Pattern Catalog — 30 candidates

`knowledge/patterns/candidates/` contains exactly 30 substantive candidates derived only
from implemented ARKAON modules and tests. They are not production promotions and are not
owned assets. Every package remains `ETHERNIAN_REVIEW_REQUIRED`.

The validator recomputes source/test evidence hashes, package hashes, semantic fingerprints,
catalog coverage, and uniqueness.

Each `evidence_hashes` entry is SHA-256 over **evidence bytes for hashing**, not necessarily
the on-disk raw file bytes. For **text** evidence (known text suffixes such as `.py`, and no
NUL bytes), bytes are normalized by replacing CRLF (`\r\n`) with LF (`\n`) before hashing so
Linux CI checkouts and CRLF worktrees agree. **Binary** evidence (NUL present or non-text suffix)
uses the raw byte stream unchanged. `tools/generate_pattern_candidates.py` and
`apf.pattern_catalog.validate_catalog` share the same rule via `evidence_file_digest()`.

Promotion requires an external Ed25519 signature bound to
the catalog revision, exact package and evidence/test digests, policy, expiry, and one-time
nonce. Runtime code contains a public key only. Test signing is labelled `TEST_VECTOR` and
cannot be interpreted as a production decision.

The reuse proof runner requires at least three separately approved public patterns and rejects
all candidates before promotion. A public-pattern approval never changes `owned_asset=false`.

Readiness: catalog candidates and verification harness are implemented. Thirty external
Ethernian decisions and a production reuse proof remain pending; no promotion is claimed.
