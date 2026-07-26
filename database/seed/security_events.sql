-- ═══════════════════════════════════════════════════════════════════════════════
-- CineOS — Security Events Table (cineos_audit schema)
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS cineos_audit.security_events (
    event_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type      VARCHAR(100) NOT NULL,
    severity        VARCHAR(20)  NOT NULL DEFAULT 'info',
    source_ip       INET,
    user_agent      TEXT,
    request_id      VARCHAR(100),
    api_key_id      VARCHAR(100),
    details         JSONB,
    created_at      TIMESTAMPTZ  DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════════════════════
-- Indexes for common query patterns
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_security_events_type
    ON cineos_audit.security_events (event_type);

CREATE INDEX IF NOT EXISTS idx_security_events_severity
    ON cineos_audit.security_events (severity);

CREATE INDEX IF NOT EXISTS idx_security_events_created_at
    ON cineos_audit.security_events (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_security_events_source_ip
    ON cineos_audit.security_events (source_ip);

CREATE INDEX IF NOT EXISTS idx_security_events_request_id
    ON cineos_audit.security_events (request_id);

CREATE INDEX IF NOT EXISTS idx_security_events_api_key_id
    ON cineos_audit.security_events (api_key_id);

CREATE INDEX IF NOT EXISTS idx_security_events_composite
    ON cineos_audit.security_events (event_type, severity, created_at DESC);

-- Partial index for high-severity events (fast alerting queries)
CREATE INDEX IF NOT EXISTS idx_security_events_high_severity
    ON cineos_audit.security_events (created_at DESC)
    WHERE severity IN ('error', 'critical');

-- ═══════════════════════════════════════════════════════════════════════════════
-- Cleanup: auto-delete events older than 90 days (optional)
-- ═══════════════════════════════════════════════════════════════════════════════

-- CREATE OR REPLACE FUNCTION cineos_audit.purge_old_security_events()
-- RETURNS void AS $$
-- BEGIN
--     DELETE FROM cineos_audit.security_events
--     WHERE created_at < NOW() - INTERVAL '90 days';
-- END;
-- $$ LANGUAGE plpgsql;
