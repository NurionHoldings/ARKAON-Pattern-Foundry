BEGIN;

DROP TABLE IF EXISTS candidate_manifests;
DROP TABLE IF EXISTS review_tasks;
DROP TABLE IF EXISTS command_receipts;
DROP TABLE IF EXISTS durable_events;
DROP TABLE IF EXISTS durable_jobs;

COMMIT;
