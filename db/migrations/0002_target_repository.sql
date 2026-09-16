BEGIN;

ALTER TABLE analysis_targets
  ADD COLUMN permissions_json jsonb NOT NULL DEFAULT '{"read":true,"parse":false,"derive":false,"publish_common_pattern":false}'::jsonb,
  ADD COLUMN source_evidence_ids_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN request_fingerprint text NOT NULL DEFAULT '';

ALTER TABLE analysis_targets
  ADD CONSTRAINT ck_target_permissions_object CHECK (jsonb_typeof(permissions_json) = 'object'),
  ADD CONSTRAINT ck_target_evidence_array CHECK (jsonb_typeof(source_evidence_ids_json) = 'array');

COMMIT;
