# ADR-006: Why Quality AI is mandatory before progression

**Status:** Accepted
**Date:** 2026-07-26
**Deciders:** CineOS Architecture Team

## Problem

In a cinematic production pipeline, renders progress through multiple stages: initial render, quality analysis, potential repair, re-render, re-analysis, and final delivery. Without mandatory quality gates, defective renders can progress downstream, where they consume additional compute resources for compositing, color grading, and packaging — only to be rejected late in the pipeline when the defect is finally discovered by a human reviewer or a later-stage automated check. Late-stage rejections are expensive: they waste compute cycles on downstream processing of defective input, delay delivery timelines by requiring full rework chains, and create confusion about which version of an asset is authoritative. A defect caught after compositing and color grading means undoing all that work, repairing the render, and redoing the downstream steps. We need to determine whether quality analysis should be an optional checkpoint that can be skipped under time pressure or a mandatory gate that blocks progression until it passes.

## Decision

Quality AI analysis is a mandatory gate that must complete and pass before any shot can progress to the next pipeline stage. No workflow may transition a shot from "rendered" to any downstream state without a passing quality analysis record in the database. The state machine enforces this requirement: the transition from "rendered" to "in-review" or "approved" requires a quality analysis record with a score above the configured threshold for each required analysis type. Shots that fail quality analysis must enter the repair loop before they can progress.

Quality analysis runs multiple analysis types in parallel (composition scoring, color consistency evaluation, continuity detection, resolution assessment) and aggregates results into a single quality score with per-type breakdowns. The quality threshold is configurable per project and stored in the learning database, allowing it to be tuned over time based on historical data and project-specific requirements. The mandatory quality gate applies to all renders including re-renders after repair, ensuring that repaired renders are re-validated before progressing.

## Alternatives Considered

1. **Post-generation review only** — Run quality analysis at the end of the pipeline just before delivery, rather than immediately after each render stage. This reduces the number of quality analysis runs (one per shot instead of potentially multiple for repaired shots) and simplifies the pipeline flow by removing quality checks from the middle of the pipeline. However, post-generation review discovers defects after all downstream processing is complete. A defect found at this stage requires rolling back the entire downstream chain: undo compositing, undo color grading, undo packaging, repair the render, re-render, re-composite, re-grade, and re-package. The cost of late-stage defect discovery is orders of magnitude higher than early-stage discovery because of all the wasted downstream compute. Rejected because the cost of downstream rework far exceeds the cost of running quality analysis immediately after each render.

2. **Human-only review** — Skip AI quality analysis entirely and rely on human reviewers to evaluate every render at each stage. Humans are the ultimate judges of cinematic quality and can catch subjective issues (artistic intent, narrative coherence, emotional impact) that AI cannot evaluate. However, human review of every render at every stage is not scalable. A production may generate hundreds of renders per day; requiring human review of each one creates a bottleneck that delays the entire pipeline by hours or days. Human review is expensive (labor cost per review) and inconsistent (different reviewers apply different standards, especially under time pressure). AI quality analysis does not replace human review but augments it by pre-filtering obvious defects, quantifying objective metrics, and ensuring consistent baseline quality. Rejected as the primary mechanism because human-only review does not scale and does not provide the consistency needed for automated pipeline progression.

3. **Skip for speed** — Allow renders to progress without quality analysis when pipeline pressure is high (tight deadlines, urgent client deliveries). This maximizes throughput by eliminating the quality gate as a potential bottleneck. However, allowing skipped quality gates means defective renders will propagate downstream, consuming compute resources on compositing, grading, and packaging before the defect is eventually discovered. It also creates an inconsistent pipeline where some shots are quality-validated and others are not, making it impossible to guarantee delivery quality or provide quality metrics. The time saved by skipping quality analysis (minutes per shot) is typically less than the time lost to downstream rework of defective shots (hours per shot). Rejected because the downstream cost of skipped quality gates consistently exceeds the time saved.

## Trade-offs

We gain guaranteed quality validation for every shot before any downstream processing consumes compute resources, early defect detection that minimizes wasted compute and maximizes the value of every GPU-hour spent, consistent quality standards enforced by AI models with configurable thresholds that apply uniformly across projects and content types, and a foundation for the repair loop (defects are identified immediately with precise localization information and can be repaired before progressing). We accept the latency added by quality analysis (seconds to minutes per shot depending on analysis types and model complexity), the compute cost of running AI analysis on every render (including re-renders after repair), the possibility of false positives that flag acceptable renders for unnecessary repair, and the hard dependency on quality analysis worker availability — if quality analysis workers are unavailable, the pipeline stalls at the quality gate.

## Consequences

### Positive
- Defective renders are caught immediately after generation, before any downstream processing consumes compute resources on flawed input
- The repair loop receives precise defect information from quality analysis (type, location, severity), enabling targeted partial repair rather than full regeneration
- Consistent quality thresholds are enforced across all projects and content types, eliminating human variability in pass/fail decisions
- Quality scores accumulate in the learning database, enabling threshold tuning and trend analysis over time to optimize the balance between false positives and missed defects
- Downstream workflows (compositing, grading, packaging) can trust that input shots have passed quality validation, simplifying their error handling
- False positive rates can be monitored and thresholds adjusted to balance between missed defects and unnecessary repairs
- The mandatory gate provides a clear, auditable checkpoint for quality compliance reporting to stakeholders

### Negative
- The quality gate becomes a pipeline bottleneck if analysis throughput cannot keep up with render throughput, requiring careful capacity planning
- False positives waste repair compute on shots that were already acceptable, adding cost and latency without value
- Quality analysis workers must be available and healthy for the pipeline to progress, creating an availability dependency that requires monitoring and redundancy
- The quality analysis models may not catch all defect types, creating a false sense of security that can be worse than no gate at all
- Re-renders after repair require re-analysis, adding cumulative latency to the repair loop for shots that fail multiple times
- New projects start with potentially suboptimal thresholds because the learning database requires historical data to provide recommendations

## Future Improvements
- Implement adaptive quality thresholds per project based on learning database data, replacing hardcoded defaults with data-driven values
- Add a confidence score to quality analysis results to distinguish high-confidence failures from borderline cases that may need human review
- Build a quality analysis throughput monitor that alerts when analysis queue depth threatens to create a pipeline bottleneck
- Implement selective quality analysis (skip full re-analysis for re-renders of shots that previously scored above a very high threshold on non-defective dimensions)
- Add false positive tracking and threshold auto-tuning based on human review outcomes to reduce unnecessary repairs over time
- Create quality analysis dashboards that show defect distribution by type, severity, and project for continuous improvement insights

## References
- CineOS quality gate specification: ../architecture/quality-gate.md
- CineOS repair loop documentation: ../architecture/repair-loop.md
- Learning database schema: ../architecture/learning-database.md
- Quality threshold tuning guide: ../operations/threshold-tuning.md
- CineOS quality analysis models: ../ai/quality-models.md
