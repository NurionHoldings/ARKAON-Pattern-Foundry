BEGIN;

DROP TABLE IF EXISTS audit_events;
DROP TABLE IF EXISTS pattern_packages;
DROP TABLE IF EXISTS approvals;
DROP TABLE IF EXISTS pattern_candidates;
DROP TABLE IF EXISTS intent_dna;
DROP TABLE IF EXISTS analysis_runs;
DROP TABLE IF EXISTS target_snapshots;
DROP TABLE IF EXISTS source_evidence;
DROP TABLE IF EXISTS analysis_targets;
DROP TABLE IF EXISTS tenants;

COMMIT;
