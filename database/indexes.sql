-- ═══════════════════════════════════════════════════════════════════════════════
-- CineOS — Indexes
-- ═══════════════════════════════════════════════════════════════════════════════

-- cineos_core.projects
CREATE INDEX idx_projects_user ON cineos_core.projects(user_id);
CREATE INDEX idx_projects_state ON cineos_core.projects(current_state);
CREATE INDEX idx_projects_updated ON cineos_core.projects(updated_at);
CREATE INDEX idx_projects_priority ON cineos_core.projects(priority, created_at);

-- cineos_core.novels
CREATE INDEX idx_novels_project ON cineos_core.novels(project_id);

-- cineos_core.chapters
CREATE INDEX idx_chapters_novel ON cineos_core.chapters(novel_id);
CREATE INDEX idx_chapters_project ON cineos_core.chapters(project_id);

-- cineos_core.scenes
CREATE INDEX idx_scenes_project ON cineos_core.scenes(project_id);
CREATE INDEX idx_scenes_chapter ON cineos_core.scenes(chapter_id);
CREATE INDEX idx_scenes_state ON cineos_core.scenes(state);
CREATE INDEX idx_scenes_importance ON cineos_core.scenes(importance);
CREATE INDEX idx_scenes_emotion ON cineos_core.scenes(primary_emotion);

-- cineos_core.shots
CREATE INDEX idx_shots_scene ON cineos_core.shots(scene_id);
CREATE INDEX idx_shots_project ON cineos_core.shots(project_id);
CREATE INDEX idx_shots_state ON cineos_core.shots(state);
CREATE INDEX idx_shots_type ON cineos_core.shots(shot_type);

-- cineos_core.characters
CREATE INDEX idx_characters_project ON cineos_core.characters(project_id);
CREATE INDEX idx_characters_state ON cineos_core.characters(state);
CREATE INDEX idx_characters_name ON cineos_core.characters(canonical_name);
CREATE INDEX idx_characters_role ON cineos_core.characters(role);

-- cineos_core.locations
CREATE INDEX idx_locations_project ON cineos_core.locations(project_id);
CREATE INDEX idx_locations_type ON cineos_core.locations(location_type);

-- cineos_core.scene_characters
CREATE INDEX idx_scene_characters_scene ON cineos_core.scene_characters(scene_id);
CREATE INDEX idx_scene_characters_character ON cineos_core.scene_characters(character_id);

-- cineos_core.events
CREATE INDEX idx_events_project ON cineos_core.events(project_id);
CREATE INDEX idx_events_type ON cineos_core.events(event_type);
CREATE INDEX idx_events_severity ON cineos_core.events(severity);
CREATE INDEX idx_events_created ON cineos_core.events(created_at);
CREATE INDEX idx_events_workflow ON cineos_core.events(workflow);

-- cineos_core.state_log
CREATE INDEX idx_state_log_project ON cineos_core.state_log(project_id);
CREATE INDEX idx_state_log_entity ON cineos_core.state_log(entity_type, entity_id);
CREATE INDEX idx_state_log_new_state ON cineos_core.state_log(new_state);
CREATE INDEX idx_state_log_created ON cineos_core.state_log(created_at);

-- cineos_core.versions
CREATE INDEX idx_versions_entity ON cineos_core.versions(entity_type, entity_id);
CREATE INDEX idx_versions_project ON cineos_core.versions(project_id);
CREATE INDEX idx_versions_current ON cineos_core.versions(is_current) WHERE is_current = TRUE;

-- cineos_core.checkpoints
CREATE INDEX idx_checkpoints_project ON cineos_core.checkpoints(project_id);
CREATE INDEX idx_checkpoints_state ON cineos_core.checkpoints(state_at_checkpoint);

-- cineos_memory.prompt_patterns
CREATE INDEX idx_prompt_patterns_type ON cineos_memory.prompt_patterns(pattern_type);
CREATE INDEX idx_prompt_patterns_confidence ON cineos_memory.prompt_patterns(confidence);

-- cineos_memory.backend_performance
CREATE INDEX idx_backend_performance_type ON cineos_memory.backend_performance(backend_type, backend_name);
CREATE INDEX idx_backend_performance_success ON cineos_memory.backend_performance(success);

-- cineos_gen.prompt_versions
CREATE INDEX idx_prompt_versions_shot ON cineos_gen.prompt_versions(shot_id);
CREATE INDEX idx_prompt_versions_project ON cineos_gen.prompt_versions(project_id);
CREATE INDEX idx_prompt_versions_current ON cineos_gen.prompt_versions(is_current) WHERE is_current = TRUE;

-- cineos_quality.reviews
CREATE INDEX idx_reviews_project ON cineos_quality.reviews(project_id);
CREATE INDEX idx_reviews_entity ON cineos_quality.reviews(entity_type, entity_id);
CREATE INDEX idx_reviews_passed ON cineos_quality.reviews(passed);
CREATE INDEX idx_reviews_created ON cineos_quality.reviews(created_at);

-- cineos_quality.repairs
CREATE INDEX idx_repairs_project ON cineos_quality.repairs(project_id);
CREATE INDEX idx_repairs_entity ON cineos_quality.repairs(entity_type, entity_id);
CREATE INDEX idx_repairs_success ON cineos_quality.repairs(success);

-- cineos_quality.checks
CREATE INDEX idx_checks_project ON cineos_quality.checks(project_id);
CREATE INDEX idx_checks_review ON cineos_quality.checks(review_id);
CREATE INDEX idx_checks_entity ON cineos_quality.checks(entity_type, entity_id);
CREATE INDEX idx_checks_name ON cineos_quality.checks(check_name);

-- cineos_exec.workers
CREATE INDEX idx_workers_type ON cineos_exec.workers(worker_type);
CREATE INDEX idx_workers_state ON cineos_exec.workers(state);
CREATE INDEX idx_workers_enabled ON cineos_exec.workers(enabled);

-- cineos_exec.jobs
CREATE INDEX idx_jobs_state ON cineos_exec.jobs(state);
CREATE INDEX idx_jobs_type ON cineos_exec.jobs(job_type);
CREATE INDEX idx_jobs_worker ON cineos_exec.jobs(worker_id);
CREATE INDEX idx_jobs_project ON cineos_exec.jobs(project_id);
CREATE INDEX idx_jobs_priority ON cineos_exec.jobs(priority, created_at);

-- cineos_exec.workflow_executions
CREATE INDEX idx_workflow_executions_project ON cineos_exec.workflow_executions(project_id);
CREATE INDEX idx_workflow_executions_workflow ON cineos_exec.workflow_executions(workflow_name);
CREATE INDEX idx_workflow_executions_state ON cineos_exec.workflow_executions(state);

-- cineos_audit.learning_records
CREATE INDEX idx_learning_project ON cineos_audit.learning_records(project_id);

-- cineos_audit.execution_log
CREATE INDEX idx_execution_log_project ON cineos_audit.execution_log(project_id);
CREATE INDEX idx_execution_log_workflow ON cineos_audit.execution_log(workflow_name);
