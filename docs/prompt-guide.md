# CineOS Prompt Guide

CineOS uses Jinja2 templates for all LLM prompts. Prompts are stored in `prompts/` organized by category. This guide covers template syntax, all prompts, customization, A/B testing, and versioning.

## Template Syntax

Prompts use Jinja2 syntax with these features:

### Variables

```
{{ variable_name }}
{{ scene.full_text }}
{{ character.canonical_name }}
```

### Conditionals

```
{% if scene.has_dialogue %}
This scene contains dialogue between {{ scene.character_names | join(', ') }}.
{% endif %}
```

### Loops

```
{% for shot in scene.shots %}
Shot {{ loop.index }}: {{ shot.shot_type }} - {{ shot.description }}
{% endfor %}
```

### Filters

```
{{ text | truncate(500) }}
{{ characters | selectattr('role', 'equalto', 'protagonist') | list }}
{{ prompt | replace('\n', ' ') }}
```

### Template Inheritance

Some prompts extend base templates:

```
{% extends "base/shot_prompt.j2" %}
{% block shot_details %}
...specific content...
{% endblock %}
```

## Prompt Directory Structure

```
prompts/
├── story/
│   ├── parse_chapter.j2
│   ├── analyze_intelligence.j2
│   └── build_story_bible.j2
├── character/
│   ├── extract_characters.j2
│   ├── build_character_bible.j2
│   └── generate_visual_prompt.j2
├── world/
│   ├── build_world_bible.j2
│   └── generate_world_prompt.j2
├── shot/
│   ├── plan_shots.j2
│   ├── build_image_prompt.j2
│   └── generate_narration.j2
├── quality/
│   ├── review_image.j2
│   ├── review_audio.j2
│   └── review_video.j2
└── repair/
    ├── identify_issues.j2
    └── fix_prompt.j2
```

## All Prompts Explained

### Story Prompts

#### `story/parse_chapter.j2`

**Used by:** Workflow 003 (Story Parser)
**Purpose:** Splits chapter text into scenes with metadata
**Input:** Chapter text, chapter number, novel metadata
**Output:** JSON array of scenes with text, dialogue flags, emotion tags

Key variables:
- `{{ chapter.text }}` — Full chapter text
- `{{ chapter.number }}` — Chapter number
- `{{ novel.language }}` — Detected language
- `{{ novel.genre }}` — Detected genre

#### `story/analyze_intelligence.j2`

**Used by:** Workflow 004 (Story Intelligence)
**Purpose:** Analyzes narrative structure, themes, conflicts, and character arcs
**Input:** Full novel text, chapter summaries
**Output:** JSON with themes, conflicts, character arcs, narrative structure

Key variables:
- `{{ chapters }}` — List of chapter objects
- `{{ novel.title }}` — Novel title
- `{{ novel.word_count }}` — Total word count

#### `story/build_story_bible.j2`

**Used by:** Workflow 005 (Story Bible Builder)
**Purpose:** Creates comprehensive story bible
**Input:** Intelligence analysis, character data, world data
**Output:** Full story bible with genre, themes, tone, pacing, visual style

Key variables:
- `{{ intelligence }}` — Analysis from workflow 004
- `{{ characters }}` — Character profiles
- `{{ world }}` — World data

### Character Prompts

#### `character/extract_characters.j2`

**Used by:** Workflow 006 (Character Engine)
**Purpose:** Extracts and profiles all characters from the text
**Input:** Novel text, scene breakdowns
**Output:** Character profiles with physical descriptions, personality, relationships

Key variables:
- `{{ scenes }}` — All scenes
- `{{ text }}` — Full text
- `{{ existing_characters }}` — Previously identified characters

#### `character/build_character_bible.j2`

**Used by:** Workflow 006 (Character Engine)
**Purpose:** Creates detailed character bible with visual prompts
**Input:** Character profile, story context
**Output:** Full character bible with positive/negative visual prompts

Key variables:
- `{{ character }}` — Character object
- `{{ story_genre }}` — Genre for style matching
- `{{ art_style }}` — Target art style

#### `character/generate_visual_prompt.j2`

