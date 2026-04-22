---
name: dependency-map
description: Map module/service dependencies — imports, API calls, shared state. Build dependency graph. Identify circular deps, tight coupling, SPOFs
---

## Before You Start

- [ ] Clarify the scope: single module, a service, or the entire system
- [ ] Identify the language and import mechanism (Python imports, JS require/import, Go packages, etc.)
- [ ] Determine what counts as a "dependency" for this analysis: code imports only, or also runtime dependencies (DB, queues, APIs)
- [ ] Check if a dependency management file exists (requirements.txt, package.json, go.mod, pom.xml)

## Workflow

1. **Inventory the modules.** List all top-level modules, packages, or services in the codebase. For each:
   - Name and purpose (one sentence)
   - Entry point file
   - Approximate size (files, lines)

2. **Trace code-level dependencies.** For each module, read import statements and function calls to build the import graph:
   ```
   module_a
     imports: module_b, module_c, external_lib_x
     called_by: module_d, module_e
   ```
   Record both directions: what it uses (outbound) and what uses it (inbound).

3. **Trace runtime dependencies.** Beyond code imports, identify:
   - **Database access**: which modules read/write which tables or collections
   - **API calls**: which modules call which internal or external HTTP/gRPC endpoints
   - **Message queues**: which modules produce/consume which topics or queues
   - **Shared config**: environment variables, config files, or feature flags read by multiple modules
   - **File system**: shared directories, temp files, log paths

4. **Build the dependency graph.** Present as a text-based directed graph:
   ```
   [cli] --imports--> [chat] --imports--> [chat_server] --calls--> [FastAPI app]
                        |                                              |
                        +--imports--> [chat_ui]                        +--reads--> [DB]
                        +--imports--> [chat_commands]
   [routers] --imports--> [backend] --calls--> [cursor API]
              --imports--> [models]
              --imports--> [config]
   ```

5. **Detect circular dependencies.** Walk the graph to find cycles:
   - Direct: A imports B, B imports A
   - Indirect: A imports B, B imports C, C imports A
   - For each cycle found, note the severity:
     - **Critical**: causes import errors or initialization order issues
     - **Warning**: works but creates tight coupling that blocks independent testing/deployment

6. **Identify tight coupling.** Flag modules that are tightly coupled:
   - **High fan-in**: module imported by many others — changing it breaks everything
   - **High fan-out**: module imports many others — it knows too much
   - **Shared mutable state**: multiple modules read/write the same global, cache key, or DB table without coordination
   - **Leaky abstractions**: module exposes internal implementation details that callers depend on

7. **Identify single points of failure (SPOFs).** Find components where:
   - Failure causes cascading failures across multiple other components
   - No fallback, retry, or circuit breaker exists
   - The component is not redundant (single instance, single region)
   - Recovery requires manual intervention

8. **Assess third-party dependencies.** For external libraries:
   - Count direct vs transitive dependencies
   - Flag unmaintained packages (no updates in 12+ months)
   - Flag packages with known security advisories
   - Identify vendor lock-in risks (hard to replace)

9. **Output the dependency report.**
   ```
   ## Dependency Map: {scope}

   ### Module Inventory
   | Module | Purpose | Files | Inbound Deps | Outbound Deps |
   |--------|---------|-------|-------------|--------------|

   ### Dependency Graph
   {text-based directed graph}

   ### Circular Dependencies
   | Cycle | Severity | Modules Involved | Recommendation |
   |-------|----------|-----------------|----------------|

   ### Tight Coupling Hotspots
   | Module | Issue | Fan-In | Fan-Out | Recommendation |
   |--------|-------|--------|---------|----------------|

   ### Single Points of Failure
   | Component | Impact if Down | Mitigation |
   |-----------|---------------|------------|

   ### Third-Party Risk
   | Package | Risk | Reason | Alternative |
   |---------|------|--------|-------------|
   ```

## Definition of Done

- [ ] All modules inventoried with purpose and size
- [ ] Import-level dependency graph built with both directions (uses / used-by)
- [ ] Runtime dependencies mapped (DB, APIs, queues, shared config)
- [ ] Circular dependencies detected and classified by severity
- [ ] Tight coupling hotspots identified with fan-in/fan-out counts
- [ ] Single points of failure flagged with impact and mitigation
- [ ] Third-party dependency risks assessed
- [ ] Text-based dependency graph included
