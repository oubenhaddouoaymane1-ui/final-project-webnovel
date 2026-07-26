"""Quick component smoke test — validates each module individually."""
import asyncio, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

async def main():
    t0 = time.time()
    def ts(): return f"[{time.time()-t0:5.1f}s]"

    from src.config import load_config
    config = load_config("config/config.yaml")
    print(f"{ts()} Config loaded")

    from src.database import init_database
    db = init_database(Path(config["database"]["path"]))
    print(f"{ts()} Database ready")

    # 1) Parser — uses regex only, no LLM
    from src.novel_analyzer.parser import NovelParser
    parser = NovelParser(config)
    novel_text = Path("test_novel.txt").read_text()
    chapters = parser.parse_chapters(novel_text)
    print(f"{ts()} Parser: {len(chapters)} chapters")

    # Manual scene creation (skip LLM analysis for speed)
    from src.novel_analyzer.parser import Scene
    scene1 = Scene(id="ch1_sc1", chapter_number=1, scene_number=1,
        text=novel_text, characters=["Aldric", "Princess Elara"],
        location="castle courtyard", time_of_day="morning",
        emotion="neutral", importance="normal")
    scene2 = Scene(id="ch2_sc1", chapter_number=2, scene_number=1,
        text=novel_text, characters=["King Theron", "Meridian", "Aldric", "Elara"],
        location="throne room", time_of_day="afternoon",
        emotion="tension", importance="important")
    scenes = [scene1, scene2]
    print(f"{ts()} Scenes created: {len(scenes)}")

    # 2) Single character DNA (LLM call — ~30s)
    from src.character_engine.researcher import CharacterResearcher
    researcher = CharacterResearcher(config, db)
    print(f"{ts()} Building character DNA for 'Aldric'...")
    dna = await researcher.llm.build_character_dna("Aldric", {
        "appearances": ["Chapter 1 Scene 1"],
        "dialogues": ["Another peaceful day"],
        "physical_descriptions": ["tall knight with brown hair and blue eyes"],
        "personality_traits": ["brave", "loyal"],
        "actions": ["stood at the gate", "gripped his sword hilt"]
    })
    print(f"{ts()} Character DNA: {dna}")

    # 3) Single world build (LLM call — ~30s)
    from src.world_engine.builder import WorldBuilder
    wb = WorldBuilder(config, db)
    print(f"{ts()} Building world...")
    world = await wb.build_world(novel_text, scenes)
    print(f"{ts()} World: tech={world.technology}, atm={world.visual_atmosphere}")

    # 4) Visual production (no LLM, placeholder images)
    from src.visual_production.producer import VisualProducer
    # Build a minimal Character from DNA
    from src.database.models import Character
    char = Character(id="char-aldric", canonical_name="Aldric",
        gender="male", hair_color=dna.get("hair_color","brown"),
        eye_color=dna.get("eye_color","blue"),
        typical_clothing=dna.get("typical_clothing","armor"))
    vp = VisualProducer(config, db)
    images = await vp.produce_scene(scene1, [char], world)
    print(f"{ts()} Images generated: {len(images)}")

    # 5) Audio production (espeak fallback)
    from src.audio_production.producer import AudioProducer
    ap = AudioProducer(config, db)
    audio = await ap.produce_scene(scene1)
    print(f"{ts()} Audio: {audio.duration:.1f}s at {audio.audio_path}")

    # 6) Quality judge
    from src.quality_control.judge import QualityJudge
    judge = QualityJudge(config)
    score = await judge.evaluate_final("test.mp4")
    print(f"{ts()} Quality score: {score:.1f}")

    print(f"\n{'='*50}")
    print(f"ALL COMPONENTS OK in {time.time()-t0:.1f}s")
    print(f"{'='*50}")

if __name__ == "__main__":
    asyncio.run(main())
