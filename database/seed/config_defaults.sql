-- ═══════════════════════════════════════════════════════════════════════════════
-- CineOS — Default Configuration Values
-- ═══════════════════════════════════════════════════════════════════════════════

INSERT INTO cineos_config.system_config (config_key, config_value, description, category, data_type) VALUES
-- Quality
('quality.min_image_quality', '0.60', 'Minimum image quality score to pass review', 'quality', 'number'),
('quality.min_character_consistency', '0.70', 'Minimum character consistency score', 'quality', 'number'),
('quality.min_world_consistency', '0.60', 'Minimum world consistency score', 'quality', 'number'),
('quality.min_composition', '0.50', 'Minimum composition score', 'quality', 'number'),
('quality.min_prompt_alignment', '0.60', 'Minimum prompt alignment score', 'quality', 'number'),
('quality.min_audio_quality', '0.50', 'Minimum audio quality score', 'quality', 'number'),
('quality.min_naturalness', '0.50', 'Minimum TTS naturalness score', 'quality', 'number'),
('quality.min_emotion_match', '0.40', 'Minimum emotion match score', 'quality', 'number'),
('quality.min_duration_fit', '0.60', 'Minimum audio-video duration fit', 'quality', 'number'),
('quality.min_video_quality', '0.60', 'Minimum video clip quality', 'quality', 'number'),
('quality.min_audio_video_sync', '0.70', 'Minimum audio-video sync score', 'quality', 'number'),
('quality.min_overall_quality', '0.60', 'Minimum overall project quality', 'quality', 'number'),
('quality.max_repair_attempts', '3', 'Maximum repair attempts per item', 'quality', 'number'),
('quality.repair_escalation_threshold', '0.30', 'Score below which repair is escalated', 'quality', 'number'),
('quality.hard_failure_threshold', '0.20', 'Score below which item is rejected', 'quality', 'number'),
('quality.auto_approve_threshold', '0.85', 'Score above which auto-approve', 'quality', 'number'),
-- Generation
('generation.default_image_backends', '["pollinations","hf_inference","colab_comfyui"]', 'Image backend priority order — cloud only, no local GPU', 'generation', 'array'),
('generation.default_tts_backends', '["edge_tts","colab_kokoro"]', 'TTS backend priority order — cloud only', 'generation', 'array'),
('generation.candidates_per_shot', '2', 'Number of image variants per shot', 'generation', 'number'),
('generation.image_concurrency', '1', 'Concurrent image generation tasks', 'generation', 'number'),
('generation.audio_concurrency', '2', 'Concurrent audio generation tasks', 'generation', 'number'),
('generation.max_seed_retries', '3', 'Max retries with different seeds', 'generation', 'number'),
-- Video
('video.default_fps', '24', 'Default video frames per second', 'video', 'number'),
('video.default_resolution_width', '1920', 'Default video width', 'video', 'number'),
('video.default_resolution_height', '1080', 'Default video height', 'video', 'number'),
('video.default_codec', 'libx264', 'Default video codec', 'video', 'string'),
('video.default_audio_codec', 'aac', 'Default audio codec', 'video', 'string'),
('video.default_crf', '18', 'Default constant rate factor (lower = better)', 'video', 'number'),
('video.default_preset', 'medium', 'Default encoding preset', 'video', 'string'),
('video.max_telegram_file_size_mb', '50', 'Maximum file size for Telegram bot upload', 'video', 'number'),
-- Shot Planning
('planning.shots_per_scene_critical', '10', 'Target shots for critical scenes', 'planning', 'number'),
('planning.shots_per_scene_high', '7', 'Target shots for high importance scenes', 'planning', 'number'),
('planning.shots_per_scene_normal', '5', 'Target shots for normal scenes', 'planning', 'number'),
('planning.shots_per_scene_low', '3', 'Target shots for low importance scenes', 'planning', 'number'),
('planning.max_total_shots', '1000', 'Maximum total shots per project', 'planning', 'number'),
('planning.max_video_duration_seconds', '3600', 'Maximum video duration in seconds', 'planning', 'number'),
('planning.max_shot_duration_seconds', '30', 'Maximum single shot duration', 'planning', 'number'),
('planning.min_shot_duration_seconds', '3', 'Minimum single shot duration', 'planning', 'number'),
-- Limits
('limits.max_novel_words', '500000', 'Maximum novel word count', 'limits', 'number'),
('limits.max_scenes', '200', 'Maximum scenes per project', 'limits', 'number'),
('limits.max_project_duration_hours', '72', 'Maximum project processing time', 'limits', 'number'),
('limits.min_novel_words', '50', 'Minimum novel word count', 'limits', 'number'),
-- Telegram
('telegram.progress_update_interval_seconds', '30', 'Progress update throttle interval', 'telegram', 'number'),
('telegram.max_message_length', '4096', 'Maximum Telegram message length', 'telegram', 'number'),
('telegram.allowed_user_ids', '[]', 'Telegram user IDs allowed to use bot', 'telegram', 'array'),
-- Worker
('worker.heartbeat_timeout_seconds', '90', 'Seconds before worker declared offline', 'worker', 'number'),
('worker.health_check_interval_seconds', '60', 'Worker health check interval', 'worker', 'number'),
('worker.max_task_timeout_seconds', '300', 'Default maximum task timeout', 'worker', 'number'),
('worker.retry_backoff_base_ms', '1000', 'Base delay for exponential backoff', 'worker', 'number'),
('worker.retry_backoff_max_ms', '300000', 'Maximum backoff delay', 'worker', 'number')
ON CONFLICT (config_key) DO NOTHING;