**Used by:** Workflow 013 (Prompt Builder)
**Purpose:** Generates image generation prompts for characters
**Input:** Character profile, scene context, style bible
**Output:** Optimized positive and negative prompts

Key variables:
- `{{ character }}` — Character with all physical attributes
- `{{ scene }}` — Current scene context
- `{{ style }}` — Style bible
- `{{ shot_type }}` — Camera framing (close-up, medium, full)

### World Prompts

#### `world/build_world_bible.j2`

**Used by:** Workflow 007 (World Engine)
**Purpose:** Builds world bible with geography, culture, architecture
**Input:** Novel text, extracted locations
**Output:** Comprehensive world bible

Key variables:
- `{{ locations }}` — Extracted locations
- `{{ text }}` — Novel text
- `{{ era }}` — Time period

#### `world/generate_world_prompt.j2`

**Used by:** Workflow 013 (Prompt Builder)
**Purpose:** Generates image prompts for locations
**Input:** Location profile, time of day, weather
**Output:** Location image prompt

Key variables:
- `{{ location }}` — Location with visual attributes
- `{{ time_of_day }}` — Morning, afternoon, evening, night
- `{{ weather }}` — Weather conditions
- `{{ style }}` — Style bible

### Shot Prompts

#### `shot/plan_shots.j2`

**Used by:** Workflow 010 (Shot Planner)
**Purpose:** Plans individual shot details
**Input:** Scene data, character positions, emotional arc
**Output:** Shot list with camera angles, lighting, composition

Key variables:
- `{{ scene }}` — Full scene data
- `{{ characters_in_scene }}` — Characters present
- `{{ emotional_arc }}` — Emotion progression
- `{{ pacing }}` — Desired pacing (fast, normal, slow)

#### `shot/build_image_prompt.j2`

**Used by:** Workflow 013 (Prompt Builder)
**Purpose:** Assembles final image generation prompt from components
**Input:** Character prompts, world prompts, style, shot details
**Output:** Complete positive and negative prompt strings

Key variables:
- `{{ character_prompts }}` — Character visual prompts
- `{{ world_prompt }}` — World/location prompt
- `{{ style_prompt }}` — Style prompt
- `{{ shot }}` — Shot details (camera, lighting, composition)
- `{{ quality_tags }}` — Quality enhancement tags

#### `shot/generate_narration.j2`

**Used by:** Workflow 018 (Voice Engine)
**Purpose:** Generates narration text for TTS
**Input:** Shot narration text, emotional context
**Output:** Cleaned narration text optimized for TTS

Key variables:
- `{{ shot.narration_text }}` — Raw narration
- `{{ shot.narration_emotion }}` — Target emotion
- `{{ language }}` — Target language

### Quality Prompts

#### `quality/review_image.j2`

**Used by:** Workflow 016 (Quality AI)
**Purpose:** Reviews generated images for quality
**Input:** Image, prompt used, character references
**Output:** Quality scores and decision

Key variables:
- `{{ image }}` — Generated image
- `{{ prompt_used }}` — Original prompt
- `{{ character_references }}` — Expected character appearance
- `{{ world_references }}` — Expected world appearance
- `{{ thresholds }}` — Quality thresholds

#### `quality/review_audio.j2`

**Used by:** Workflow 016 (Quality AI)
**Purpose:** Reviews generated audio
**Input:** Audio file, narration text, expected emotion
**Output:** Audio quality scores

Key variables:
- `{{ audio }}` — Generated audio
- `{{ text }}` — Original text
- `{{ expected_emotion }}` — Target emotion
- `{{ expected_duration }}` — Target duration

#### `quality/review_video.j2`

**Used by:** Workflow 023 (Final Review)
**Purpose:** Reviews final video output
**Input:** Video file, project data
**Output:** Overall quality scores

### Repair Prompts

#### `repair/identify_issues.j2`

**Used by:** Workflow 017 (Repair Engine)
**Purpose:** Identifies specific issues in failed quality checks
**Input:** Quality review results, original prompt
**Output:** Prioritized list of issues with repair strategies

Key variables:
- `{{ review }}` — Failed quality review
- `{{ issues }}` — Detected issues
- `{{ original_prompt }}` — Original generation prompt

