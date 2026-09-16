from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "knowledge" / "patterns" / "candidates"


SPECS = [
    (
        "intent-dna-lock",
        "Intent DNA Lock",
        "Bind every execution to an immutable approved intent fingerprint.",
        "src/apf/intent_lock.py",
        "tests/test_intent_lock.py",
    ),
    (
        "principal-capability-separation",
        "Principal Capability Separation",
        "Separate actor identity from narrowly scoped execution authority.",
        "src/apf/domain.py",
        "tests/test_api.py",
    ),
    (
        "tenant-bound-ownership",
        "Tenant-bound Ownership",
        "Revalidate tenant and owner relationships at every protected operation.",
        "src/apf/repository.py",
        "tests/test_repository_contract.py",
    ),
    (
        "one-time-approval-token",
        "One-time Approval Token",
        "Consume narrowly bound human approval exactly once before mutation.",
        "src/apf/approval_tokens.py",
        "tests/test_approval_tokens.py",
    ),
    (
        "state-machine-guard",
        "State Machine Guard",
        "Permit lifecycle changes only through explicit transition rules.",
        "src/apf/state_machine.py",
        "tests/test_state_machine.py",
    ),
    (
        "idempotent-command-receipt",
        "Idempotent Command Receipt",
        "Make retried commands return the same committed result without duplicate effects.",
        "src/apf/development_orchestrator.py",
        "tests/test_development_orchestrator.py",
    ),
    (
        "hash-chained-ledger",
        "Hash-chained Audit Ledger",
        "Make ordered audit history tamper-evident with predecessor-bound hashes.",
        "src/apf/orchestrator_storage.py",
        "tests/test_orchestrator_storage.py",
    ),
    (
        "optimistic-version-guard",
        "Optimistic Version Guard",
        "Reject stale writers before they overwrite newer durable state.",
        "src/apf/durable_review.py",
        "tests/test_durable_review.py",
    ),
    (
        "evidence-content-addressing",
        "Evidence Content Addressing",
        "Address evidence by verified content digest rather than mutable location.",
        "src/apf/evidence_vault.py",
        "tests/test_evidence_vault.py",
    ),
    (
        "provenance-chain",
        "Provenance Chain",
        "Carry origin, authorization, and transformation evidence through asset review.",
        "src/apf/authorized_material.py",
        "tests/test_authorized_material.py",
    ),
    (
        "license-obligation-gate",
        "License Obligation Gate",
        "Block reuse until license permissions and obligations are explicit.",
        "src/apf/learning_safety.py",
        "tests/test_learning_safety.py",
    ),
    (
        "secret-redaction-boundary",
        "Secret Redaction Boundary",
        "Remove credentials and session material before analysis or persistence.",
        "src/apf/authorized_material.py",
        "tests/test_authorized_material.py",
    ),
    (
        "authorized-origin-allowlist",
        "Authorized Origin Allowlist",
        "Restrict collectors to pre-authorized origins and revalidate redirects.",
        "src/apf/collector_runtime.py",
        "tests/test_collector_runtime.py",
    ),
    (
        "bounded-collection-budget",
        "Bounded Collection Budget",
        "Enforce request, size, rate, and media limits during acquisition.",
        "src/apf/collector_service.py",
        "tests/test_collector_service.py",
    ),
    (
        "robots-policy-check",
        "Robots Policy Check",
        "Evaluate declared crawl policy before retrieving public material.",
        "src/apf/continuous_collection.py",
        "tests/test_continuous_collection.py",
    ),
    (
        "static-normalization-sandbox",
        "Static Normalization Sandbox",
        "Normalize authorized minified material without executing untrusted code.",
        "src/apf/execution_sandbox.py",
        "tests/test_execution_sandbox.py",
    ),
    (
        "mediated-auth-attestation",
        "Mediated Auth Attestation",
        "Bind user-mediated authentication evidence to the exact acquisition request.",
        "src/apf/mediated_auth.py",
        "tests/test_mediated_auth.py",
    ),
    (
        "external-review-attestation",
        "External Review Attestation",
        "Require externally signed and expiring review evidence for gated progress.",
        "src/apf/analog_review.py",
        "tests/test_analog_review.py",
    ),
    (
        "nonce-replay-defense",
        "Nonce Replay Defense",
        "Consume signed decision nonces once to prevent approval replay.",
        "src/apf/analog_review.py",
        "tests/test_analog_review.py",
    ),
    (
        "candidate-not-asset",
        "Candidate Not Asset",
        "Keep reviewed candidates distinct from owned or production assets.",
        "src/apf/asset_registry.py",
        "tests/test_asset_registry.py",
    ),
    (
        "clean-room-analog-synthesis",
        "Clean-room Analog Synthesis",
        "Convert observed behavior into independent specifications and implementation evidence.",
        "src/apf/analog_synthesis.py",
        "tests/test_analog_synthesis.py",
    ),
    (
        "similarity-leakage-guard",
        "Similarity Leakage Guard",
        "Reject outputs retaining excessive source identifiers or verbatim fragments.",
        "src/apf/learning_safety.py",
        "tests/test_learning_safety.py",
    ),
    (
        "role-separated-benchmark",
        "Role-separated Benchmark",
        "Separate producer, attacker, judge, and approver roles in evaluation.",
        "src/apf/role_benchmark.py",
        "tests/test_role_benchmark.py",
    ),
    (
        "deterministic-test-vector",
        "Deterministic Test Vector",
        "Label synthetic signing and benchmark artifacts so they cannot imply production approval.",
        "src/apf/certification_vectors.py",
        "tests/test_release_certification.py",
    ),
    (
        "release-manifest-binding",
        "Release Manifest Binding",
        "Bind release decisions to exact artifact, test, evidence, and policy digests.",
        "src/apf/release_certification.py",
        "tests/test_release_certification.py",
    ),
    (
        "durable-review-queue",
        "Durable Review Queue",
        "Persist open and completed reviews with restart-safe ordering and integrity checks.",
        "src/apf/durable_review.py",
        "tests/test_console_durable.py",
    ),
    (
        "repository-contract-parity",
        "Repository Contract Parity",
        "Run one behavioral contract across memory and PostgreSQL repositories.",
        "src/apf/db.py",
        "tests/test_postgres_repository.py",
    ),
    (
        "migration-roundtrip",
        "Migration Roundtrip",
        "Verify schema upgrades and downgrades preserve declared database invariants.",
        "src/apf/migrations.py",
        "tests/test_migrations.py",
    ),
    (
        "read-only-pilot-observation",
        "Read-only Pilot Observation",
        "Gather platform metadata without write authority or operational side effects.",
        "src/apf/owned_platform_pilot.py",
        "tests/test_owned_platform_pilot.py",
    ),
    (
        "operations-console-boundary",
        "Operations Console Boundary",
        "Expose review operations through a server-enforced API rather than trusted UI state.",
        "src/apf/console.py",
        "tests/test_console.py",
    ),
]

