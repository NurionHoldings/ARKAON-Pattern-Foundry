BEGIN;

CREATE TABLE tenants (
  id uuid PRIMARY KEY,
  name varchar(200) NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE analysis_targets (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  name varchar(200) NOT NULL,
  target_type varchar(40) NOT NULL,
  classification varchar(40) NOT NULL CHECK (classification <> 'PROHIBITED'),
  state varchar(40) NOT NULL DEFAULT 'DRAFT',
  revision integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid NOT NULL,
  UNIQUE (tenant_id, name)
);

CREATE TABLE source_evidence (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  target_id uuid NOT NULL REFERENCES analysis_targets(id),
  source_type varchar(40) NOT NULL,
  locator text NOT NULL,
  content_hash char(64) NOT NULL,
  license_id varchar(200),
  authorization_id uuid,
  derivation_allowed boolean NOT NULL DEFAULT false,
  classification varchar(40) NOT NULL,
  acquired_at timestamptz NOT NULL,
  created_by uuid NOT NULL,
  UNIQUE (tenant_id, target_id, content_hash)
);

CREATE TABLE target_snapshots (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  target_id uuid NOT NULL REFERENCES analysis_targets(id),
  manifest_hash char(64) NOT NULL,
  sealed_at timestamptz NOT NULL,
  created_by uuid NOT NULL,
  UNIQUE (target_id, manifest_hash)
);

CREATE TABLE analysis_runs (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  snapshot_id uuid NOT NULL REFERENCES target_snapshots(id),
  state varchar(40) NOT NULL DEFAULT 'QUEUED',
  intent_fingerprint char(64),
  analyzer_version varchar(80) NOT NULL,
  budget_json jsonb NOT NULL,
  revision integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid NOT NULL
);

CREATE UNIQUE INDEX uq_active_run_per_snapshot
ON analysis_runs(snapshot_id)
WHERE state IN (
  'QUEUED','INTENT_SCOPING','ANALYZING','ABSTRACTING','VALIDATING',
  'REVIEW_PENDING','PARTIAL_REVIEW','HOLD'
);

CREATE TABLE intent_dna (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  analysis_run_id uuid NOT NULL REFERENCES analysis_runs(id),
  axes_json jsonb NOT NULL,
  completeness numeric(4,3) NOT NULL CHECK (completeness BETWEEN 0 AND 1),
  fingerprint char(64) NOT NULL,
  locked boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid NOT NULL,
  UNIQUE (analysis_run_id, fingerprint)
);

CREATE TABLE pattern_candidates (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  analysis_run_id uuid NOT NULL REFERENCES analysis_runs(id),
  slug varchar(200) NOT NULL,
  state varchar(40) NOT NULL DEFAULT 'DRAFT',
  risk_class varchar(20) NOT NULL,
  content_hash char(64) NOT NULL,
  revision integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid NOT NULL,
  UNIQUE (tenant_id, content_hash)
);

CREATE TABLE approvals (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  candidate_id uuid NOT NULL REFERENCES pattern_candidates(id),
  approver_id uuid NOT NULL,
  approver_role varchar(80) NOT NULL,
  decision varchar(30) NOT NULL,
  expected_content_hash char(64) NOT NULL,
  decided_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (candidate_id, approver_id, expected_content_hash)
);

CREATE TABLE pattern_packages (
  id uuid PRIMARY KEY,
  candidate_id uuid NOT NULL REFERENCES pattern_candidates(id),
  namespace varchar(200) NOT NULL,
  slug varchar(200) NOT NULL,
  version varchar(30) NOT NULL,
  status varchar(30) NOT NULL,
  content_hash char(64) NOT NULL,
  published_at timestamptz NOT NULL,
  UNIQUE (namespace, slug, version),
  UNIQUE (content_hash)
);

CREATE TABLE audit_events (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL,
  aggregate_type varchar(80) NOT NULL,
  aggregate_id uuid NOT NULL,
  event_type varchar(100) NOT NULL,
  actor_id uuid NOT NULL,
  correlation_id uuid NOT NULL,
  payload_json jsonb NOT NULL,
  occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_audit_aggregate ON audit_events(tenant_id, aggregate_type, aggregate_id, occurred_at);

COMMIT;

