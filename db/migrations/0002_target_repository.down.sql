BEGIN;

ALTER TABLE IF EXISTS analysis_targets
  DROP CONSTRAINT IF EXISTS ck_target_evidence_array,
  DROP CONSTRAINT IF EXISTS ck_target_permissions_object,
  DROP COLUMN IF EXISTS request_fingerprint,
  DROP COLUMN IF EXISTS source_evidence_ids_json,
  DROP COLUMN IF EXISTS permissions_json;

COMMIT;
