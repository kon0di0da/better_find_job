CREATE SCHEMA IF NOT EXISTS interview;

CREATE TABLE interview.interview_plans (
  plan_id uuid PRIMARY KEY,
  candidate_id uuid NOT NULL,
  resume_version_id uuid NOT NULL,
  jd_id uuid NOT NULL,
  seed bigint NOT NULL DEFAULT 20260901,
  status varchar(24) NOT NULL DEFAULT 'DRAFT',
  constraint_report jsonb NOT NULL,
  version integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz NULL
);
CREATE INDEX idx_interview_plans_candidate ON interview.interview_plans(candidate_id, created_at DESC) WHERE deleted_at IS NULL;

CREATE TABLE interview.interview_plan_items (
  plan_item_id uuid PRIMARY KEY,
  plan_id uuid NOT NULL REFERENCES interview.interview_plans(plan_id) ON DELETE CASCADE,
  sequence_no smallint NOT NULL CHECK (sequence_no BETWEEN 1 AND 10),
  question_id uuid NOT NULL,
  question_version_id uuid NOT NULL,
  question_type varchar(24) NOT NULL,
  snapshot_json jsonb NOT NULL,
  project_id text NULL,
  evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz NULL,
  UNIQUE (plan_id, sequence_no),
  UNIQUE (plan_id, question_id)
);
CREATE INDEX idx_plan_items_plan ON interview.interview_plan_items(plan_id, sequence_no);

CREATE TABLE interview.interview_sessions (
  session_id uuid PRIMARY KEY,
  plan_id uuid NOT NULL UNIQUE REFERENCES interview.interview_plans(plan_id) ON DELETE RESTRICT,
  candidate_id uuid NOT NULL,
  state varchar(24) NOT NULL DEFAULT 'READY',
  current_index smallint NOT NULL DEFAULT 0 CHECK (current_index BETWEEN 0 AND 10),
  version integer NOT NULL DEFAULT 0,
  started_at timestamptz NULL,
  completed_at timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz NULL
);
CREATE INDEX idx_sessions_candidate ON interview.interview_sessions(candidate_id, created_at DESC) WHERE deleted_at IS NULL;

CREATE TABLE interview.interview_answers (
  answer_id uuid PRIMARY KEY,
  session_id uuid NOT NULL REFERENCES interview.interview_sessions(session_id) ON DELETE CASCADE,
  question_index smallint NOT NULL CHECK (question_index BETWEEN 1 AND 10),
  kind varchar(16) NOT NULL CHECK (kind IN ('MAIN','FOLLOW_UP')),
  status varchar(16) NOT NULL CHECK (status IN ('ANSWERED','UNANSWERED')),
  answer_text text NULL,
  content_hash char(64) NULL,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz NULL,
  UNIQUE (session_id, question_index, kind)
);
CREATE INDEX idx_answers_session ON interview.interview_answers(session_id, question_index);

CREATE TABLE interview.assessments (
  assessment_id uuid PRIMARY KEY,
  session_id uuid NOT NULL REFERENCES interview.interview_sessions(session_id) ON DELETE CASCADE,
  status varchar(24) NOT NULL DEFAULT 'PENDING',
  total_score numeric(5,1) NULL CHECK (total_score BETWEEN 0 AND 100),
  rubric_version varchar(64) NOT NULL,
  prompt_version varchar(64) NOT NULL,
  model_version varchar(64) NOT NULL,
  weight_version varchar(64) NOT NULL,
  calculator_version varchar(64) NOT NULL,
  recompute_hash char(64) NULL,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz NULL,
  UNIQUE (session_id, version)
);
CREATE INDEX idx_assessments_session ON interview.assessments(session_id, created_at DESC);

CREATE TABLE interview.assessment_items (
  assessment_item_id uuid PRIMARY KEY,
  assessment_id uuid NOT NULL REFERENCES interview.assessments(assessment_id) ON DELETE CASCADE,
  question_index smallint NOT NULL CHECK (question_index BETWEEN 1 AND 10),
  status varchar(24) NOT NULL,
  score numeric(5,1) NOT NULL CHECK (score BETWEEN 0 AND 100),
  dimensions_json jsonb NOT NULL,
  evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  rationale text NULL,
  advice_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz NULL,
  UNIQUE (assessment_id, question_index)
);
CREATE INDEX idx_assessment_items_assessment ON interview.assessment_items(assessment_id, question_index);

CREATE TABLE interview.idempotency_records (
  idempotency_id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL,
  actor_id uuid NOT NULL,
  method varchar(12) NOT NULL,
  normalized_path text NOT NULL,
  idempotency_key varchar(128) NOT NULL,
  payload_hash char(64) NOT NULL,
  response_status integer NOT NULL,
  response_body jsonb NOT NULL,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz NULL,
  expires_at timestamptz NOT NULL,
  UNIQUE (tenant_id, actor_id, method, normalized_path, idempotency_key)
);
CREATE INDEX idx_idempotency_expiry ON interview.idempotency_records(expires_at);

CREATE TABLE interview.audit_events (
  audit_event_id uuid PRIMARY KEY,
  actor_id uuid NULL,
  actor_role varchar(32) NOT NULL,
  action varchar(64) NOT NULL,
  target_type varchar(64) NOT NULL,
  target_id_hash char(64) NOT NULL,
  before_hash char(64) NULL,
  after_hash char(64) NULL,
  trace_id varchar(128) NOT NULL,
  result varchar(24) NOT NULL,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz NULL
);
CREATE INDEX idx_audit_events_target ON interview.audit_events(target_type, target_id_hash, created_at DESC);

CREATE TABLE interview.async_tasks (
  task_id uuid PRIMARY KEY,
  task_type varchar(64) NOT NULL,
  aggregate_id uuid NOT NULL,
  status varchar(24) NOT NULL DEFAULT 'PENDING',
  attempt smallint NOT NULL DEFAULT 0 CHECK (attempt BETWEEN 0 AND 3),
  payload jsonb NOT NULL,
  last_error_code varchar(64) NULL,
  next_run_at timestamptz NULL,
  version integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz NULL
);
CREATE INDEX idx_async_tasks_runnable ON interview.async_tasks(status, next_run_at);

CREATE TABLE interview.bad_cases (
  bad_case_id uuid PRIMARY KEY,
  session_id uuid NOT NULL REFERENCES interview.interview_sessions(session_id) ON DELETE CASCADE,
  category varchar(32) NOT NULL,
  note text NULL,
  status varchar(24) NOT NULL DEFAULT 'OPEN',
  owner_id uuid NULL,
  version integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz NULL
);
CREATE INDEX idx_bad_cases_open ON interview.bad_cases(status, category, created_at) WHERE deleted_at IS NULL;

CREATE TABLE interview.event_outbox (
  event_id uuid PRIMARY KEY,
  aggregate_id uuid NOT NULL,
  event_type varchar(80) NOT NULL,
  event_version integer NOT NULL,
  envelope jsonb NOT NULL,
  status varchar(24) NOT NULL DEFAULT 'PENDING',
  attempts smallint NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz NULL
);
CREATE INDEX idx_event_outbox_publish ON interview.event_outbox(status, created_at);

CREATE TABLE interview.event_inbox (
  consumer_name varchar(80) NOT NULL,
  event_id uuid NOT NULL,
  aggregate_id uuid NOT NULL,
  aggregate_version integer NULL,
  processed_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz NULL,
  version integer NOT NULL DEFAULT 1,
  PRIMARY KEY (consumer_name, event_id)
);
