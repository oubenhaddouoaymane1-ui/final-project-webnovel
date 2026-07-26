-- ═══════════════════════════════════════════════════════════════════════════════
-- CineOS — Constraints (added after table creation)
-- ═══════════════════════════════════════════════════════════════════════════════

-- FK from scenes to locations (added after locations table exists)
ALTER TABLE cineos_core.scenes ADD CONSTRAINT fk_scenes_location
    FOREIGN KEY (location_id) REFERENCES cineos_core.locations(location_id);
