-- ═══════════════════════════════════════════════════════════════════════════════
-- CineOS — Observability Tables
-- Metrics collection and distributed tracing for the audit schema.
-- ═══════════════════════════════════════════════════════════════════════════════

-- ── Metrics ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS cineos_audit.metrics (
    metric_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    metric_name     VARCHAR(200) NOT NULL,
    metric_value    DOUBLE PRECISION NOT NULL,
    labels          JSONB DEFAULT '{}',
    unit            VARCHAR(50) DEFAULT '',
    collected_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_metrics_name ON cineos_audit.metrics(metric_name);
CREATE INDEX IF NOT EXISTS idx_metrics_collected_at ON cineos_audit.metrics(collected_at);
CREATE INDEX IF NOT EXISTS idx_metrics_name_collected ON cineos_audit.metrics(metric_name, collected_at);
CREATE INDEX IF NOT EXISTS idx_metrics_labels ON cineos_audit.metrics USING GIN (labels);

-- ── Traces ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS cineos_audit.traces (
    trace_id        UUID NOT NULL,
    span_id         VARCHAR(32) NOT NULL,
    parent_span_id  VARCHAR(32),
    operation_name  VARCHAR(300) NOT NULL,
    start_time      TIMESTAMPTZ NOT NULL,
    end_time        TIMESTAMPTZ,
    duration_ms     DOUBLE PRECISION DEFAULT 0,
    status          VARCHAR(50) DEFAULT 'ok',
    attributes      JSONB DEFAULT '{}',
    PRIMARY KEY (trace_id, span_id)
);

CREATE INDEX IF NOT EXISTS idx_traces_trace_id ON cineos_audit.traces(trace_id);
CREATE INDEX IF NOT EXISTS idx_traces_operation ON cineos_audit.traces(operation_name);
CREATE INDEX IF NOT EXISTS idx_traces_start_time ON cineos_audit.traces(start_time);
CREATE INDEX IF NOT EXISTS idx_traces_status ON cineos_audit.traces(status);
CREATE INDEX IF NOT EXISTS idx_traces_parent ON cineos_audit.traces(parent_span_id);
CREATE INDEX IF NOT EXISTS idx_traces_attributes ON cineos_audit.traces USING GIN (attributes);
CREATE INDEX IF NOT EXISTS idx_traces_trace_start ON cineos_audit.traces(trace_id, start_time);
