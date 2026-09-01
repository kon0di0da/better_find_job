CREATE SCHEMA IF NOT EXISTS knowledge;

CREATE TABLE knowledge.questions (
  question_id uuid PRIMARY KEY,
  current_version integer NOT NULL DEFAULT 1 CHECK (current_version > 0),
  review_status varchar(24) NOT NULL DEFAULT 'PENDING',
  enabled boolean NOT NULL DEFAULT false,
  version integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz NULL
);
CREATE INDEX idx_questions_eligible ON knowledge.questions(review_status, enabled) WHERE deleted_at IS NULL;

CREATE TABLE knowledge.question_versions (
  question_version_id uuid PRIMARY KEY,
  question_id uuid NOT NULL REFERENCES knowledge.questions(question_id) ON DELETE RESTRICT,
  version integer NOT NULL CHECK (version > 0),
  question_type varchar(24) NOT NULL,
  stem text NOT NULL,
  difficulty varchar(16) NOT NULL,
  skill_tags jsonb NOT NULL,
  rubric_version varchar(64) NOT NULL,
  rubric_json jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz NULL,
  UNIQUE (question_id, version)
);
CREATE INDEX idx_question_versions_question ON knowledge.question_versions(question_id, version DESC);

CREATE TABLE knowledge.merge_cases (
  merge_case_id uuid PRIMARY KEY,
  left_question_id uuid NOT NULL REFERENCES knowledge.questions(question_id),
  right_question_id uuid NOT NULL REFERENCES knowledge.questions(question_id),
  similarity numeric(5,4) NOT NULL CHECK (similarity BETWEEN 0 AND 1),
  status varchar(24) NOT NULL DEFAULT 'OPEN',
  version integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz NULL,
  CHECK (left_question_id <> right_question_id),
  UNIQUE (left_question_id, right_question_id, status)
);
CREATE INDEX idx_merge_cases_status ON knowledge.merge_cases(status, created_at);
