BEGIN;

CREATE TABLE durable_jobs (
  tenant_id varchar(64) NOT NULL,
  job_id varchar(64) NOT NULL,
  principal_id varchar(64) NOT NULL,
  request_fingerprint varchar(80) NOT NULL,
  job_fingerprint varchar(80) NOT NULL,
  idempotency_key varchar(128) NOT NULL,
  create_payload_fingerprint varchar(80) NOT NULL,
  state varchar(40) NOT NULL,
  version integer NOT NULL,
  event_head varchar(80) NOT NULL,
  event_count integer NOT NULL,
  expires_at timestamptz NOT NULL,
  snapshot_hash varchar(80) NOT NULL,
  quarantined boolean NOT NULL DEFAULT false,
  PRIMARY KEY (tenant_id, job_id),
  UNIQUE (tenant_id, idempotency_key)
);

CREATE TABLE durable_events (
  tenant_id varchar(64) NOT NULL,
  job_id varchar(64) NOT NULL,
  sequence integer NOT NULL,
  job_fingerprint varchar(80) NOT NULL,
  event_type varchar(64) NOT NULL,
  state varchar(40) NOT NULL,
  version integer NOT NULL,
  occurred_at timestamptz NOT NULL,
  metadata jsonb NOT NULL,
  previous_hash varchar(80) NOT NULL,
  event_hash varchar(80) NOT NULL,
  PRIMARY KEY (tenant_id, job_id, sequence),
  UNIQUE (tenant_id, job_id, event_hash),
  FOREIGN KEY (tenant_id, job_id) REFERENCES durable_jobs (tenant_id, job_id)
);

CREATE TABLE command_receipts (
  tenant_id varchar(64) NOT NULL,
  job_id varchar(64) NOT NULL,
  command_id varchar(128) NOT NULL,
  payload_fingerprint varchar(80) NOT NULL,
  resulting_state varchar(40) NOT NULL,
  resulting_version integer NOT NULL,
  event_hash varchar(80) NOT NULL,
  receipt_hash varchar(80) NOT NULL,
  PRIMARY KEY (tenant_id, job_id, command_id),
  FOREIGN KEY (tenant_id, job_id) REFERENCES durable_jobs (tenant_id, job_id)
);

CREATE TABLE review_tasks (
  tenant_id varchar(64) NOT NULL,
  task_id varchar(64) NOT NULL,
  job_id varchar(64) NOT NULL,
  request_fingerprint varchar(80) NOT NULL,
  principal_id varchar(64) NOT NULL,
  stage varchar(32) NOT NULL,
  reason_code varchar(64) NOT NULL,
  evidence_fingerprint varchar(80) NOT NULL,
  expires_at timestamptz NOT NULL,
  status varchar(32) NOT NULL,
  decision_nonce varchar(64),
  decision varchar(32),
  decision_expires_at timestamptz,
  decision_signature varchar(256),
  job_event_head varchar(80) NOT NULL,
  task_hash varchar(80) NOT NULL,
  PRIMARY KEY (tenant_id, task_id),
  FOREIGN KEY (tenant_id, job_id) REFERENCES durable_jobs (tenant_id, job_id)
);

CREATE UNIQUE INDEX uq_review_nonce ON review_tasks (decision_nonce) WHERE decision_nonce IS NOT NULL;

CREATE TABLE candidate_manifests (
  tenant_id varchar(64) NOT NULL,
  job_id varchar(64) NOT NULL,
  candidate_hash varchar(80) NOT NULL,
  quarantine_reference varchar(80) NOT NULL,
  license_obligations jsonb NOT NULL,
  status varchar(64) NOT NULL CHECK (status = 'CANDIDATE_NOT_OWNED_ASSET'),
  job_event_head varchar(80) NOT NULL,
  manifest_hash varchar(80) NOT NULL,
  PRIMARY KEY (tenant_id, job_id),
  FOREIGN KEY (tenant_id, job_id) REFERENCES durable_jobs (tenant_id, job_id)
);

COMMIT;
