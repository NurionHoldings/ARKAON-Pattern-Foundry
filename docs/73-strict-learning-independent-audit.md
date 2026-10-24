# Strict learning gate independent review

Reviewed source: 1fecb32c8b78aefa888b2c754d70e6b93807ab7f (split branch).
Render, IAM, services and logo changes are excluded from this review.

Corrections: missing/negative/fractional/boolean/nonfinite failure counts must not
pass metrics validation. Require a full commit SHA and nonblank CI run reference.
Reject traversal and symlink escape in lesson lookup.

Remaining HOLD: validators currently check supplied records, not externally
authenticated CI results or reviewer signatures. Work outcome hashes can only
prove internal consistency of supplied text. Held-out training separation still
depends on declarations/fingerprints rather than corpus membership validation.
Feedback path strings are not verified independent review artifacts.
READY_FOR_REVIEW means a candidate for a reviewer to investigate, not verified
learning improvement or operational readiness. No final improvement recognition,
automatic implementation, merge, deployment or global HOLD release is authorized.

The patch bundle in patches/ describes the original 0d3a63f snapshot only; it
does not contain these independent audit corrections. Review current branch
files for the final implementation. Do not apply that patch directly to main.
