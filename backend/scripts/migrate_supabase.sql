-- OrgMind Supabase migration
-- Run once in Supabase SQL editor or via psql

-- decisions table
CREATE TABLE IF NOT EXISTS decisions (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    rationale   TEXT,
    date        TEXT,
    source_type TEXT,
    source_url  TEXT,
    confidence  FLOAT DEFAULT 0,
    stale       BOOLEAN DEFAULT FALSE,
    review_status TEXT DEFAULT 'ok',
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- review_queue table
CREATE TABLE IF NOT EXISTS review_queue (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id  TEXT NOT NULL,
    decision_title TEXT,
    flags        TEXT[] NOT NULL DEFAULT '{}',
    status       TEXT NOT NULL DEFAULT 'pending',
    note         TEXT,
    flagged_at   TIMESTAMPTZ DEFAULT now(),
    updated_at   TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_decisions_source_type ON decisions(source_type);
CREATE INDEX IF NOT EXISTS idx_decisions_stale ON decisions(stale);
CREATE INDEX IF NOT EXISTS idx_decisions_review_status ON decisions(review_status);
CREATE INDEX IF NOT EXISTS idx_review_queue_decision_id ON review_queue(decision_id);
CREATE INDEX IF NOT EXISTS idx_review_queue_status ON review_queue(status);
CREATE INDEX IF NOT EXISTS idx_review_queue_flagged_at ON review_queue(flagged_at DESC);
