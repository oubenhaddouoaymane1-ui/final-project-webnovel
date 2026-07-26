# ADR-004: Why State Machine controls execution

**Status:** Accepted
**Date:** 2026-07-26
**Deciders:** CineOS Architecture Team

## Problem

CineOS shots and renders progress through a series of well-defined states during their lifecycle: a shot moves from ingested to queued to rendering to rendered to analyzing to analyzed to in-repair to repaired or approved to delivered. Multiple concurrent workflows can read and attempt to modify the state of the same shot simultaneously — a render completion callback tries to transition to "rendered" while a timeout handler tries to transition to "failed," or a quality analysis worker tries to transition to "analyzing" while a cancellation request tries to transition to "cancelled." Without explicit state management, race conditions, invalid transitions, and lost updates are inevitable. We need a mechanism that enforces valid state transitions, prevents concurrent modification conflicts, and provides a complete audit trail of every state change for debugging and compliance.

## Decision

We implement an explicit state machine pattern for all pipeline entities (shots, renders, quality gates, reviews). State transitions are defined in PostgreSQL using check constraints on state columns and enforced through database-level transition functions. Every transition is recorded in an audit log table with the previous state, new state, triggering workflow identifier, timestamp, and optional reason string. Workflows do not set state directly through UPDATE statements; they call a transition function that validates the transition is legal before applying it.

The state machine defines a finite set of valid states and a transition table specifying which states can transition to which other states. For example, a shot can move from "queued" to "rendering" but never from "delivered" to "rendering." The database function performing the transition uses a transaction with row-level locking to prevent concurrent modification, ensuring exactly one workflow wins any race to transition a given entity. The transition function returns success or failure with a descriptive message, allowing workflows to handle rejected transitions gracefully.

## Alternatives Considered

1. **Implicit state tracking** — Allow each workflow to read the current state and write its own state update without a centralized transition function. Workflows check the current state before writing and proceed if the state looks correct. This is the simplest approach and requires no database-level state machine infrastructure. However, implicit tracking creates a TOCTOU (time-of-check-to-time-of-use) race condition: two workflows can both read state as "rendering" and both attempt to transition to "rendered" or "failed" simultaneously. Without locking, the last write wins and the other transition is silently lost. Debugging state issues requires reading individual workflow execution logs to reconstruct the state history, which is error-prone and time-consuming. Rejected because race conditions and lost transitions are unacceptable for production pipeline integrity.

2. **Event sourcing only** — Store every state change as an immutable event in an append-only log. Current state is derived by replaying events from the beginning of the event stream. Event sourcing provides a perfect audit trail and makes it easy to implement temporal queries ("what was the state of this shot 3 hours ago?"). However, event sourcing adds significant architectural complexity: every read requires replaying events or maintaining a materialized projection that must be kept in sync, the current state is not directly queryable without the projection layer, and the event store itself requires careful design to avoid becoming a write bottleneck. Event sourcing also requires every component to agree on event formats and replay semantics, creating tight coupling between producers and consumers. Rejected as the sole approach; adopted partially as the audit log pattern that supplements the state machine.

3. **Database triggers only** — Implement state transition validation as PostgreSQL triggers that fire on UPDATE to the state column. Triggers can check a transition table and reject invalid transitions with an EXCEPTION. This provides database-level enforcement without requiring a separate function call from application code. However, triggers fire as part of the UPDATE execution, making error handling awkward for application code that issued the UPDATE. Triggers do not natively provide the row-level locking pattern needed to prevent concurrent transitions atomically — two concurrent UPDATEs can both pass trigger checks before either commits. Trigger logic is harder to test and version-control compared to explicit functions called by application code. Rejected as the sole mechanism; used as a supplementary safety net alongside the explicit transition function.

## Trade-offs

We gain guaranteed valid state transitions enforced at the database level regardless of which application component attempts the transition, complete audit trails of every state change for debugging and compliance reporting, race condition prevention through transactional locking with clear winner/loser semantics, and a single source of truth for what transitions are legal that is queryable as data. We accept the overhead of a database round-trip for every state transition (adding a few milliseconds of latency), the rigidity of pre-defined transitions (adding a new state requires updating the transition table, the function, and potentially check constraints), the complexity of the locking pattern in the transition function, and the need to carefully design the state machine upfront before the full set of transitions is known from production experience.

## Consequences

### Positive
- Invalid state transitions are rejected at the database level with descriptive error messages, preventing data corruption regardless of application bugs in any component
- The audit log table provides a complete, queryable history of every entity's lifecycle for debugging, compliance, and performance analysis
- Row-level locking during transitions prevents race conditions even when multiple workflows operate on the same entity concurrently
- The transition table serves as living documentation of the pipeline's legal flow, queryable by anyone with database access and visualizable as a graph
- State can be queried directly from PostgreSQL without replaying events, simplifying reads, reports, and monitoring dashboards
- Database triggers on the state column provide a supplementary safety net that catches any transition not routed through the transition function
- The audit log enables root cause analysis by showing exactly which workflow triggered each transition and why

### Negative
- Adding a new state or transition requires updating the transition table, the transition function, and potentially the check constraints, which is a schema migration
- The row-level locking pattern can create contention under very high concurrent transition rates for the same entity (though this is rare in practice)
- Error handling for rejected transitions must be implemented in every workflow that attempts a state change, adding boilerplate
- The state machine does not model side effects (e.g., "when transitioning to rendering, dispatch the render farm job") — side effects remain in workflow logic
- Debugging state machine rejections requires querying the audit log and understanding the transition table structure, adding a learning curve for new team members
- The initial design of the state machine must anticipate future states and transitions, which is difficult without full production experience

## Future Improvements
- Add a state machine visualization tool that generates a graph diagram from the transition table definition for documentation and onboarding
- Implement a notification system that alerts when entities are stuck in a state longer than a configured threshold, preventing silent pipeline stalls
- Create a migration tool that generates the transition table, transition function, and check constraints from a declarative YAML state machine definition file
- Add priority-based locking to handle scenarios where a high-priority transition (e.g., cancellation) must preempt a low-priority one
- Implement composite state machines for entities that have independent sub-state machines (e.g., a shot has an approval state and a delivery state that progress independently)
- Add metrics on transition latency, contention frequency, and rejection rates to identify bottlenecks and usability issues in the locking pattern

## References
- State pattern: https://en.wikipedia.org/wiki/State_pattern
- Finite state machine: https://en.wikipedia.org/wiki/Finite-state_machine
- PostgreSQL row locking documentation: https://www.postgresql.org/docs/current/transaction-iso.html
- CineOS state machine transition table: ../architecture/state-machine.md
- CineOS audit log schema: ../architecture/audit-log.md
