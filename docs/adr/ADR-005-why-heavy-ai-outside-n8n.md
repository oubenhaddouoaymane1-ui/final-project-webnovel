# ADR-005: Why heavy AI computation runs outside n8n

**Status:** Accepted
**Date:** 2026-07-26
**Deciders:** CineOS Architecture Team

## Problem

CineOS uses AI models for quality analysis (composition scoring, color consistency, continuity detection, resolution assessment), upscaling, denoising, frame interpolation, and partial repair operations. These operations require GPU acceleration with significant VRAM (8-24 GB per model), processing times ranging from seconds per frame to minutes per shot, and memory-intensive tensor operations that can consume gigabytes of RAM. n8n's execution environment is a Node.js process designed for workflow orchestration — routing data between nodes, making HTTP calls, and performing database operations — not for GPU-accelerated computation. Running heavy AI workloads inside n8n would consume the orchestration layer's resources, risk crashing the workflow engine due to OOM conditions, and prevent independent scaling of GPU resources. We need to determine where AI computation should execute relative to the orchestration layer.

## Decision

All heavy AI computation runs on remote worker processes outside of n8n. n8n workflows dispatch work to remote workers by writing job records to PostgreSQL and, in some cases, sending HTTP requests to worker endpoints. Remote workers poll the database for pending jobs, execute GPU-accelerated operations, and write results back to PostgreSQL. n8n workflows detect completion by polling the database for result records or receiving webhook callbacks from workers when processing finishes.

Each worker type (quality analysis, upscaling, denoising, frame interpolation, partial repair) runs as an independent Python process with its own GPU resource requirements, scaling characteristics, and failure modes. Workers are deployed as long-running processes on GPU-equipped machines and can be scaled independently based on the type of AI work they perform. Worker health is monitored through heartbeat records in the database, and stale workers are automatically detected and replaced by process supervision.

## Alternatives Considered

1. **Execute Command nodes in n8n** — n8n's Execute Command node can run arbitrary shell commands, including invoking Python scripts or CLI tools that perform AI computation. This keeps everything within the n8n workflow graph and requires no external infrastructure. However, Execute Command nodes run in the n8n process's execution context, consuming the same Node.js process's memory and CPU. Long-running GPU operations (minutes to hours) would block the n8n execution thread, preventing other workflows from executing. If the GPU operation crashes, it can take down the entire n8n instance due to shared process memory. There is no way to route GPU work to a specific machine with a GPU, since Execute Command runs on whatever host n8n is deployed to. Rejected because GPU operations are fundamentally incompatible with n8n's single-process, cooperative scheduling execution model.

2. **Python subprocess spawned by n8n** — A custom n8n node or HTTP Request node could spawn a Python subprocess on the n8n host that performs AI computation. The subprocess runs outside Node.js and can use GPU resources directly through CUDA or Metal. However, the subprocess still runs on the n8n host machine, which may not have a GPU or may not have sufficient VRAM for multiple concurrent AI operations. The subprocess lifecycle must be managed by n8n, adding complexity to the workflow and creating resource leak risks if subprocesses are not properly reaped. If the subprocess hangs or leaks memory, n8n has limited ability to detect and kill it since it cannot introspect the child process's resource usage. Subprocess management does not scale horizontally since it is tied to the n8n host. Rejected because it couples GPU work to the n8n host and does not enable independent scaling or resource isolation.

3. **In-workflow GPU calls via Python kernel** — If n8n supported an embedded Python runtime with GPU access, workflows could call AI models directly as inline operations. Some workflow tools offer kernel-style execution environments that embed interpreters. However, n8n does not support embedded Python kernels, and building this capability would require forking n8n's execution engine and maintaining a custom build. Even if implemented, sharing GPU resources between the orchestration process and computation processes creates resource contention and fault propagation risks — a GPU OOM in one workflow could crash the entire n8n instance. Rejected because it requires substantial n8n modifications and creates unacceptable coupling between orchestration and computation.

## Trade-offs

We gain isolation between orchestration and computation (a GPU worker crash does not affect n8n's ability to manage other workflows), independent horizontal scaling of GPU resources (add more quality analysis workers without scaling n8n itself), resource monitoring per worker type (track GPU utilization, VRAM usage, and processing throughput independently for capacity planning), and the ability to use Python's mature ML ecosystem (PyTorch, TensorFlow, OpenCV, Pillow) without Node.js bindings or FFI overhead. We accept the added complexity of worker infrastructure (deployment, process supervision, health monitoring), the latency of database polling or webhook callbacks for completion detection (adding seconds of latency compared to in-process calls), the need for a job queue protocol with retry and timeout semantics, and the operational overhead of monitoring and deploying separate worker processes on GPU-equipped machines.

## Consequences

### Positive
- n8n remains lightweight and responsive for orchestration tasks even when GPU workers are under heavy load, experiencing high latency, or experiencing partial failures
- GPU workers can be deployed on dedicated GPU machines and scaled independently based on workload characteristics and budget constraints
- Worker crashes are isolated and do not bring down the orchestration layer or affect other pipeline stages running in n8n
- Each worker type can be optimized independently with different VRAM requirements, different Python dependency versions, and different scaling policies
- GPU utilization metrics are collected per worker type, enabling informed capacity planning and cost optimization decisions
- Workers can be implemented in Python with direct access to PyTorch, TensorFlow, Hugging Face transformers, and other ML frameworks without FFI overhead or binding complexity
- Worker instances can be ephemeral (container-based) or persistent (long-running processes), depending on cost and latency requirements

### Negative
- Job dispatch and completion detection add latency compared to in-process function calls (database polling interval of one to five seconds, or webhook delivery time)
- Workers require their own deployment, monitoring, and health checking infrastructure that must be built and maintained
- Debugging worker failures requires correlating logs across n8n execution logs and worker process logs, which are in different systems and formats
- The job queue protocol (database schema, polling logic, timeout handling, retry semantics) must be designed, implemented, and maintained
- Network communication between n8n and workers adds a failure mode (network partition, database unavailability, DNS resolution failure) that in-process calls avoid
- Worker scaling requires infrastructure management (container orchestration, process supervision, or cloud auto-scaling groups) beyond n8n's capabilities

## Future Improvements
- Replace database polling with PostgreSQL LISTEN/NOTIFY for real-time job completion detection, reducing completion detection latency from seconds to milliseconds
- Implement a worker health check endpoint and integrate it with n8n workflow retry logic for automatic failover to healthy worker instances
- Add GPU resource tracking to the database to enable intelligent job routing based on available VRAM and current GPU utilization per worker
- Build a worker auto-scaling system that monitors queue depth and scales worker instances up or down based on demand
- Implement worker result caching to avoid re-computing analysis for unchanged shots, reducing GPU time and costs
- Create a worker dashboard that shows per-type throughput, error rates, queue depth, and resource utilization in real time
- Add graceful worker shutdown that finishes in-progress jobs before terminating, preventing partial results and wasted compute

## References
- n8n Execute Command node: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.executeCommand
- PostgreSQL LISTEN/NOTIFY: https://www.postgresql.org/docs/current/sql-notify.html
- CineOS worker architecture: ../architecture/worker-architecture.md
- CineOS GPU resource management: ../architecture/gpu-resources.md
- CineOS job queue protocol: ../architecture/job-queue.md
