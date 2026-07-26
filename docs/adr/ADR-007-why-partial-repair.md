# ADR-007: Why Partial Repair is preferred over full regeneration

**Status:** Accepted
**Date:** 2026-07-26
**Deciders:** CineOS Architecture Team

## Problem

When a render fails quality analysis, the pipeline must correct the defect and re-validate the result. The simplest approach is full regeneration: discard the failed render entirely and re-render the shot from scratch with the same or adjusted parameters. However, many failed renders are mostly correct — a single frame may have a compositing artifact, a short segment may have a color inconsistency, or a localized region may have a resolution issue caused by a momentary glitch in the render engine. Full regeneration of a multi-minute cinematic shot at 4K resolution can consume hours of GPU compute and may introduce new defects in previously correct regions, since render engines are not perfectly deterministic. We need a repair strategy that addresses specific defects without discarding work that is already correct.

## Decision

When a render fails quality analysis, the system first attempts partial repair: it identifies the specific defective frames, regions, or attributes and applies targeted corrections only to those areas. Partial repair uses the quality analysis results to pinpoint defects (e.g., "frames 1247-1253 have compositing artifacts at coordinates [x,y] with width W and height H," "color temperature drifts above threshold in the third quarter of the timeline," "resolution drops below threshold in the bottom-right quadrant of frame 892"), then dispatches a repair job that operates only on the identified defect scope.

The repair workflow reads the defect report, determines the repair strategy (AI-assisted frame repair for localized artifacts, targeted color correction for color drift, localized re-render for geometry errors), executes the repair on the specific frames and regions, and re-validates the repaired region through quality analysis. Only if partial repair fails — the defect cannot be repaired without affecting surrounding content, or the repair introduces new defects — does the system escalate to full regeneration. The escalation path is: partial repair attempt → quality re-validation → if still failing → full regeneration with adjusted parameters.

## Alternatives Considered

1. **Always regenerate** — When a render fails quality analysis, discard it entirely and re-render from scratch with potentially adjusted parameters. This guarantees a clean slate and eliminates the complexity of partial repair logic, defect localization, and region-specific processing. However, full regeneration is the most expensive option in terms of compute time and resources. A render that took 4 hours to generate is discarded and re-rendered, even if 95% of the frames were correct. Full regeneration also introduces risk: the new render may introduce different defects that were not present in the original (render engines have stochastic elements), and the regeneration parameters may not perfectly reproduce the correct elements. For high-resolution cinematic content with complex lighting and compositing, full regeneration can cost hundreds of GPU-hours per shot. Rejected because the compute cost and risk of introducing new defects make this approach unsustainable at scale.

2. **Human manual fix** — Route failed renders to a human artist who manually identifies and fixes the defect using professional editing tools (Nuke for compositing, DaVinci Resolve for color, After Effects for visual effects). Human artists can make nuanced decisions about repair quality and artistic intent that AI cannot evaluate. However, manual fixes do not scale: a production generating dozens of failed renders per day creates an unsustainable workload for the art team. Manual fixes are also inconsistent across artists (different artists apply different techniques and quality standards) and difficult to reproduce if the same defect appears in similar shots. The turnaround time for human repair is hours to days, far slower than automated partial repair which completes in minutes. Rejected as the primary repair mechanism; human review remains available as a fallback for complex defects that automated repair cannot handle.

3. **Accept defects** — Allow renders with quality analysis failures to progress through the pipeline without correction, accepting the defects as permanent. This maximizes throughput by eliminating the repair step entirely and reducing the total pipeline time per shot. However, accepting defects means downstream processing (compositing, color grading, audio mixing, packaging) operates on flawed input, potentially amplifying or obscuring the defect in ways that are harder to fix later. Defective final deliveries damage reputation with clients and stakeholders and may require expensive post-delivery fixes that disrupt the pipeline for other shots. The downstream cost of propagating defects consistently exceeds the cost of early repair. Rejected because accepting defects violates the quality guarantees that the pipeline is designed to provide and undermines the investment in quality analysis infrastructure.

## Trade-offs

We gain significant compute cost savings by repairing only defective regions (often 1-5% of the total render) rather than re-rendering entire shots (100% of the render), faster turnaround on the repair loop (targeted repair takes minutes versus hours for full regeneration), preservation of correct render elements that would be discarded in a full regeneration (eliminating the risk of introducing new defects in previously correct regions), and a learning opportunity (the system tracks what types of defects are repairable and which require escalation, building knowledge for future optimization). We accept the complexity of defect localization (identifying exactly which frames and regions need repair with sufficient precision), the possibility that partial repair may not fully resolve complex defects (requiring escalation to full regeneration after a failed attempt), the need for repair-specific AI models that can operate on localized regions while maintaining coherence with surrounding content, and the challenge of ensuring repaired regions are seamlessly blended with the surrounding un-repaired content without visible seams.

## Consequences

### Positive
- Compute costs are reduced by orders of magnitude for the majority of failed renders, which typically have localized defects affecting a small percentage of frames
- Turnaround time for the repair loop drops from hours (full regeneration) to minutes (targeted repair), reducing pipeline delay
- Previously correct render elements are preserved, eliminating the risk of introducing new defects during repair that were not present in the original
- The learning database tracks repair success rates by defect type, repair strategy, and content characteristics, enabling continuous improvement of repair capabilities
- Escalation to full regeneration provides a safety net for defects that cannot be repaired locally, ensuring all defects are eventually resolved
- Repair patterns (which defects are commonly repairable, which require escalation, which repair strategies work best for which defect types) inform render parameter tuning to prevent similar defects in future renders

### Negative
- Defect localization requires additional AI analysis to identify the exact frames and regions needing repair, adding latency and compute cost before repair begins
- Partial repair AI models must handle seamless blending between repaired and un-repaired regions, which is technically challenging and can introduce artifacts at boundaries
- The repair workflow has more branching logic (repair attempt → re-validation → potential escalation) compared to a simple regenerate flow, increasing complexity
- False localization (identifying the wrong region as defective) can lead to repairing content that was already correct, potentially introducing new defects
- Repair-specific AI models require training data, validation datasets, and ongoing maintenance, adding to the ML operations burden
- Escalation logic must handle edge cases where partial repair makes the render worse rather than better, requiring before/after comparison

## Future Improvements
- Implement defect localization confidence scoring to reduce false positives in region identification and only repair high-confidence defects
- Build a repair model training pipeline that learns from successful and failed repairs to improve repair quality and success rates over time
- Add automatic escalation heuristics based on defect complexity (e.g., large-area defects or defects spanning more than 20% of frames automatically escalate without attempting partial repair)
- Create a repair history database that tracks which repair strategies succeed for which defect types, content types, and render backends
- Implement progressive repair (repair in stages, re-validating after each stage rather than all at once) to catch failures early
- Add cost tracking that compares partial repair cost against estimated full regeneration cost to make data-driven escalation decisions

## References
- CineOS repair loop documentation: ../architecture/repair-loop.md
- CineOS defect classification system: ../architecture/defect-classes.md
- Partial repair model documentation: ../ai/repair-models.md
- Cost optimization analysis: ../operations/cost-analysis.md
- CineOS quality analysis output format: ../ai/analysis-output.md
