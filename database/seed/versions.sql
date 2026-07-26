-- ═══════════════════════════════════════════════════════════════════════════════
-- CineOS — Component Version Tracking Table
-- Stores version history for all system components.
-- Used by src/versioning/tracker.py
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS cineos_config.versions (
    version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    component VARCHAR(50) NOT NULL,
    version_number VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR(200),
    reason TEXT,
    compatibility JSONB,
    metadata JSONB,
    UNIQUE(component, version_number)
);

CREATE INDEX IF NOT EXISTS idx_versions_component ON cineos_config.versions(component);
CREATE INDEX IF NOT EXISTS idx_versions_created ON cineos_config.versions(created_at);

-- Seed initial versions for each component
INSERT INTO cineos_config.versions (component, version_number, created_by, reason, compatibility, metadata)
VALUES
    ('workflow',  '1.0.0', 'system', 'Initial release — 25 n8n workflows',
        '{"requires_database": ">=1.0.0", "requires_worker": ">=1.0.0"}'::jsonb,
        '{"description": "All 25 production workflows"}'::jsonb),
    ('prompt',    '1.0.0', 'system', 'Initial release — 16 Jinja2 templates',
        '{"requires_database": ">=1.0.0"}'::jsonb,
        '{"description": "Story, character, world, shot, quality, repair prompts"}'::jsonb),
    ('database',  '1.0.0', 'system', 'Initial schema — 7 schemas, all tables',
        '{}'::jsonb,
        '{"schemas": ["cineos_core", "cineos_memory", "cineos_gen", "cineos_quality", "cineos_exec", "cineos_audit", "cineos_config"]}'::jsonb),
    ('worker',    '1.0.0', 'system', 'Initial release — 6 worker types',
        '{"requires_database": ">=1.0.0"}'::jsonb,
        '{"workers": ["supervisor", "image", "quality", "render", "voice", "animation"]}'::jsonb),
    ('api',       '1.0.0', 'system', 'Initial REST API',
        '{"requires_database": ">=1.0.0", "requires_worker": ">=1.0.0"}'::jsonb,
        '{"spec": "openapi.yaml", "auth": "bearer"}'::jsonb),
    ('config',    '1.0.0', 'system', 'Default configuration files',
        '{}'::jsonb,
        '{"files": ["settings.yaml", "models.yaml", "workers.yaml", "quality.yaml", "telegram.yaml"]}'::jsonb),
    ('model',     '1.0.0', 'system', 'Default AI model configuration',
        '{"requires_worker": ">=1.0.0"}'::jsonb,
        '{"llm": "llama3.2", "image": "flux.1-dev", "voice": "kokoro", "animation": "liveportrait"}'::jsonb)
ON CONFLICT (component, version_number) DO NOTHING;
