# ADR-002: Why PostgreSQL is the single source of truth

**Status:** Accepted
**Date:** 2026-07-26
**Deciders:** CineOS Architecture Team

## Problem

CineOS must persist and query a wide variety of structured and semi-structured data: project metadata with rigid schemas, render job histories with complex relational queries, AI analysis results that vary by content type, user preferences, quality thresholds, learning database entries, and pipeline state transitions. The database must handle concurrent writes from n8n orchestrations, AI workers, and the Telegram bot simultaneously without corruption or lost updates. It must also support ad-hoc analytical queries for reporting, auditing every state transition for compliance and debugging, and storing flexible JSON payloads from AI analysis nodes without requiring schema migrations for every new analysis type. The data store must be reliable enough that no production data is ever lost and queryable enough that the entire pipeline can operate through a single query language.

## Decision

We use PostgreSQL as the single source of truth for all CineOS data. Every piece of persistent state — projects, shots, renders, quality scores, pipeline states, user preferences, learning database entries, prompt versions, and audit logs — lives in PostgreSQL. No data is stored exclusively in files, in-memory caches, or external services without a corresponding authoritative record in the database.

PostgreSQL's JSONB columns store semi-structured data such as AI analysis results and render metadata, allowing us to query inside JSON documents with GIN indexes while still enforcing a relational schema for the core fields. Triggers and materialized views implement computed aggregates and enforce business rules at the database level, ensuring consistency regardless of which application component writes data. Row-level security policies can restrict data access per user or service. The entire data model is managed through versioned migrations that are tested in CI before deployment.

## Alternatives Considered

1. **MongoDB** — MongoDB's document model is appealing for semi-structured AI analysis results that vary significantly between analysis types. Schema flexibility means new analysis formats can be stored without migrations. However, MongoDB lacks true multi-document ACID transactions in earlier versions and its transaction support in recent versions has performance caveats and operational complexity. MongoDB's query language for joins and aggregations is significantly less powerful than SQL for the relational queries we need — for example, finding all shots across projects that failed a specific quality gate within a time range with correlated analysis results. MongoDB also lacks built-in support for triggers, views, and constraints that we rely on for data integrity. The aggregation pipeline is powerful but verbose compared to SQL. Rejected because the relational query requirements and data integrity guarantees exceed MongoDB's strengths.

2. **Redis** — Redis provides sub-millisecond latency for read and write operations, making it ideal for caching and real-time state tracking. Its data structures (sorted sets, streams, pub/sub) could model pipeline state and event logs efficiently. However, Redis is primarily an in-memory store with optional persistence through RDB snapshots and AOF logs. Using Redis as the sole data store risks data loss on failure without careful persistence configuration, and even with persistence, it does not provide the durability guarantees of a disk-first RDBMS. Redis lacks SQL query capabilities, making ad-hoc analytical queries and reporting extremely difficult. The data model for complex relational queries (e.g., joins across projects, shots, and quality scores) would require application-level logic that SQL handles natively. Rejected as a primary store; used only as a caching layer for hot data.

3. **SQLite** — SQLite requires zero operational overhead, stores data in a single file, and provides full ACID compliance for single-writer scenarios. For a small team or prototype, SQLite would be the simplest possible choice with no server to manage. However, SQLite uses file-level locking that severely limits concurrent write throughput. CineOS has multiple concurrent writers: n8n workflows creating jobs, AI workers writing analysis results, the Telegram bot reading and writing user state, and background tasks updating learning data. SQLite's concurrency model cannot handle this workload without contention and locking errors. SQLite also lacks network access, requiring every component to access the same filesystem, which is incompatible with distributed worker deployment. Rejected because concurrent multi-process access across networked services is a hard requirement.

4. **File-based storage (JSON files, YAML, flat files)** — Storing pipeline state, project metadata, and configuration as files in a directory structure is the simplest possible approach. It is human-readable, version-controllable with git, and requires no database server. However, file-based storage provides no transactional guarantees, no concurrent access safety, no query capabilities beyond file scanning, and no referential integrity. As the number of projects and shots grows, file-based lookups become linear scans that are orders of magnitude slower than indexed database queries. There is no way to efficiently answer questions like "show me all shots across all projects that are currently in the quality gate with a score below threshold." Rejected because the query and concurrency requirements are fundamentally incompatible with file-based approaches.

## Trade-offs

We gain full ACID compliance ensuring every pipeline state transition is atomic and consistent, powerful SQL queries for reporting and auditing across all entities, JSONB flexibility for semi-structured AI results without sacrificing relational integrity, mature replication and backup tooling for disaster recovery, and a single query language (SQL) that every component can use. We accept the operational overhead of running a PostgreSQL server (backups, monitoring, vacuum management), the need for schema migration tooling (we use a migration framework), the higher memory footprint compared to SQLite, and the learning curve for team members unfamiliar with advanced SQL features like window functions, CTEs, and JSONB operators.

## Consequences

### Positive
- Every piece of persistent data has a single authoritative location, eliminating data silos and synchronization bugs across components
- ACID transactions ensure pipeline state transitions are atomic even when multiple n8n workflows execute concurrently
- JSONB columns with GIN indexes provide flexible storage for AI analysis results with performant querying inside JSON documents
- Database triggers enforce business rules (e.g., preventing state transitions to invalid states) at the data layer regardless of which component writes data
- Materialized views pre-compute expensive aggregates for dashboard queries without impacting write performance
- Row-level security policies can restrict data access per user or service without requiring application-level enforcement
- Mature backup, point-in-time recovery, and replication tooling provides production-grade data safety and disaster recovery
- PostgreSQL's extension ecosystem (pg_trgm, PostGIS, pg_stat_statements) enables advanced features without external tools

### Negative
- Schema migrations require coordination across all components that write to the database, adding deployment complexity
- PostgreSQL server requires monitoring, vacuuming, and periodic maintenance for optimal performance and disk space management
- Connection pooling must be configured and managed to handle concurrent connections from n8n, AI workers, and the bot without exhausting the connection limit
- JSONB queries, while flexible, are slower than native relational columns for structured data and cannot leverage type-specific operators
- PostgreSQL upgrades occasionally require downtime or careful rolling upgrade procedures for major version changes
- Team members must learn SQL and database design principles rather than relying on ORM abstractions alone
- A single database instance is a single point of failure without replication or failover configuration

## Future Improvements
- Implement automated schema migration testing in CI using a disposable PostgreSQL instance to catch migration errors before deployment
- Add read replicas for analytical queries and reporting to avoid impacting production write performance during heavy reporting periods
- Evaluate PostgreSQL logical replication for real-time data streaming to downstream analytics and monitoring systems
- Create a database connection pooling layer (PgBouncer) to optimize connection reuse across all services and reduce connection overhead
- Implement automated VACUUM tuning and monitoring to prevent table bloat as data volume grows over time
- Add row-level security policies as multi-tenant or multi-team access patterns emerge
- Set up automated backup verification by restoring backups to a test instance and running data integrity checks

## References
- PostgreSQL documentation: https://www.postgresql.org/docs/
- PostgreSQL JSONB documentation: https://www.postgresql.org/docs/current/datatype-json.html
- CineOS database schema: ../architecture/database-schema.md
- CineOS data flow documentation: ../architecture/data-flow.md
- PostgreSQL performance tuning guide: https://www.postgresql.org/docs/current/runtime-config-resource.html