# Per-pattern controls are intentionally explicit: this catalog is evidence, not a count target.
DETAILS = {
    "intent-dna-lock": (
        "canonical intent fingerprint compared before every transition",
        "stored fingerprint never changes after approval",
        "mismatched execution intent cannot advance",
        "noncanonical JSON changes the digest",
        "an alternate command path omits the check",
        "approved intent governs a multi-step job",
        "operators need an editable draft rather than a locked execution",
    ),
    "principal-capability-separation": (
        "principal resolution followed by capability scope verification",
        "identity alone grants no operation",
        "capability subject must equal the resolved principal",
        "role claims are mistaken for capabilities",
        "a capability is accepted for another subject",
        "actors receive task-scoped authority",
        "a trusted single-user offline utility has no authorization boundary",
    ),
    "tenant-bound-ownership": (
        "repository predicates include tenant and owner identifiers",
        "cross-tenant rows are never returned",
        "ownership is checked from durable state, not request claims",
        "an ID-only lookup leaks another tenant",
        "ownership changes between read and write",
        "shared storage serves independent organizations",
        "data is physically isolated with no shared query surface",
    ),
    "one-time-approval-token": (
        "HMAC-bound claims consumed under a lock",
        "task and result fingerprints match exactly",
        "a token identifier is consumed at most once",
        "expired approval authorizes a late mutation",
        "concurrent retries consume the token twice",
        "one human decision authorizes one sensitive command",
        "standing role permission is the intended policy",
    ),
    "state-machine-guard": (
        "transition table rejects undeclared source-to-target edges",
        "terminal states cannot silently reopen",
        "side effects occur only after a legal edge",
        "caller assigns a target state directly",
        "new states ship without transition coverage",
        "workflow legality is finite and enumerable",
        "state is merely descriptive and carries no behavior",
    ),
    "idempotent-command-receipt": (
        "idempotency key maps to a fingerprinted stored receipt",
        "same key and payload returns one result",
        "same key with different payload is rejected",
        "receipt persistence follows the side effect",
        "key scope collides across tenants",
        "clients retry commands after network ambiguity",
        "every invocation is intentionally a distinct event",
    ),
    "hash-chained-ledger": (
        "each entry hashes canonical content plus predecessor hash",
        "entry order is cryptographically committed",
        "chain verification starts from a defined genesis",
        "history rows are edited without recomputing descendants",
        "canonicalization differs across readers",
        "audit ordering must reveal tampering",
        "cryptographic non-repudiation requires an external signature service",
    ),
    "optimistic-version-guard": (
        "compare-and-swap rejects an unexpected aggregate version",
        "each successful mutation increments once",
        "stale expected versions produce no write",
        "two writers share the same accepted version",
        "retry code hides a genuine conflict",
        "concurrent reviewers update one aggregate",
        "the database operation is append-only and commutative",
    ),
    "evidence-content-addressing": (
        "SHA-256 digest indexes immutable evidence bytes",
        "retrieved bytes reproduce the recorded digest",
        "different content cannot reuse an evidence identity",
        "mutable files change behind a stable path",
        "digest metadata is trusted without byte verification",
        "review depends on exact captured material",
        "only a live external state observation matters",
    ),
    "provenance-chain": (
        "origin and authorization survive every transformation record",
        "every derivative points to its immediate source",
        "authorization evidence precedes acquisition",
        "a transformation drops license metadata",
        "two sources merge without separate lineage",
        "materials may become reusable candidates",
        "input is generated entirely inside the current transaction",
    ),
    "license-obligation-gate": (
        "permission class and obligations select the reuse route",
        "unknown licenses never enter direct reuse",
        "attribution and share-alike duties remain attached",
        "a permissive label lacks supporting evidence",
        "incompatible obligations are combined",
        "third-party material may be incorporated",
        "only internal proprietary code is involved",
    ),
    "secret-redaction-boundary": (
        "structured header, query, storage and body redactors run before persistence",
        "raw credentials never reach the evidence vault",
        "redaction markers reveal no secret value",
        "an uncommon token field escapes matching",
        "raw capture is logged before sanitization",
        "developer artifacts can contain authentication material",
        "the source format is proven incapable of carrying secrets",
    ),
    "authorized-origin-allowlist": (
        "normalized scheme-host-port tuple is checked after every redirect",
        "no request leaves approved origins",
        "redirect destinations receive a fresh policy check",
        "userinfo or port tricks alter origin parsing",
        "DNS or redirect moves collection outside scope",
        "collection authority names exact web origins",
        "a local supplied file requires no network access",
    ),
    "bounded-collection-budget": (
        "request count, byte size, media type and rate counters fail closed",
        "budget exhaustion stops further fetches",
        "declared size never overrides measured bytes",
        "streaming content exceeds its advertised length",
        "retries evade the request counter",
        "remote acquisition must limit operational impact",
        "a prevalidated local artifact is read once",
    ),
    "robots-policy-check": (
        "robots decision is recorded before a scheduled public fetch",
        "denied paths are not requested",
        "policy cache expiry triggers reevaluation",
        "stale robots data permits a newly denied path",
        "user-agent matching selects the wrong group",
        "automated public crawling is authorized",
        "the owner directly supplies the material",
    ),
    "static-normalization-sandbox": (
        "parser-only normalization forbids dynamic execution and network access",
        "untrusted scripts are never evaluated",
        "normalized output preserves analyzable structure",
        "parser confusion triggers executable fallback",
        "oversized syntax causes resource exhaustion",
        "authorized minified code needs structural inspection",
        "behavior can only be established by executing untrusted payloads",
    ),
    "mediated-auth-attestation": (
        "external signature binds request fingerprint, actions and grant reference",
        "gate holds verification key but no signing key",
        "interactive actions exactly match the approved request",
        "boolean approval is spoofed by the worker",
        "attestation is replayed against another request",
        "user must complete official authentication interaction",
        "public data requires no authenticated session",
    ),
    "external-review-attestation": (
        "Ed25519 decision binds candidate hash, policy, expiry and nonce",
        "reviewer signature covers the exact candidate",
        "expired or reused decisions never advance state",
        "candidate changes after signing",
        "worker possesses a reviewer signing key",
        "independent review is a required gate",
        "automated low-risk validation is policy-authorized",
    ),
    "nonce-replay-defense": (
        "atomic nonce consumption follows successful signature and binding checks",
        "invalid signatures never consume nonce state",
        "a valid nonce succeeds no more than once",
        "process-local nonce state resets unexpectedly",
        "two verifiers lack a shared consumption store",
        "signed decisions represent one-time authority",
        "the signed message is informational and reusable",
    ),
    "candidate-not-asset": (
        "separate status types prohibit candidate-to-owned coercion",
        "review approval does not establish ownership",
        "registry accepts only declared promotion outcomes",
        "generic strings bypass typed status checks",
        "UI labels imply ownership absent legal evidence",
        "learning outputs await rights and quality review",
        "the artifact was authored and registered through the owned-asset process",
    ),
    "clean-room-analog-synthesis": (
        "observations become behavior specs before independent implementation",
        "source fragments do not enter generated output",
        "implementation evidence traces to abstract requirements",
        "unique identifiers leak through the specification",
        "a developer copies implementation details from capture",
        "functionality may be independently reimplemented",
        "the license explicitly permits direct source reuse",
    ),
    "similarity-leakage-guard": (
        "token and identifier overlap thresholds quarantine suspicious output",
        "large verbatim fragments always block publication",
        "similarity decision is recorded with measured evidence",
        "renaming evades a lexical-only detector",
        "common framework boilerplate causes a false positive",
        "derived work must remain independently expressed",
        "direct reuse is authorized and attribution obligations are satisfied",
    ),
    "role-separated-benchmark": (
        "producer, attacker, judge and approver identities are independently assigned",
        "a producer cannot approve its own result",
        "attack findings remain visible to the judge",
        "one actor silently occupies multiple roles",
        "score aggregation hides a critical failure",
        "evaluation claims require adversarial independence",
        "a disposable developer unit test needs no governance decision",
    ),
    "deterministic-test-vector": (
        "fixed inputs and explicit TEST_VECTOR labels produce reproducible artifacts",
        "test signatures cannot be presented as production evidence",
        "repeated runs yield the same expected digest",
        "random time or nonce changes the fixture",
        "test keys are loaded by production configuration",
        "cryptographic failure paths need stable fixtures",
        "real approvals are being issued",
    ),
    "release-manifest-binding": (
        "release signature covers artifact, evidence, test and policy digests",
        "any released byte change invalidates certification",
        "release identity includes the complete tested manifest",
        "tests run against a different build",
        "mutable evidence URLs replace content hashes",
        "a deployable bundle needs independent certification",
        "an exploratory local build will not be distributed",
    ),
    "durable-review-queue": (
        "transactional queue persists open review, decision and receipt records",
        "restart preserves every unresolved review",
        "one review decision produces one durable receipt",
        "crash commits state without its receipt",
        "duplicate delivery creates two open reviews",
        "human review spans processes or restarts",
        "review finishes synchronously inside one failure-free call",
    ),
    "repository-contract-parity": (
        "one behavioral suite executes against memory and PostgreSQL adapters",
        "adapter-visible outcomes remain equivalent",
        "database-specific constraints strengthen rather than alter contracts",
        "memory tests miss transaction behavior",
        "SQL null or JSON semantics diverge",
        "multiple persistence adapters implement one port",
        "only one storage engine will ever exist",
    ),
    "migration-roundtrip": (
        "ordered upgrade and downgrade scripts are executed against schema invariants",
        "upgrade reaches the declared head once",
        "downgrade removes only revision-owned objects",
        "duplicate columns break fresh installs",
        "rollback destroys preexisting data structures",
        "versioned relational schema changes ship",
        "storage is ephemeral and schemaless",
    ),
    "read-only-pilot-observation": (
        "read-only capability and deterministic metadata snapshots prohibit writes",
        "pilot execution has no mutation route",
        "snapshot digest identifies the analyzed input",
        "read credentials unexpectedly allow writes",
        "live data changes during observation",
        "an owned platform is analyzed before integration",
        "the task requires modifying the platform",
    ),
    "operations-console-boundary": (
        "server APIs enforce tenant and reviewer checks regardless of UI state",
        "hidden buttons are never authorization controls",
        "detail responses remain tenant scoped",
        "client-supplied role unlocks an action",
        "cached UI data crosses tenant sessions",
        "operators inspect and decide queued work",
        "no human operations interface exists",
    ),
}


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for path in OUT.glob("*.json"):
        path.unlink()
    for slug, title, intent, source, test in SPECS:
        mechanism, invariant_a, invariant_b, failure_a, failure_b, applies, not_when = DETAILS[slug]
        hashes = {ref: digest((ROOT / ref).read_bytes()) for ref in (source, test)}
        source_names = re.findall(
            r"^(?:class|def) ([a-zA-Z_][a-zA-Z0-9_]*)", (ROOT / source).read_text(), re.MULTILINE
        )
        test_names = re.findall(
            r"^def (test_[a-zA-Z0-9_]+)\(", (ROOT / test).read_text(), re.MULTILINE
        )
        if not source_names or not test_names:
            raise RuntimeError(f"evidence anchor not found for {slug}")
        package = {
            "schema_version": "apf.pattern-candidate/1.0",
            "pattern_id": f"apf.public.{slug}",
            "version": "0.1.0",
            "title": title,
            "intent": intent,
            "problem": f"Without {mechanism}, the system can accept an outcome that is not justified by the {title.lower()} contract.",
            "context": f"This pattern addresses {applies}; its concrete control is {mechanism}.",
            "forces": [
                f"Correctness requires that {invariant_a}",
                f"Operational pressure can cause: {failure_a}",
            ],
            "solution": f"Implement {mechanism}. Verify the anchored symbol `{source_names[0]}` with `{test_names[0]}` before reuse.",
            "invariants": [invariant_a, invariant_b],
            "failure_modes": [failure_a, failure_b],
            "security": f"The security boundary specifically rejects `{failure_a}` and fails closed if the {title.lower()} evidence cannot be verified.",
            "privacy": f"For {title.lower()}, persist only its decision identifiers and digests; exclude payload data unrelated to {mechanism}.",
            "license_provenance": {
                "license": "INTERNAL_PROPRIETARY",
                "origin": "ARKAON_IMPLEMENTED_INTERNAL",
                "external_material_included": False,
            },
            "evidence_hashes": hashes,
            "source_refs": [source],
            "test_refs": [test],
            "verification_test_ids": [f"{test}::{test_names[0]}"],
            "reuse_constraints": [
                f"Confirm the target still requires: {applies}",
                f"Do not apply when: {not_when}",
                "External Ethernian promotion signature remains mandatory",
            ],
            "applies_when": applies,
            "not_when": not_when,
            "evidence_anchors": {"source_symbol": source_names[0], "test_name": test_names[0]},
            "status": "ETHERNIAN_REVIEW_REQUIRED",
            "owned_asset": False,
            "semantic_fingerprint": digest(
                canonical({"intent": intent, "source": source, "title": title})
            ),
        }
        package["package_hash"] = digest(canonical(package))
        (OUT / f"{slug}.json").write_text(json.dumps(package, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
