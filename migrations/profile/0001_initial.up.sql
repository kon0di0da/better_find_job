CREATE SCHEMA IF NOT EXISTS profile;

CREATE TABLE profile.candidate_resumes (
  resume_id uuid PRIMARY KEY,
  candidate_id uuid NOT NULL,
  tenant_id uuid NOT NULL,
  current_version integer NOT NULL DEFAULT 0 CHECK (current_version >= 0),
  object_key text NOT NULL,
  file_name text NOT NULL,
  mime_type text NOT NULL,
  size_bytes bigint NOT NULL CHECK (size_bytes > 0 AND size_bytes <= 10485760),
  checksum_sha256 char(64) NOT NULL,
  status varchar(24) NOT NULL DEFAULT 'PENDING',
  version integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz NULL,
  UNIQUE (tenant_id, candidate_id, resume_id)
);
CREATE INDEX idx_candidate_resumes_candidate ON profile.candidate_resumes(tenant_id, candidate_id) WHERE deleted_at IS NULL;

CREATE TABLE profile.resume_versions (
  resume_version_id uuid PRIMARY KEY,
  resume_id uuid NOT NULL REFERENCES profile.candidate_resumes(resume_id) ON DELETE CASCADE,
  version integer NOT NULL CHECK (version > 0),
  schema_version varchar(32) NOT NULL,
  content_json jsonb NOT NULL,
  source varchar(24) NOT NULL DEFAULT 'PARSER',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz NULL,
  UNIQUE (resume_id, version)
);
CREATE INDEX idx_resume_versions_resume ON profile.resume_versions(resume_id, version DESC);

CREATE TABLE profile.resume_evidence (
  evidence_id uuid PRIMARY KEY,
  resume_version_id uuid NOT NULL REFERENCES profile.resume_versions(resume_version_id) ON DELETE CASCADE,
  page_no integer NULL CHECK (page_no IS NULL OR page_no > 0),
  start_offset integer NOT NULL CHECK (start_offset >= 0),
  end_offset integer NOT NULL CHECK (end_offset > start_offset),
  quote text NOT NULL,
  checksum_sha256 char(64) NOT NULL,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz NULL,
  UNIQUE (resume_version_id, evidence_id)
);
CREATE INDEX idx_resume_evidence_version ON profile.resume_evidence(resume_version_id);

CREATE TABLE profile.job_descriptions (
  jd_id uuid PRIMARY KEY,
  candidate_id uuid NOT NULL,
  tenant_id uuid NOT NULL,
  version integer NOT NULL DEFAULT 1 CHECK (version > 0),
  raw_text text NOT NULL,
  profile_json jsonb NOT NULL,
  status varchar(24) NOT NULL DEFAULT 'READY',
  warning_codes jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz NULL,
  UNIQUE (tenant_id, candidate_id, jd_id)
);
CREATE INDEX idx_job_descriptions_candidate ON profile.job_descriptions(tenant_id, candidate_id) WHERE deleted_at IS NULL;

CREATE TABLE profile.deletion_jobs (
  deletion_job_id uuid PRIMARY KEY,
  subject_hash char(64) NOT NULL,
  resume_id uuid NULL,
  scope varchar(24) NOT NULL,
  status varchar(24) NOT NULL DEFAULT 'PENDING',
  attempts smallint NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 3),
  pending_targets jsonb NOT NULL DEFAULT '[]'::jsonb,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  deadline_at timestamptz NOT NULL,
  completed_at timestamptz NULL,
  version integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz NULL
);
CREATE INDEX idx_deletion_jobs_due ON profile.deletion_jobs(status, deadline_at);
