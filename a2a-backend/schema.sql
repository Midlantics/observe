-- Run this in your Supabase SQL editor, OR let Docker Compose auto-apply it on first start.

CREATE SCHEMA IF NOT EXISTS a2a;

-- Traces: one row per agent run
CREATE TABLE IF NOT EXISTS a2a.traces (
  trace_id     TEXT PRIMARY KEY,
  workspace_id UUID NOT NULL,
  agent_name   TEXT,
  status       TEXT NOT NULL DEFAULT 'running', -- running | success | error
  started_at   TIMESTAMPTZ NOT NULL,
  ended_at     TIMESTAMPTZ,
  duration_ms  INT,
  metadata     JSONB NOT NULL DEFAULT '{}',
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS traces_workspace_started ON a2a.traces (workspace_id, started_at DESC);
CREATE INDEX IF NOT EXISTS traces_workspace_status  ON a2a.traces (workspace_id, status);

-- Spans: OpenTelemetry-compatible, child rows of traces
CREATE TABLE IF NOT EXISTS a2a.spans (
  span_id        TEXT PRIMARY KEY,
  trace_id       TEXT NOT NULL REFERENCES a2a.traces(trace_id) ON DELETE CASCADE,
  parent_span_id TEXT,
  workspace_id   UUID NOT NULL,
  name           TEXT NOT NULL,
  kind           TEXT NOT NULL DEFAULT 'internal', -- internal | llm | tool | agent | handoff
  status         TEXT NOT NULL DEFAULT 'ok',       -- ok | error
  started_at     TIMESTAMPTZ NOT NULL,
  ended_at       TIMESTAMPTZ,
  duration_ms    INT,
  attributes     JSONB NOT NULL DEFAULT '{}',
  events         JSONB NOT NULL DEFAULT '[]',
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS spans_trace     ON a2a.spans (trace_id);
CREATE INDEX IF NOT EXISTS spans_workspace ON a2a.spans (workspace_id, started_at DESC);

-- LLM calls: detailed record of every model invocation
CREATE TABLE IF NOT EXISTS a2a.llm_calls (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  span_id           TEXT REFERENCES a2a.spans(span_id) ON DELETE SET NULL,
  trace_id          TEXT NOT NULL,
  workspace_id      UUID NOT NULL,
  model             TEXT NOT NULL,
  provider          TEXT NOT NULL,
  prompt_tokens     INT,
  completion_tokens INT,
  total_tokens      INT,
  latency_ms        INT,
  cost_usd          NUMERIC(12, 6),
  input             JSONB,
  output            JSONB,
  error             TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS llm_calls_workspace ON a2a.llm_calls (workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS llm_calls_trace     ON a2a.llm_calls (trace_id);
CREATE INDEX IF NOT EXISTS llm_calls_model     ON a2a.llm_calls (workspace_id, model);

-- ── Subscriptions ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS a2a.subscriptions (
  workspace_id           UUID PRIMARY KEY,
  plan                   TEXT NOT NULL DEFAULT 'free',  -- free | policy | approval | firewall | bundle
  status                 TEXT NOT NULL DEFAULT 'active',-- active | canceled | past_due
  stripe_customer_id     TEXT,
  stripe_subscription_id TEXT,
  current_period_end     TIMESTAMPTZ,
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE a2a.subscriptions ENABLE ROW LEVEL SECURITY;

-- ── API Keys ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS a2a.api_keys (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL,
  name         TEXT NOT NULL,
  key_hash     TEXT NOT NULL UNIQUE,   -- SHA-256 of the raw key, never stored in plain text
  revoked      BOOLEAN NOT NULL DEFAULT FALSE,
  last_used_at TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS api_keys_workspace ON a2a.api_keys (workspace_id);
CREATE INDEX IF NOT EXISTS api_keys_hash      ON a2a.api_keys (key_hash) WHERE revoked = false;

ALTER TABLE a2a.api_keys ENABLE ROW LEVEL SECURITY;

-- ── Policy Engine ─────────────────────────────────────────────────────────────

-- Policies: workspace-defined rule sets
CREATE TABLE IF NOT EXISTS a2a.policies (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL,
  name         TEXT NOT NULL,
  description  TEXT NOT NULL DEFAULT '',
  enabled      BOOLEAN NOT NULL DEFAULT TRUE,
  rules        JSONB NOT NULL DEFAULT '[]',
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS policies_workspace ON a2a.policies (workspace_id);

-- Policy events: every evaluation result
CREATE TABLE IF NOT EXISTS a2a.policy_events (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id    UUID NOT NULL,
  trace_id        TEXT,
  agent_name      TEXT,
  action_type     TEXT NOT NULL,
  payload         JSONB NOT NULL DEFAULT '{}',
  verdict         TEXT NOT NULL,   -- allow | flag | block
  triggered_rules JSONB NOT NULL DEFAULT '[]',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS policy_events_workspace ON a2a.policy_events (workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS policy_events_verdict   ON a2a.policy_events (workspace_id, verdict);

-- ── Approval Layer ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS a2a.approval_requests (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id     UUID NOT NULL,
  trace_id         TEXT,
  agent_name       TEXT,
  action_type      TEXT NOT NULL,
  description      TEXT NOT NULL,
  payload          JSONB NOT NULL DEFAULT '{}',
  status           TEXT NOT NULL DEFAULT 'pending', -- pending | approved | rejected | expired
  reviewer_note    TEXT,
  timeout_seconds  INT NOT NULL DEFAULT 3600,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  decided_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS approval_workspace_status ON a2a.approval_requests (workspace_id, status);
CREATE INDEX IF NOT EXISTS approval_workspace_time   ON a2a.approval_requests (workspace_id, created_at DESC);

-- ── Firewall ───────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS a2a.firewall_events (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL,
  trace_id     TEXT,
  agent_name   TEXT,
  context      TEXT NOT NULL DEFAULT 'input', -- input | output | tool_call
  content_hash TEXT,                           -- md5 of scanned content (not stored raw)
  verdict      TEXT NOT NULL,                  -- clean | warn | block
  threats      JSONB NOT NULL DEFAULT '[]',
  metadata     JSONB NOT NULL DEFAULT '{}',
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS firewall_workspace ON a2a.firewall_events (workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS firewall_verdict   ON a2a.firewall_events (workspace_id, verdict);

-- RLS: each workspace_id is the Supabase auth user UUID
ALTER TABLE a2a.traces         ENABLE ROW LEVEL SECURITY;
ALTER TABLE a2a.spans          ENABLE ROW LEVEL SECURITY;
ALTER TABLE a2a.llm_calls      ENABLE ROW LEVEL SECURITY;
ALTER TABLE a2a.policies          ENABLE ROW LEVEL SECURITY;
ALTER TABLE a2a.policy_events     ENABLE ROW LEVEL SECURITY;
ALTER TABLE a2a.approval_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE a2a.firewall_events   ENABLE ROW LEVEL SECURITY;

-- Service role bypasses RLS, which is what the backend uses.
-- Anon/authenticated users are blocked by default (no policies = no access).
