---
name: system-analysis
description: Analyze codebase for a requirement — identify files, data flows, dependencies, and tests needed
---

## Before You Start

- [ ] Clarify the scope: is this a new feature, a modification, or a refactor? Each requires different analysis depth
- [ ] Identify the system layers involved (API gateway, service layer, data layer, async workers, caches)
- [ ] Check for recent changes in the same area — ongoing work by other teams creates merge risk
- [ ] Know the deployment topology: which services own which data, what communication patterns exist (sync REST, async events, shared DB)

## Workflow

1. **Understand the requirement.** Parse the user's request to identify:
   - What functionality needs to be added or changed
   - Which system layers are involved (API, service, data, UI)
   - Any constraints or non-functional requirements mentioned

2. **Map the affected files.** Read the codebase to identify:
   - Files that need direct modification (source code changes)
   - Files that need indirect updates (imports, configs, registrations)
   - New files that need to be created
   - Test files that need new or updated tests

3. **Trace data flows.** For each affected component:
   - Entry point: where does the request/data come in?
   - Processing: which functions/methods handle the logic?
   - Storage: what databases, caches, or files are written?
   - Output: what response or side effect is produced?
   - Draw the flow: `A -> B -> C -> D` with file:function references

4. **Identify dependencies.** Map what the change depends on and what depends on it:
   - Upstream dependencies: libraries, services, configs this code uses
   - Downstream consumers: other modules, services, or APIs that call this code
   - Shared state: databases, caches, environment variables, global config
   - External integrations: third-party APIs, message queues, file systems

5. **Assess test requirements.** Determine what tests are needed:
   - Unit tests: which new functions need test coverage?
   - Integration tests: which component interactions need testing?
   - Edge cases: what boundary conditions, error paths, and null cases must be covered?
   - Existing tests: which current tests might break and need updates?

6. **Output structured LLD.** Present the analysis as a Low-Level Design document:

   ```
   ## Low-Level Design: {requirement summary}

   ### Files to Change
   | File | Change Type | Description |
   |------|------------|-------------|
   | path/to/file.py | MODIFY | Add new handler for X |
   | path/to/new.py | CREATE | New service class for Y |

   ### Data Flow
   Request -> Router (file:line) -> Service (file:line) -> Repository (file:line) -> DB

   ### Dependencies
   - Upstream: {library}, {service}
   - Downstream: {consumer module}, {API endpoint}
   - Shared state: {database table}, {env var}

   ### Tests Needed
   - [ ] Unit: test_{function} in test_{module}.py
   - [ ] Integration: test_{flow} end-to-end
   - [ ] Edge cases: {null input, empty list, timeout}

   ### Risks
   - {risk description} — mitigation: {approach}

   ### Dependency Graph
   ```
   [changed module] --imports--> [module A] --imports--> [module B]
                     <--called-by-- [module C]
                     --writes-to--> [database/table]
                     --emits--> [event/message]
   ```

   ### Performance Considerations
   - Hot path: {yes/no — is this in the critical request path?}
   - Expected latency impact: {none / +Xms per request}
   - Data volume: {how much data flows through this path}
   - Bottleneck risk: {identified bottleneck or "none expected"}
   ```

## Dependency Graph Analysis

Go beyond listing imports. Trace the full dependency chain:

1. **Direct dependencies**: What does the changed code import/call?
2. **Transitive dependencies**: What do THOSE modules depend on? (stop at 2 levels deep unless risk warrants more)
3. **Reverse dependencies**: What code imports/calls the changed module? These are the consumers that may break.
4. **Data dependencies**: What database tables, cache keys, config values, or env vars does this code read/write?
5. **Runtime dependencies**: What services must be running for this code to work? (databases, message queues, external APIs)

Present as a directed graph with edge labels (`imports`, `calls`, `reads`, `writes`, `emits`, `consumes`).

## Data Flow Tracing

For each affected flow, trace the complete path:

```
[Entry point] -> [Validation] -> [Business logic] -> [Data access] -> [Side effects] -> [Response]
     |                |                |                  |                |
     v                v                v                  v                v
  Request schema   Input rules    Core algorithm     DB/cache/file   Events, logs,
  validation       applied        executed           accessed         notifications
```

At each step, note: What can go wrong? What error is returned? Is the error logged?

## Performance Bottleneck Identification

Check for these common patterns in the affected code:

| Pattern | Risk | Detection |
|---------|------|-----------|
| **N+1 queries** | O(N) DB calls where 1 would suffice | Loop containing a DB call; missing `JOIN` or batch fetch |
| **Unbounded result sets** | Memory exhaustion, slow responses | Query without `LIMIT`, list without pagination |
| **Synchronous external calls** | Request latency tied to slowest dependency | HTTP/gRPC calls in the request path without timeout |
| **Missing index** | Full table scan on every query | `WHERE` clause on unindexed column |
| **Large object serialization** | CPU spike and memory pressure | Serializing entire entity graphs instead of projections |
| **Lock contention** | Thread starvation under load | `synchronized`, mutex, or `SELECT FOR UPDATE` in hot path |

## Definition of Done

- [ ] All affected files identified with change type (CREATE, MODIFY, DELETE)
- [ ] Data flow traced end-to-end with file:line references
- [ ] Dependency graph mapped (both directions: what it uses, what uses it)
- [ ] Performance bottlenecks assessed for the affected path
- [ ] Test requirements specified with concrete test names and file locations
- [ ] Risks listed with severity and mitigation strategy
- [ ] LLD document is specific enough for code-writer to implement without further questions
