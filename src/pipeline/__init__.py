"""Pipeline package — staged processing with hard gates."""
from .contracts import (
    NovelText, Chapter, Scene, CharacterDNA, WorldBible,
    ShotPlan, ScenePlan, GeneratedImage, GeneratedAudio,
    AssembledVideo, AuditReport, PipelineResult,
)
from .orchestrator import PipelineOrchestrator, PipelineHalted
from .phase1_intake import phase1_intake, IntakeError
from .phase2_analysis import phase2_analysis, AnalysisError
from .phase3_verify import phase3_verify, VerificationError
from .phase4_prompt_plan import phase4_prompt_plan, PromptPlanError
from .phase5_render import phase5_render, RenderError
from .phase6_assembly import phase6_assembly, AssemblyError
from .phase7_audit import phase7_audit, AuditError
