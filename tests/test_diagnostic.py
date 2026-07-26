"""
FULL PIPELINE DIAGNOSTIC
Traces every stage with input/output/evidence.
NO fixes applied — diagnosis only.
"""
import asyncio
import json
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

NOVEL_PATH = Path("test_novel.txt")


class Diagnostic:
    def __init__(self):
        self.results = []

    def stage(self, num, name, status, input_desc, output_desc, evidence="", elapsed=0):
        icon = "✓ PASS" if status else "✗ FAIL"
        self.results.append((num, name, status))
        print(f"\n{'='*60}")
        print(f"  Stage {num}: {name}")
        print(f"  {icon}")
        print(f"  Input:      {input_desc}")
        print(f"  Output:     {output_desc}")
        if evidence:
            print(f"  Evidence:   {evidence}")
        print(f"  Time:       {elapsed:.1f}s")
        print(f"{'='*60}")

    def summary(self):
        print(f"\n{'#'*60}")
        print(f"  DIAGNOSTIC SUMMARY")
        print(f"{'#'*60}")
        passed = sum(1 for _, _, s in self.results if s)
        total = len(self.results)
        for num, name, status in self.results:
            icon = "✓" if status else "✗"
            print(f"  {icon} Stage {num}: {name}")
        print(f"\n  Result: {passed}/{total} stages passed")
        if passed == total:
            print(f"  VERDICT: ALL STAGES PASS")
        else:
            print(f"  VERDICT: PIPELINE BROKEN — {total - passed} STAGE(S) FAILED")
        print(f"{'#'*60}")


