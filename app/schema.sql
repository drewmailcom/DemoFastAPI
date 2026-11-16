-- Applied on every start; every statement is idempotent.

CREATE TABLE IF NOT EXISTS users (
  id            serial PRIMARY KEY,
  username      text NOT NULL UNIQUE,
  password_hash text NOT NULL,
  role          text NOT NULL CHECK (role IN ('ADMIN', 'ANALYST', 'READ_ONLY'))
);

CREATE TABLE IF NOT EXISTS sessions (
  id         text PRIMARY KEY,
  user_id    int NOT NULL REFERENCES users ON DELETE CASCADE,
  expires_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
  id         serial PRIMARY KEY,
  name       text NOT NULL UNIQUE,
  importance int NOT NULL CHECK (importance BETWEEN 1 AND 5)
);

CREATE TABLE IF NOT EXISTS signatures (
  id         serial PRIMARY KEY,
  name       text NOT NULL,
  priority   int NOT NULL CHECK (priority BETWEEN 1 AND 5),
  -- [{"field": "process.name", "value": "mimikatz.exe"}, ...]; all must match.
  conditions jsonb NOT NULL CHECK (jsonb_array_length(conditions) > 0)
);

CREATE TABLE IF NOT EXISTS detections (
  id                    serial PRIMARY KEY,
  customer_id           int NOT NULL REFERENCES customers,
  signature_id          int NOT NULL REFERENCES signatures,
  matched_signature_ids int[] NOT NULL,
  -- Snapshot taken at ingestion: later edits to a customer or signature do not reorder old detections.
  customer_importance   int NOT NULL,
  signature_priority    int NOT NULL,
  priority              int NOT NULL,
  payload               jsonb NOT NULL,
  status                text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'IN_PROGRESS', 'CLOSED')),
  assigned_to           int REFERENCES users,
  assigned_at           timestamptz,
  resolution            text,
  closed_at             timestamptz,
  created_at            timestamptz NOT NULL DEFAULT now()
);

-- The database itself guarantees an analyst works on at most one detection at a time.
CREATE UNIQUE INDEX IF NOT EXISTS one_active_detection_per_analyst
  ON detections (assigned_to) WHERE status = 'IN_PROGRESS';

CREATE INDEX IF NOT EXISTS queue_order
  ON detections (priority DESC, created_at) WHERE status = 'OPEN';

-- Incidents we could not turn into a detection, kept for audit and later reprocessing.
CREATE TABLE IF NOT EXISTS unmatched_incidents (
  id          serial PRIMARY KEY,
  reason      text NOT NULL CHECK (reason IN ('UNKNOWN_CUSTOMER', 'NO_SIGNATURE')),
  payload     jsonb NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now()
);