#### `repair/fix_prompt.j2`

**Used by:** Workflow 017 (Repair Engine)
**Purpose:** Fixes prompt to address quality issues
**Input:** Original prompt, identified issues, character/style context
**Output:** Fixed prompt for regeneration

Key variables:
- `{{ original_prompt }}` — Original prompt
- `{{ issues_to_fix }}` — Issues to address
- `{{ character_context }}` — Character reference data
- `{{ style_context }}` — Style reference data

## Customizing Prompts

### Finding the Right Prompt

1. Identify which workflow handles your task
2. Check the workflow JSON to see which prompt template it calls
3. Edit the corresponding `.j2` file

### Editing a Prompt

1. Open the prompt file in your editor
2. Make changes to the template
3. Save the file
4. No restart required — templates are loaded on each use

### Adding Variables

If you need new data in a prompt:

1. Add the data to the workflow's SQL query or HTTP request
2. Reference it in the template as `{{ new_variable }}`
3. The variable will be available in the template context

### Testing Changes

Test a prompt change with a small project:

```bash
# Send a short story via Telegram
# Monitor the specific workflow execution in n8n
# Check the output quality
```

## A/B Testing Prompts

CineOS supports A/B testing through the prompt versioning system.

### Creating Prompt Variants

1. Duplicate the prompt file with a suffix:

```bash
cp prompts/shot/build_image_prompt.j2 prompts/shot/build_image_prompt_v2.j2
```

2. Edit the new variant
3. In the workflow, route to the new variant for a percentage of jobs

### Tracking Performance

Quality results are stored per prompt version:

```sql
-- Compare prompt performance
SELECT
    prompt_version,
    COUNT(*) as uses,
    AVG(quality_score) as avg_quality,
    AVG(repair_count) as avg_repairs
FROM cineos_gen.prompt_versions
JOIN cineos_gen.images ON prompt_versions.shot_id = images.shot_id
GROUP BY prompt_version
ORDER BY avg_quality DESC;
```

### Prompt Pattern Learning

The Learning Engine (workflow 025) automatically identifies successful prompt patterns:

```sql
-- View learned patterns
SELECT pattern_name, avg_quality_score, usage_count, confidence
FROM cineos_memory.prompt_patterns
ORDER BY avg_quality_score DESC;
```

## Prompt Versioning

Each time a prompt is used, a version record is created in `cineos_gen.prompt_versions`:

```sql
-- View prompt version history for a shot
SELECT version_number, positive_prompt, quality_score, created_at
FROM cineos_gen.prompt_versions
WHERE shot_id = 'your-shot-id'
ORDER BY version_number;
```

This allows:
- Rolling back to a previous prompt if quality degrades
- Comparing different prompt versions
- Learning from successful prompt patterns

## Best Practices

### Prompt Structure

Follow this structure for image generation prompts:

```
[Quality tags], [Subject description], [Character details],
[Scene/environment], [Lighting], [Camera], [Style], [Mood]
```

Example:

```
masterpiece, best quality, highly detailed, cinematic lighting,
a medieval knight standing in a castle courtyard,
armor reflecting golden sunset light, determined expression,
stone walls with ivy, warm evening atmosphere,
wide angle shot, rule of thirds, photorealistic
```

### Negative Prompts

Always include a comprehensive negative prompt:

```
lowres, bad anatomy, bad hands, text, error, missing fingers,
extra digit, fewer digits, cropped, worst quality, low quality,
normal quality, jpeg artifacts, signature, watermark, username, blurry,
deformed, disfigured, mutation, mutated
```

### Language-Specific Prompts

For non-English novels, adapt prompts to the target language:

```jinja2
{% if language == 'ar' %}
{# Arabic-specific TTS settings #}
voice: "ar-SA-ZariyahNeural"
{% elif language == 'en' %}
voice: "en-US-AriaNeural"
{% endif %}
```

### Performance Tips

- Keep prompts concise — shorter prompts generate faster
- Use established quality tags rather than natural language
- Include specific camera/composition terms for better results
- Reference character descriptions from the database for consistency
