# ADR-001: Why n8n is the orchestration layer

**Status:** Accepted
**Date:** 2026-07-26
**Deciders:** CineOS Architecture Team

## Problem

CineOS requires a workflow orchestration layer that coordinates rendering pipelines, asset management, AI-powered quality analysis, and human review loops. The orchestration system must handle long-running workflows (some spanning hours or days for large renders), support conditional branching based on quality analysis results, retry failed steps with configurable backoff, and remain accessible to non-developer team members such as producers and directors who may need to inspect or modify pipeline logic without filing engineering tickets. The system must also integrate with external services through HTTP webhooks (render farm callbacks, AI worker completion signals), maintain direct access to a shared PostgreSQL database for state management, and support workflow composition through sub-workflow chaining. We need to evaluate whether an existing orchestration platform can serve this role or whether a custom solution is warranted.

## Decision

We adopt n8n (self-hosted, community edition) as the primary orchestration layer for all CineOS workflows. n8n will coordinate every pipeline stage including shot ingestion, render dispatch, quality gate evaluation, repair loops, and final delivery. Workflows are authored visually in the n8n editor and stored as JSON definitions that live alongside the codebase in version control, enabling code review of pipeline changes.

n8n's Execute Workflow nodes allow us to chain sub-workflows together, enabling modular composition without tight coupling between pipeline stages. Webhook nodes expose HTTP endpoints that external services (render farms, AI workers, Telegram bot) can call back into to report completion or status changes. PostgreSQL nodes provide direct, transactional access to the shared database without requiring a separate API layer for simple data operations. The self-hosted deployment runs on our own infrastructure, keeping all production data and workflow definitions under our control with zero licensing cost under the community edition.

## Alternatives Considered

1. **Apache Airflow** — Airflow is battle-tested for batch-oriented data pipelines and has strong scheduling capabilities with its DAG execution model. It has a large ecosystem of providers and operators. However, its DAG-based model assumes relatively short task durations and is poorly suited to human-in-the-loop workflows where a task might pause for hours waiting for a producer's approval. Airflow's UI is developer-focused and intimidating for non-technical stakeholders who need to inspect pipeline status. The executor model (Celery, Kubernetes) adds significant operational overhead that is disproportionate for our scale. The learning curve for writing Airflow DAGs in Python is steep for team members unfamiliar with the framework. Rejected because it forces an engineering-heavy workflow for what should be accessible pipeline definitions and cannot gracefully handle long-running human approval gates.

2. **Temporal** — Temporal provides extremely strong durability guarantees and explicit state machine programming through workflows-as-code. It excels at complex, long-running distributed transactions with automatic retries and compensation logic. However, Temporal requires writing workflow code in Go, Java, or TypeScript with no visual editor, creating a hard dependency on engineering for any pipeline change. Temporal also lacks built-in webhook handling, requiring custom activity implementations for HTTP callbacks and custom infrastructure for webhook routing. The operational complexity of running Temporal servers, workers, and the visibility store exceeds our current team capacity. Debugging requires understanding Temporal's internal execution model and history service. Rejected because the engineering cost of authoring and maintaining workflows is too high and the lack of visual authoring excludes non-developers.

3. **Prefect** — Prefect offers a Python-native experience with a modern UI and good cloud integration. Its flow/task model maps well to our decomposition into independent stages. Prefect 2.x introduced excellent local execution and orchestration capabilities. However, Prefect's free tier is limited and its self-hosted option (Prefect Server) has weaker community support and documentation compared to n8n. The Python-only authoring model excludes non-developers entirely. Prefect's webhook support requires additional configuration and does not match n8n's native, first-class webhook nodes with inline payload inspection. Prefect Cloud pricing scales with execution count, which becomes expensive at our volume. Rejected because the community edition limitations and Python-only authoring model create unnecessary constraints.

4. **Custom orchestrator (in-house)** — Building our own orchestration engine would give us total control over the execution model, state transitions, and UI. The appeal is eliminating any third-party dependency and tailoring every aspect to cinematic production workflows. However, the engineering investment to build a reliable orchestrator with persistence, retry logic, monitoring, and a usable interface is substantial — we estimate six to twelve months of dedicated engineering. We would spend months building infrastructure instead of production features. Maintaining a custom orchestrator becomes a permanent tax on the team as we add features, fix bugs, and handle security updates. Rejected because the build-and-maintain cost far exceeds the adaptation cost of n8n.

## Trade-offs

We gain a visual workflow editor that non-developers can use to inspect and modify pipeline logic, a large community providing pre-built integrations and troubleshooting help, rapid iteration on pipeline changes without code deployments, and a self-hosted deployment with zero licensing cost under the community edition. We accept that n8n's execution model is less durable than Temporal's (no automatic workflow replay on failure), that complex branching logic can become visually unwieldy at scale in the editor, and that we are coupled to n8n's release cycle and potential breaking changes between versions. We also accept that n8n's native observability is limited compared to purpose-built orchestrators, requiring us to supplement with custom logging and database-driven status tracking.

## Consequences

### Positive
- Producers and directors can inspect and even modify pipeline workflows through a visual interface without requiring engineering support or code changes
- Webhook-first design integrates naturally with render farm callbacks, AI worker completion signals, and Telegram bot interactions
- Execute Workflow chaining allows us to keep individual workflows focused and independently testable while composing complex pipelines
- Self-hosted community edition eliminates licensing costs and keeps all production data and workflow definitions on-premises
- Active open-source community provides rapid bug fixes, new node types, and community support forums for troubleshooting
- JSON-based workflow definitions are version-controllable and diffable in pull requests, enabling code review of pipeline changes
- The built-in credential management system stores API keys and database connections securely with encryption at rest

### Negative
- n8n's execution engine is single-node in community edition, creating a potential bottleneck for very high-throughput scenarios
- Complex conditional logic becomes difficult to author and debug in the visual editor compared to code-based alternatives
- Upgrade path from community edition to enterprise features (multi-execution, advanced observability, RBAC) involves licensing cost
- Debugging workflow failures requires navigating n8n's execution log UI, which lacks structured alerting without additional tooling
- Dependency on n8n's TypeScript runtime for custom nodes means we must occasionally maintain forked or custom node packages
- The visual editor can become slow and difficult to navigate for workflows exceeding fifty nodes

## Future Improvements
- Evaluate n8n's queue mode for horizontal scaling as pipeline throughput grows beyond single-node capacity
- Build custom n8n nodes for CineOS-specific operations (render farm dispatch, media asset resolution) to reduce workflow complexity
- Implement structured logging that exports n8n execution metadata to our PostgreSQL database for unified observability
- Investigate n8n's emerging multi-user permission model to control who can modify production pipeline workflows
- Create a testing harness that runs workflow definitions against snapshot databases for regression testing pipeline changes
- Build a workflow health dashboard that monitors execution success rates, average durations, and error patterns across all 25 workflows
- Establish a regular n8n upgrade cadence with automated test suite validation before upgrading production instances

## References
- n8n documentation: https://docs.n8n.io
- n8n community edition license and features: https://n8n.io/pricing
- Execute Workflow node documentation: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.executeWorkflow
- Webhook node documentation: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook
- CineOS pipeline architecture overview: ../architecture/pipeline-overview.md
- CineOS workflow registry and catalog: ../workflows/README.md
