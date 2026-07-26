# ADR-003: Why workflows are decomposed into 25 independent units

**Status:** Accepted
**Date:** 2026-07-26
**Deciders:** CineOS Architecture Team

## Problem

CineOS manages a complex cinematic production pipeline that includes shot ingestion, multiple rendering passes (look development, lighting, compositing), AI-powered quality analysis across multiple dimensions, human review loops, repair cycles with partial and full strategies, asset packaging, and final delivery. The question is how to structure this pipeline within n8n: should it be one large workflow that handles everything end-to-end, a handful of coarse-grained workflows organized by pipeline phase, or many small, focused workflows organized by single responsibility? The answer affects fault isolation (can a failure in one stage block unrelated stages?), retry granularity (must we restart the entire pipeline or just the failed stage?), team scalability (can multiple engineers work on different stages simultaneously?), and debuggability (can we trace issues to a specific stage without understanding the entire pipeline?).

## Decision

We decompose the CineOS pipeline into approximately 25 independent n8n workflows, each responsible for a single, well-defined stage of the production pipeline. Workflows communicate through PostgreSQL (reading and writing state records to the shots and renders tables) and through n8n's Execute Workflow node for direct chaining when a downstream workflow must trigger immediately upon completion of an upstream one.

Each workflow operates on a specific entity type or pipeline stage: shot ingestion, render job creation, render farm dispatch, render completion handling, quality gate evaluation, individual quality analysis types (composition analysis, color consistency, continuity detection, resolution assessment), repair assessment, partial repair execution, full regeneration, human review assignment, review response handling, asset packaging, delivery preparation, notification dispatch, and pipeline state machine transitions. No workflow is responsible for more than one conceptual operation, and each workflow can be understood, tested, and modified in isolation.

## Alternatives Considered

1. **Monolithic workflow (single workflow)** — A single n8n workflow containing all pipeline logic in one visual graph. This is the simplest approach to author and initially debug since all logic is visible in one view. However, a monolithic workflow becomes unmanageable as the pipeline grows: the visual editor struggles to render graphs with hundreds of nodes, debugging requires tracing through unrelated stages to find the failure point, a failure in render dispatch blocks the entire pipeline even for unrelated downstream operations, and any change to one stage requires redeploying the entire workflow. A monolithic workflow also prevents multiple team members from working on different stages simultaneously since the entire workflow is a single unit. Rejected because the pipeline complexity exceeds what a single workflow can handle maintainably.

2. **3-5 large workflows** — Grouping related stages into a small number of coarse-grained workflows (e.g., "Ingestion," "Rendering," "Quality and Repair," "Delivery") reduces complexity compared to a monolith while maintaining some manageability. However, these groupings create artificial boundaries that force unrelated concerns together. The "Rendering" workflow would need to handle both job creation (synchronous orchestration) and completion callbacks (asynchronous webhook handling), mixing fundamentally different execution patterns. A failure in render completion handling would block render job creation within the same workflow. Debugging still requires tracing through large workflows with many branches and conditional paths. Rejected because the granularity is still too coarse for effective fault isolation and independent iteration.

3. **Microservices only (no n8n)** — Implementing each pipeline stage as a standalone microservice with its own process, API, message queue consumer, and deployment pipeline. This provides maximum isolation and independent deployability with well-defined API contracts. However, microservices require building custom inter-service communication (message queues, API calls, event buses), distributed tracing, service discovery, and deployment pipelines for each service. The team does not have the capacity to build and operate 25 microservices. Microservices also make it harder to visualize the overall pipeline flow since each service's logic is isolated in code rather than in a shared visual representation. Rejected because the operational overhead is disproportionate to our team size and the loss of pipeline visibility is unacceptable.

## Trade-offs

We gain independent deployability (changing the quality gate logic does not risk breaking render dispatch), fine-grained fault isolation (a failure in notification dispatch does not block quality analysis), precise retry granularity (retry only the failed stage rather than restarting the entire pipeline from the beginning), and the ability for multiple team members to work on different stages in parallel without merge conflicts. We accept the complexity of managing 25 workflow definitions, the overhead of inter-workflow communication through the database (adding latency compared to in-process function calls), the need for a consistent interface contract between workflows that produce and consume data, and the challenge of maintaining an accurate mental model of the full pipeline across many independent units.

## Consequences

### Positive
- A failure in any single workflow does not cascade to block unrelated pipeline stages, improving overall pipeline resilience and throughput
- Individual workflows can be tested, debugged, and redeployed independently without affecting other stages or requiring full pipeline testing
- Team members can own specific workflows (e.g., one engineer owns all quality analysis workflows) without stepping on each other's changes during development
- Retry logic operates at the stage level, eliminating wasted re-execution of already-completed stages and reducing recovery time
- The visual editor remains manageable because each workflow contains a focused, comprehensible graph of ten to thirty nodes
- Workflow execution history provides stage-level audit trails for debugging performance bottlenecks and identifying failure patterns
- New pipeline stages can be added as new workflows without modifying any existing workflow, enabling incremental pipeline evolution
- Each workflow can be independently monitored for execution time, error rate, and throughput, enabling targeted optimization

### Negative
- Coordinating changes that span multiple workflows requires careful planning to maintain interface contracts between producers and consumers
- Debugging cross-workflow issues requires correlating execution logs across multiple workflow runs, which is harder than tracing a single monolithic execution
- The database becomes the communication bus, adding latency and a dependency on database availability compared to in-process function calls
- Maintaining 25 workflow definitions requires discipline in naming conventions, documentation, and interface standards to prevent chaos
- Integration testing the full pipeline requires standing up all 25 workflows and their database interactions, which is complex and slow
- Versioning workflow interfaces (what data a downstream workflow expects from an upstream one) requires explicit contract management and testing

## Future Improvements
- Create a workflow interface registry that documents the expected input/output contract for each workflow, enabling automated contract testing between stages
- Implement a pipeline topology visualization tool that renders the current workflow graph from database state rather than relying solely on n8n's UI
- Add distributed tracing by propagating a correlation ID through all workflow executions for end-to-end debugging across workflow boundaries
- Build an integration test framework that can execute the full pipeline against a test database with synthetic inputs for regression testing
- Create workflow templates for common patterns (webhook handler, database poller, quality gate) to reduce boilerplate when adding new stages
- Monitor workflow execution latency and error rates in a unified dashboard to identify bottlenecks and reliability issues across the full pipeline

## References
- CineOS pipeline topology diagram: ../architecture/pipeline-topology.md
- n8n Execute Workflow documentation: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.executeWorkflow
- Single Responsibility Principle: https://en.wikipedia.org/wiki/Single_responsibility_principle
- CineOS workflow registry and catalog: ../workflows/README.md
- CineOS inter-workflow communication patterns: ../architecture/workflow-communication.md
