-- OrgMind initial Supabase schema
-- Run once against your Supabase project via the SQL editor or psql

-- ── decisions ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS decisions (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    summary       TEXT,
    rationale     TEXT,
    date          TEXT,
    confidence    FLOAT,
    source_type   TEXT,
    source_url    TEXT,
    authors       TEXT[],
    entities      TEXT[],
    tags          TEXT[],
    stale         BOOLEAN DEFAULT FALSE,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS decisions_stale_idx    ON decisions (stale);
CREATE INDEX IF NOT EXISTS decisions_date_idx     ON decisions (date DESC);
CREATE INDEX IF NOT EXISTS decisions_source_idx   ON decisions (source_type);

-- ── review_queue ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS review_queue (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id   TEXT REFERENCES decisions(id) ON DELETE CASCADE,
    flags         TEXT[],
    status        TEXT DEFAULT 'pending',   -- pending | approve | reject | escalate
    note          TEXT,
    flagged_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS review_queue_status_idx ON review_queue (status);
CREATE INDEX IF NOT EXISTS review_queue_date_idx   ON review_queue (flagged_at DESC);

-- ── auto-update updated_at ────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS decisions_updated_at ON decisions;
CREATE TRIGGER decisions_updated_at
    BEFORE UPDATE ON decisions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS review_queue_updated_at ON review_queue;
CREATE TRIGGER review_queue_updated_at
    BEFORE UPDATE ON review_queue
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
