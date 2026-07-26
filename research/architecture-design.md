# System Architecture Design

## Overview
A fully automated pipeline that converts novels sent through Telegram into professional cinematic anime/manhwa style videos. The system remains completely free using only open-source technologies.

## Core Architecture Principles
1. **Modularity:** Each component is replaceable
2. **Free Only:** No paid APIs or services
3. **Quality First:** Never sacrifice quality for speed
4. **Character Consistency:** Immutable character identities
5. **Evidence-Based:** All decisions backed by novel evidence

## System Components

### 1. Telegram Interface
```
User → Telegram Bot → Novel Parser → Pipeline Orchestrator
```
- **Technology:** python-telegram-bot v22.8
- **Responsibilities:**
  - Receive novels from users
  - Send progress updates
  - Deliver final video
  - Handle user feedback

### 2. Novel Analysis Engine
```
Raw Novel → Chapter Splitter → Scene Segmenter → Story Analyzer
```
- **Technology:** Ollama + Llama 3.1 8B
- **Components:**
  - **Chapter Splitter:** Divide novel into chapters
  - **Scene Segmenter:** Split chapters into narrative scenes
  - **Story Analyzer:** Extract events, emotions, dialogue

### 3. Character Research Engine
```
Characters → Evidence Collector → DNA Builder → Character Locker
```
- **Technology:** Custom Python + SQLite
- **Components:**
  - **Evidence Collector:** Gather all character appearances
  - **DNA Builder:** Create immutable Character DNA
  - **Character Locker:** Prevent identity drift

### 4. World Engine
```
World Data → World Builder → World Bible → World Locker
```
- **Technology:** Custom Python + SQLite
- **Components:**
  - **World Builder:** Construct geography, culture, history
  - **World Bible:** Store world rules
  - **World Locker:** Prevent world inconsistencies

### 5. Visual Production Engine
```
Scene Graph → Prompt Compiler → Image Generator → Visual Critic
```
- **Technology:** Stable Diffusion XL + Animagine XL 4.0
- **Components:**
  - **Prompt Compiler:** Build prompts from all data sources
  - **Image Generator:** Generate multiple candidates
  - **Visual Critic:** Evaluate and select best result

### 6. Audio Production Engine
```
Narration Script → TTS Engine → Audio Editor → Sync Manager
```
- **Technology:** Kokoro-82M + MoviePy
- **Components:**
  - **TTS Engine:** Generate natural narration
  - **Audio Editor:** Add pauses, emotions
  - **Sync Manager:** Synchronize audio with visuals

### 7. Video Assembly Engine
```
Images + Audio → Video Composer → Effects Engine → Final Output
```
- **Technology:** MoviePy 2.0 + FFmpeg
- **Components:**
  - **Video Composer:** Assemble clips
  - **Effects Engine:** Add transitions, effects
  - **Final Output:** Render final video

### 8. Quality Control System
```
All Outputs → Quality Judge → Improvement Engine → Final Approval
```
- **Technology:** Custom Python + CLIP + InsightFace
- **Components:**
  - **Quality Judge:** Score all outputs
  - **Improvement Engine:** Regenerate if needed
  - **Final Approval:** Ensure constitution compliance

## Data Flow

```
1. User sends novel via Telegram
2. Novel is parsed and segmented
3. Characters are researched and locked
4. World is built and locked
5. Scenes are created with importance scores
6. For each scene:
   a. Prompts are compiled
   b. Images are generated (multiple candidates)
   c. Images are critiqued and selected
   d. Audio is generated
   e. Scene is assembled
7. All scenes are combined
8. Final quality check
9. Video delivered to user
```

## Storage Structure

```
project/
├── database/
│   ├── characters.db
│   ├── world.db
│   └── scenes.db
├── reference/
│   ├── character_references/
│   ├── world_references/
│   └── style_references/
├── generated/
│   ├── images/
│   ├── audio/
│   └── video/
└── checkpoints/
    └── progress.json
```

## Error Handling

### Failure Recovery
- **Checkpoint System:** Save progress every N steps
- **Retry Logic:** Automatic retry with backoff
- **Graceful Degradation:** Continue with reduced quality if needed
- **Logging:** Comprehensive logging for debugging

### Quality Thresholds
- **Character Consistency:** >90% similarity score
- **Visual Quality:** >8/10 CLIP score
- **Audio Quality:** >8/10 naturalness score
- **Overall Quality:** >8/10 final score

## Scalability Considerations

### Long Novel Strategy
- **Chunking:** Process chapters independently
- **Memory Management:** Unload completed chapters
- **Progress Tracking:** Track completion percentage
- **Resume Capability:** Continue from last checkpoint

### Resource Management
- **GPU Memory:** Process scenes sequentially
- **Storage:** Clean temporary files after completion
- **CPU:** Use async where possible

## Security Considerations

### Data Protection
- **Local Processing:** All data stays on user's machine
- **No Cloud Dependencies:** No data sent to external services
- **Input Validation:** Sanitize all user inputs
- **Prompt Injection:** Defend against novel-based attacks

### System Security
- **No Execution:** Never execute code from novels
- **File Access:** Restrict to project directories
- **API Keys:** Not needed (all free)

## Implementation Phases

### Phase 1: Core Infrastructure
- Telegram bot setup
- Database schema
- Basic pipeline

### Phase 2: Character System
- Character research engine
- Character DNA system
- Character locking

### Phase 3: Visual System
- Stable Diffusion integration
- Prompt compiler
- Visual critic

### Phase 4: Audio System
- TTS integration
- Audio editing
- Synchronization

### Phase 5: Video Assembly
- Video composer
- Effects engine
- Final output

### Phase 6: Quality Control
- Quality metrics
- Improvement engine
- Final jury

## Conclusion

This architecture provides a complete, free, and modular system for converting novels into cinematic videos while maintaining character consistency, world consistency, and high quality. All components are open-source and can be replaced independently.