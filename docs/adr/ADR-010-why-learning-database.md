# ADR-010: Why a Learning Database exists

**Status:** Accepted
**Date:** 2026-07-26
**Deciders:** CineOS Architecture Team

## Problem

CineOS operates across multiple projects, each with its own renders, quality analysis results, repair outcomes, and delivery history. Without a mechanism to capture and learn from cross-project experience, every new project starts from scratch: quality thresholds must be manually re-tuned by an experienced operator, render backend performance characteristics must be re-discovered through trial and error, defect patterns that were solved in previous projects are not automatically recognized when they appear again, and optimization decisions are made based on intuition and tribal knowledge rather than empirical data. The system does not improve over time — it merely repeats the same patterns with manual adjustments applied inconsistently by different team members. We need a persistent knowledge base that accumulates operational experience from every pipeline execution and applies it to future decisions automatically.

## Decision

We implement a Learning Database that captures operational data from every pipeline execution across all projects and uses it to inform future pipeline decisions. The Learning Database is a set of PostgreSQL tables and materialized views that aggregate historical data into actionable knowledge: quality threshold recommendations per content type and render backend, backend performance rankings (which render backend produces the fewest defects for which type of content and shot complexity), repair success rates by defect type and repair strategy, analysis accuracy metrics (how often AI analysis matches human review outcomes), and pipeline configuration recommendations (optimal retry counts, timeout values, parallelism settings).

The Learning Database is updated by every pipeline stage that produces meaningful outcome data. When a shot passes quality analysis, the quality scores, thresholds used, render backend, content characteristics, and shot metadata are recorded. When a repair succeeds or fails, the defect type, repair strategy applied, outcome, and cost (compute time and GPU-hours) are recorded. When a render completes, the backend used, parameters applied, duration, and quality outcome are recorded. Over time, the database accumulates enough data to support statistical analysis and pattern recognition that informs pipeline configuration decisions with increasing confidence.

## Alternatives Considered

1. **Static configuration** — Define quality thresholds, backend preferences, and pipeline parameters as static configuration values that are set once during initial setup and rarely changed. This is the simplest approach: configuration is predictable, auditable, easy to understand, and requires no additional infrastructure. However, static configuration does not adapt to changing content characteristics (a threshold tuned for animated content may be wrong for live-action), does not benefit from operational experience (the system never learns from its successes and failures), and requires manual expert intervention to tune when problems are discovered. A quality threshold that works well for one project may be too loose for another with higher quality standards. Static configuration treats all content types identically, ignoring that different types of content (dialogue scenes, action sequences, VFX-heavy shots, establishing shots) have fundamentally different quality characteristics. Rejected because static configuration does not enable the system to learn and improve from operational data.

2. **Manual tuning** — Rely on experienced operators to review pipeline performance metrics and manually adjust thresholds, backend preferences, and parameters based on their professional judgment. Manual tuning leverages human expertise and can account for nuanced factors that automated systems miss (artistic intent, client preferences, narrative context). However, manual tuning does not scale: as the number of projects, content types, and render backends grows, the tuning surface becomes too large for humans to optimize comprehensively. Manual tuning is also inconsistent — different operators make different judgments under different conditions, and the reasoning behind tuning decisions is rarely documented. Tuning knowledge resides in individual operators' heads and is lost when they leave the team or are unavailable. Rejected because manual tuning does not scale, does not create durable institutional knowledge, and produces inconsistent results across operators.

3. **Per-project settings only** — Allow each project to have its own configuration (thresholds, backend preferences, repair parameters) but do not share learning data across projects. This provides project-specific tuning without the complexity of a cross-project learning system. Each project can be optimized independently based on its specific requirements. However, per-project settings require each project to independently discover optimal configurations through trial and error. Lessons learned in one project (e.g., "backend X produces fewer compositing defects for high-motion content above 120fps") are not automatically applied to the next project with similar content. Each project starts from scratch with manual tuning, duplicating effort across projects. The aggregate data that could inform cross-project insights is siloed in project-specific settings and never analyzed in aggregate. Rejected because the absence of cross-project learning means the system does not accumulate knowledge or improve over time.