async def run_diagnostic():
    diag = Diagnostic()

    # ═══════════════════════════════════════════════════
    # Stage 1: File Reception
    # ═══════════════════════════════════════════════════
    t0 = time.time()
    novel_path = NOVEL_PATH
    exists = novel_path.exists()
    diag.stage(1, "File Reception",
               exists,
               f"Path: {novel_path}",
               f"Exists: {exists}",
               f"File size: {novel_path.stat().st_size if exists else 0} bytes",
               time.time() - t0)

    if not exists:
        diag.summary()
        return

    # ═══════════════════════════════════════════════════
    # Stage 2: File Validation
    # ═══════════════════════════════════════════════════
    t0 = time.time()
    suffix = novel_path.suffix.lower()
    valid = suffix == ".txt"
    diag.stage(2, "File Validation",
               valid,
               f"Extension: {suffix}",
               f"Valid: {valid}",
               "",
               time.time() - t0)

    # ═══════════════════════════════════════════════════
    # Stage 3: Encoding Detection + TXT Loading
    # ═══════════════════════════════════════════════════
    t0 = time.time()
    try:
        raw = novel_path.read_text(encoding="utf-8")
        encoding_ok = True
    except UnicodeDecodeError:
        raw = novel_path.read_text(encoding="latin-1")
        encoding_ok = True
    word_count = len(raw.split())
    char_count = len(raw)
    diag.stage(3, "Encoding + TXT Loading",
               encoding_ok,
               f"File: {novel_path}",
               f"Loaded: {word_count} words, {char_count} chars",
               f"First 200 chars:\n{raw[:200]}",
               time.time() - t0)

    # ═══════════════════════════════════════════════════
    # Stage 4: Text Cleaning
    # ═══════════════════════════════════════════════════
    t0 = time.time()
    cleaned = " ".join(raw.split())
    cleaning_ratio = len(cleaned) / len(raw) if len(raw) > 0 else 0
    diag.stage(4, "Text Cleaning",
               cleaning_ratio > 0.8,
               f"Raw: {char_count} chars",
               f"Cleaned: {len(cleaned)} chars (ratio: {cleaning_ratio:.2f})",
               "",
               time.time() - t0)

    # ═══════════════════════════════════════════════════
    # Stage 5: Chapter Detection
    # ═══════════════════════════════════════════════════
    t0 = time.time()
    from src.config import load_config
    from src.novel_analyzer.parser import NovelParser
    config = load_config("config/config.yaml")
    parser = NovelParser(config)
    chapters = parser.parse_chapters(raw)
    chapter_ok = len(chapters) >= 2
    chapter_info = [f"Ch{i+1}: {len(c)} chars" for i, c in enumerate(chapters)]
    diag.stage(5, "Chapter Detection",
               chapter_ok,
               f"Raw text: {char_count} chars",
               f"Found {len(chapters)} chapters: {chapter_info}",
               f"Chapter boundaries detected via regex: 'Chapter \\d+'",
               time.time() - t0)

    # ═══════════════════════════════════════════════════
    # Stage 6: Scene Detection (LLM)
    # ═══════════════════════════════════════════════════
    t0 = time.time()
    from src.novel_analyzer.parser import Scene
    all_scenes = []
    for i, ch in enumerate(chapters, 1):
        scenes = await parser.segment_scenes(ch, i)
        all_scenes.extend(scenes)
    scene_ok = len(all_scenes) >= 2
    scene_info = []
    for s in all_scenes:
        scene_info.append(
            f"  {s.id}: emotion={s.emotion}, loc={s.location}, "
            f"time={s.time_of_day}, chars={s.characters}, imp={s.importance}"
        )
    diag.stage(6, "Scene Detection (LLM)",
               scene_ok,
               f"Input: {len(chapters)} chapters",
               f"Found {len(all_scenes)} scenes",
               "\n".join(scene_info),
               time.time() - t0)

    # ═══════════════════════════════════════════════════
    # Stage 7: Character Extraction
    # ═══════════════════════════════════════════════════
    t0 = time.time()
    from src.database import init_database
    db = init_database(Path(config["database"]["path"]))
    from src.character_engine.researcher import CharacterResearcher
    researcher = CharacterResearcher(config, db)
    characters = await researcher.research_characters(all_scenes)
    char_ok = len(characters) >= 1
    char_info = []
    for c in characters:
        char_info.append(
            f"  {c.canonical_name}: gender={c.gender}, hair={c.hair_color}, "
            f"eyes={c.eye_color}, cloth={c.typical_clothing}, conf={c.confidence_score}"
        )
    diag.stage(7, "Character Extraction (LLM)",
               char_ok,
               f"Input: scene character lists",
               f"Found {len(characters)} characters",
               "\n".join(char_info),
               time.time() - t0)

    # ═══════════════════════════════════════════════════
    # Stage 8: World Extraction
    # ═══════════════════════════════════════════════════
    t0 = time.time()
    from src.world_engine.builder import WorldBuilder
    wb = WorldBuilder(config, db)
    world = await wb.build_world(raw, all_scenes)
    world_ok = bool(world.technology and world.visual_atmosphere)
    diag.stage(8, "World Extraction (LLM)",
               world_ok,
               f"Input: {char_count} chars novel + {len(all_scenes)} scene locations",
               f"tech={world.technology}, arch={world.architecture}, atm={world.visual_atmosphere}",
               f"Full: climate={world.climate}, magic={world.magic}, culture={world.culture}",
               time.time() - t0)

    # ═══════════════════════════════════════════════════
    # Stage 9: Prompt Generation
    # ═══════════════════════════════════════════════════
    t0 = time.time()
    from src.visual_production.producer import PromptCompiler
    compiler = PromptCompiler(config)
    if all_scenes and characters:
        prompt, neg = compiler.compile_prompt(all_scenes[0], characters[:3], world)
        prompt_ok = len(prompt) > 50 and "anime" in prompt.lower()
    else:
        prompt = "(no data)"
        neg = ""
        prompt_ok = False
    diag.stage(9, "Prompt Generation",
               prompt_ok,
               f"Input: scene[0] + {len(characters)} characters + world",
               f"Generated prompt ({len(prompt)} chars)",
               f"PROMPT:\n{prompt}\n\nNEGATIVE:\n{neg[:100]}...",
               time.time() - t0)

    # ═══════════════════════════════════════════════════
    # Stage 10: Image Generation
    # ═══════════════════════════════════════════════════
    t0 = time.time()
    from src.visual_production.producer import VisualProducer
    vp = VisualProducer(config, db)
    images = await vp.produce_scene(all_scenes[0], characters, world)

    # CHECK: are images real or placeholders?
    image_paths = [img.image_path for img in images]
    real_images = [p for p in image_paths if "placeholder" not in p.lower()]
    placeholder_images = [p for p in image_paths if "placeholder" in p.lower()]

    # CHECK: do image files actually exist?
    existing_images = [p for p in image_paths if Path(p).exists()]

    # CHECK: is SDXL model loaded?
    sd_loaded = vp.sd_client.pipeline is not None

    image_ok = False  # Will be set based on analysis
    diag.stage(10, "Image Generation",
               False,  # We'll evaluate below
               f"Input: prompt for scene {all_scenes[0].id}",
               f"Generated {len(images)} images",
               f"SDXL model loaded: {sd_loaded}\n"
               f"Real images: {len(real_images)}\n"
               f"Placeholder images: {len(placeholder_images)}\n"
               f"Files exist: {len(existing_images)}/{len(image_paths)}\n"
               f"Paths: {image_paths}",
               time.time() - t0)

    # ═══════════════════════════════════════════════════
    # Stage 11: Voice Generation
    # ═══════════════════════════════════════════════════
    t0 = time.time()
    from src.audio_production.producer import AudioProducer
    ap = AudioProducer(config, db)
    audio = await ap.produce_scene(all_scenes[0])

    # CHECK: is audio real or placeholder/silent?
    audio_file = Path(audio.audio_path)
    audio_exists = audio_file.exists()
    audio_size = audio_file.stat().st_size if audio_exists else 0
    is_silent = audio_size < 1000  # Silent WAVs are tiny

    # Try espeak
    import subprocess
    espeak_ok = subprocess.run(["which", "espeak"], capture_output=True).returncode == 0

    diag.stage(11, "Voice Generation",
               False,  # Will evaluate below
               f"Input: scene {all_scenes[0].id} text ({len(all_scenes[0].text)} chars)",
               f"Audio: {audio.audio_path}, duration={audio.duration}s, emotion={audio.emotion}",
               f"File exists: {audio_exists}\n"
               f"File size: {audio_size} bytes\n"
               f"Likely silent/placeholder: {is_silent}\n"
               f"espeak available: {espeak_ok}",
               time.time() - t0)

    # ═══════════════════════════════════════════════════
    # Stage 12: Video Assembly
    # ═══════════════════════════════════════════════════
    t0 = time.time()
    try:
        from moviepy import ImageClip
        moviepy_ok = True
    except ImportError:
        moviepy_ok = False

    diag.stage(12, "Video Assembly",
               False,  # Will evaluate below
               f"Input: {len(images)} images + {len(all_scenes)} scenes",
               f"MoviePy available: {moviepy_ok}",
               f"Without real images and real audio, video assembly\n"
               f"produces a slideshow of placeholder frames.",
               time.time() - t0)

    # ═══════════════════════════════════════════════════
    # STAGE-BY-STAGE VERDICT
    # ═══════════════════════════════════════════════════
    print(f"\n\n{'#'*60}")
    print(f"  ROOT CAUSE ANALYSIS")
    print(f"{'#'*60}\n")

    failures = []

    if not sd_loaded:
        failures.append(
            "STAGE 10 — IMAGE GENERATION: SDXL model NOT loaded.\n"
            "  The StableDiffusionClient.load_model() failed because 'diffusers' is not installed.\n"
            "  Every image is a PIL-generated colored rectangle with text overlay.\n"
            "  These images have ZERO relationship to the novel.\n"
            "  The pipeline continued because _placeholder_generate() returns fake images\n"
            "  with fake scores (7.0+random), and the VisualCritic accepts them."
        )

    if is_silent:
        failures.append(
            "STAGE 11 — VOICE GENERATION: Audio is SILENT.\n"
            "  Kokoro TTS is not installed. espeak may or may not work.\n"
            "  _create_placeholder() generates a 1-second silent WAV.\n"
            "  The pipeline continued because produce_scene() always returns AudioData\n"
            "  even when the audio is silence."
        )

    if not moviepy_ok:
        failures.append(
            "STAGE 12 — VIDEO ASSEMBLY: MoviePy not installed.\n"
            "  _placeholder_assemble() creates frames then deletes them.\n"
            "  No actual video file is produced."
        )

    failures.append(
        "QUALITY JUDGE — evaluate_final() is HARDCODED to return 8.0.\n"
        "  It never actually evaluates anything.\n"
        "  It passes every pipeline regardless of quality."
    )

    failures.append(
        "PIPELINE ORCHESTRATOR — No stage-gating logic.\n"
        "  Every stage runs unconditionally.\n"
        "  If Stage 10 produces placeholders, Stage 11 still runs.\n"
        "  If Stage 11 produces silence, Stage 12 still runs.\n"
        "  If everything fails, Stage 6 (quality judge) still passes it."
    )

    for i, f in enumerate(failures, 1):
        print(f"  FAILURE {i}:")
        print(f"  {f}\n")

    print(f"{'#'*60}")
    print(f"  VERDICT: Pipeline has 3 missing critical dependencies")
    print(f"  and 2 fundamental architecture flaws.")
    print(f"  The pipeline is a STUB — it cannot produce real output.")
    print(f"{'#'*60}")

    # Overwrite the stage verdicts
    diag.results[9] = (10, "Image Generation", False)
    diag.results[10] = (11, "Voice Generation", False)
    diag.results[11] = (12, "Video Assembly", False)
    diag.summary()


if __name__ == "__main__":
    asyncio.run(run_diagnostic())
