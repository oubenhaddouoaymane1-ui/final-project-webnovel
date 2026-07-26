# ADR-009: Why prompt versioning exists

**Status:** Accepted
**Date:** 2026-07-26
**Deciders:** CineOS Architecture Team

## Problem

CineOS uses AI models for quality analysis, defect detection, repair guidance, and content evaluation. Many of these AI operations rely on carefully crafted prompts that instruct language models or vision-language models how to analyze cinematic content. The quality of analysis results is highly sensitive to prompt wording: small changes in prompt phrasing can significantly alter analysis scores, defect identification accuracy, and repair recommendations. A prompt that asks "evaluate the composition quality" may produce different results than one that asks "identify composition defects and rate severity on a 1-10 scale." Without version control on prompts, there is no way to reproduce a previous analysis result (since the prompt that produced it may have been overwritten), understand why analysis quality changed after a prompt edit (was it the prompt change or a change in content characteristics?), or roll back to a known-good prompt when a change introduces regressions. We need a system that versions prompts, tracks which prompt version produced which analysis result, and enables controlled experimentation with prompt variants.

## Decision

Every prompt used in CineOS AI operations is versioned and stored in the PostgreSQL database with a unique version identifier, creation timestamp, author, parent version (for tracking the version tree), and the complete prompt template text with its variable placeholders documented. When an AI operation executes, it records the prompt version used alongside the result in the analysis record. This creates a complete traceability chain: given any analysis result, you can identify the exact prompt version that produced it and trace the version history back to the original prompt.

Prompt versions are immutable once created — the prompt text and configuration cannot be changed after creation. To modify a prompt, a new version is created that references the previous version as its parent. This creates a version tree that tracks the evolution of each prompt over time, including branch points where experimental variants diverge from the production version. The current active version for each prompt role (quality analysis, defect detection, repair guidance, content evaluation) is stored in a configuration table and can be changed without modifying the prompt record itself, enabling instant rollbacks and A/B testing.

## Alternatives Considered

1. **Static prompts** — Hardcode prompts as string constants in the workflow code or configuration files. This is the simplest approach: prompts are part of the codebase, versioned by git, and deployed with the application. However, static prompts require a code deployment to change, which is slow for prompt tuning iterations that may require dozens of experiments per day. Git versioning tracks line-level changes but does not natively associate specific prompt versions with specific analysis results in the database — you must cross-reference git log timestamps with database records. Rolling back a prompt change requires a code deployment rather than a configuration change, adding risk and delay. Non-developers cannot modify prompts without going through the code review and deployment process. Rejected because the deployment coupling and lack of result-to-prompt traceability are unacceptable for an iterative prompt tuning workflow.

2. **Git-only versioning** — Store prompts in files and use git history as the version system, keeping prompts in a dedicated directory tracked by version control. This provides version control without additional infrastructure and integrates with existing development workflows (branching, merging, pull requests). However, git tracks all file changes together, making it difficult to associate a specific git commit with a specific analysis result stored in the database. Git does not provide a prompt registry that maps prompt IDs to versions, nor does it support branching between prompt variants for A/B testing without complex branching strategies. Querying "which git commit was used for this analysis result" requires cross-referencing timestamps between git log and database records, which is fragile, time-zone-sensitive, and error-prone. Rejected because the association between prompt versions and analysis results requires database-level tracking that git alone cannot provide.

3. **No versioning** — Treat prompts as configuration that can be changed at any time without tracking versions. This is the simplest approach and requires no versioning infrastructure at all. However, without versioning, there is no way to reproduce previous analysis results after a prompt change — if a prompt is modified and the new version produces different results, there is no record of the previous prompt text. When analysis quality degrades after a change, there is no way to determine whether a prompt change caused the regression or whether the underlying content characteristics changed. A/B testing of prompt variants is impossible because there is no record of which prompt produced which result. Rollback requires manually remembering or reconstructing the previous prompt text from documentation or chat history, which is unreliable. Rejected because reproducibility and regression diagnosis are fundamental requirements for a production AI pipeline where prompt changes directly impact output quality.

## Trade-offs

We gain complete traceability between prompt versions and analysis results, enabling reproducibility and regression diagnosis for every analysis operation. We gain the ability to roll back prompt changes instantly by updating the active version pointer in the configuration table, without code deployment or workflow modification. We gain A/B testing capability by running the same content through different prompt versions and comparing results in the database to identify optimal prompts. We accept the database overhead of storing prompt version records (one row per version, typically a few KB each), the complexity of prompt version management (choosing when to create new versions, which version is active for each role, how to handle version conflicts), the risk of prompt version proliferation (too many similar versions become difficult to navigate and compare), and the need for a prompt testing framework that evaluates prompt variants against known-good datasets before production deployment.

## Consequences

### Positive
- Every analysis result is traceable to the exact prompt version that produced it, enabling root cause analysis when results are unexpected or inconsistent
- Prompt changes can be rolled back instantly by updating the active version pointer in the configuration table, without code deployment or workflow modification
- A/B testing of prompt variants is supported natively by running the same content through different versions and comparing results in the database
- Non-developers can create and activate prompt versions through database updates or bot commands without requiring code changes or engineering involvement
- The prompt version history provides institutional knowledge about why prompts evolved, captured through version notes and author attribution on each version
- Prompt performance metrics (average analysis score distribution, defect detection rate, false positive rate) can be computed per version to identify optimal prompts for each use case
- The version tree structure supports experimental branching where a prompt variant is tested in isolation before being promoted to the production version

### Negative
- Prompt version management requires discipline: creating versions for every meaningful change without creating excessive near-duplicate versions that clutter the registry
- The prompt registry adds a database query to every AI operation startup to resolve the current active version, adding a small latency overhead
- Testing prompt variants requires a validation dataset and evaluation framework, adding infrastructure complexity that must be maintained
- Multiple active prompt versions running simultaneously (during A/B testing) can produce inconsistent analysis results for related shots in the same project
- Prompt version cleanup (archiving obsolete versions, merging branches) requires periodic maintenance to prevent database bloat and navigation confusion
- The team must adopt and follow a workflow convention for when to create new prompt versions versus modifying existing ones, which requires cultural alignment

## Future Improvements
- Implement a prompt testing framework that evaluates new prompt versions against a curated dataset of known-good analyses before production activation, providing pass/fail recommendations
- Add automatic prompt performance monitoring that detects quality regressions after prompt version changes and alerts the team
- Build a prompt comparison dashboard that shows analysis result distributions for two or more prompt versions side by side with statistical significance testing
- Implement gradual rollout of prompt versions (canary deployment) where a new version processes a small percentage of work before full activation
- Add prompt template variable documentation and validation to prevent errors when modifying prompt structure or adding new variables
- Create a prompt library that categorizes and describes each prompt's purpose, expected inputs, expected outputs, and performance characteristics for onboarding new team members

## References
- Prompt engineering best practices: https://www.promptingguide.ai
- CineOS prompt registry schema: ../architecture/prompt-registry.md
- CineOS AI operation documentation: ../ai/operations.md
- Prompt versioning in ML pipelines: https://neptune.ai/blog/ml-experiment-tracking
- Prompt template syntax reference: ../ai/prompt-templates.md