## Trade-offs

We gain automatic improvement of pipeline configuration based on accumulated operational data, cross-project knowledge transfer that benefits new projects immediately from day one, data-driven decision making that replaces intuition and manual tuning with empirical evidence, threshold optimization that adapts to content characteristics based on actual pass/fail outcomes, backend ranking that routes work to the most effective renderer for each content type based on historical defect rates, repair strategy selection guided by historical success rates for each defect type, and a durable institutional knowledge base that survives team member changes and provides traceable rationale for every configuration decision. We accept the complexity of maintaining the learning database schema and aggregation logic, the risk of drawing incorrect conclusions from insufficient or biased data (especially early in the system's life when sample sizes are small), the need for statistical rigor in analysis to avoid overfitting to noisy data or confounding variables, the computational overhead of running aggregation queries on growing historical datasets, and the challenge of determining when historical data is representative enough of current conditions to inform decisions.

## Consequences

### Positive
- New projects automatically benefit from accumulated knowledge of previous projects, reducing ramp-up time and initial configuration errors
- Quality thresholds are continuously optimized based on actual pass/fail outcomes rather than static expert estimates, improving first-pass quality rates
- Render backend selection is informed by historical defect rates for similar content, routing work to the most effective renderer and reducing downstream repair
- Repair strategy selection is guided by historical success rates for each defect type and content combination, reducing failed repair attempts and escalation rates
- Pipeline configuration recommendations are data-driven and auditable, with clear evidence supporting each recommendation that stakeholders can verify
- Trend analysis identifies systemic issues (e.g., a particular backend's quality degrading over time, a model's accuracy declining) before they become critical failures
- The learning database provides a foundation for future ML-based pipeline optimization, Bayesian hyperparameter tuning, and predictive quality modeling

### Negative
- The learning database requires ongoing maintenance to ensure data quality, prevent stale or corrupted data from influencing decisions, and handle schema evolution as new metrics are added
- Statistical analysis of pipeline data requires careful methodology to avoid misleading conclusions from small sample sizes, confounding variables, or selection bias
- The aggregation queries that compute recommendations add database load, requiring careful indexing, query optimization, and potentially materialized views for expensive computations
- The system may develop biases if operational data is not representative of future content (e.g., learning predominantly from one genre of content may produce suboptimal recommendations for other genres)
- Displaying and explaining recommendation rationale to users adds UI complexity — users need to understand why a recommendation was made to trust it
- Initial data insufficiency means the learning database provides no value until enough operational history accumulates (typically dozens to hundreds of shots per recommendation category)
- There is a risk of over-optimization: tuning thresholds too aggressively based on historical data may reduce the system's ability to handle novel or unexpected content

## Future Improvements
- Implement confidence intervals on all recommendations so users understand the reliability and statistical significance of each suggestion
- Add anomaly detection that alerts when operational outcomes deviate significantly from learned patterns, indicating a systemic issue or content change
- Build a recommendation dashboard that explains why each recommendation is made, showing the underlying data, statistical analysis, and confidence level
- Implement automatic threshold adjustment with human approval gates for high-confidence recommendations, reducing manual intervention for well-understood patterns
- Add content-type clustering that groups similar shots for more targeted learning (e.g., separate learning for dialogue scenes, action sequences, VFX-heavy shots, and establishing shots)
- Create a data quality monitoring system that detects and flags stale, biased, or insufficient data for each recommendation category
- Implement A/B testing of learning-driven recommendations against static defaults to quantify the value of the learning system and justify continued investment
- Build predictive models that forecast quality outcomes based on render parameters before rendering begins, enabling preemptive parameter optimization

## References
- CineOS learning database schema: ../architecture/learning-database.md
- CineOS quality threshold documentation: ../architecture/quality-gate.md
- CineOS render backend comparison: ../architecture/render-backends.md
- Bayesian optimization for pipeline tuning: https://arxiv.org/abs/1807.02811
- CineOS operational metrics: ../operations/metrics.md
- CineOS data aggregation queries: ../architecture/learning-queries.md
