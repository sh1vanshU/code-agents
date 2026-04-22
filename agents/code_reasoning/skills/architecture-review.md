---
name: architecture-review
description: Review system architecture — layers, components, dependencies, API contracts, deployment topology
---

## Before You Start

- [ ] Determine review scope: entire system, a single service, or a specific subsystem
- [ ] Identify the tech stack: languages, frameworks, databases, message brokers, caches
- [ ] Check for existing architecture docs (CLAUDE.md, README.md, docs/, ADRs)
- [ ] Understand the deployment model: monolith, microservices, serverless, hybrid

## Workflow

1. **Read project context files.** Start with `CLAUDE.md`, `README.md`, `docs/architecture.md`, or any ADR (Architecture Decision Record) directories. These give you the intended architecture before you verify against the actual code.

2. **Identify system layers.** Map the codebase into architectural layers:
   - **Presentation**: API routes, controllers, CLI handlers, UI components
   - **Application**: Service classes, use cases, orchestrators, command handlers
   - **Domain**: Business logic, entities, value objects, domain events
   - **Infrastructure**: Database access, external API clients, message producers/consumers, file I/O
   - **Cross-cutting**: Auth, logging, config, error handling, middleware

3. **Map component boundaries.** For each major component:
   - Name and single-sentence purpose
   - Public interface (exported functions, API endpoints, event contracts)
   - Internal structure (key files, classes, patterns used)
   - Size: approximate lines of code, number of files

4. **Trace dependency directions.** Build a component dependency diagram:
   ```
   [Presentation] --> [Application] --> [Domain]
        |                  |
        v                  v
   [Infrastructure]   [Infrastructure]
   ```
   Flag any violations: does infrastructure import domain? Does presentation bypass application?

5. **Review API contracts.** For each public API (REST, gRPC, events, CLI):
   - Endpoint/topic name and HTTP method
   - Request/response schemas (or reference to Pydantic models, protobuf, etc.)
   - Authentication and authorization requirements
   - Rate limits, pagination, versioning strategy
   - Error response format and codes

6. **Analyze deployment topology.** Document:
   - How many deployable units (services, lambdas, containers)
   - Communication patterns: sync (HTTP/gRPC) vs async (queues/events)
   - Data stores: which service owns which database/table
   - Shared resources: caches, config services, secret managers
   - External dependencies: third-party APIs, CDNs, DNS

7. **Assess architectural qualities.** Evaluate against key attributes:
   | Quality | Assessment | Evidence |
   |---------|-----------|----------|
   | **Modularity** | High/Medium/Low | Are boundaries clean? Can you replace a component? |
   | **Testability** | High/Medium/Low | Are dependencies injectable? Are there seams for mocking? |
   | **Scalability** | High/Medium/Low | Stateless services? Horizontal scaling possible? |
   | **Observability** | High/Medium/Low | Structured logging? Metrics? Tracing? Health checks? |
   | **Security** | High/Medium/Low | Auth at boundaries? Secrets management? Input validation? |

8. **Identify architectural risks.** Flag:
   - Single points of failure (SPOF)
   - Missing circuit breakers or timeouts on external calls
   - Tight coupling between components that should be independent
   - Inconsistent patterns across similar components
   - Missing or outdated documentation vs actual code

9. **Produce architecture document.** Output a structured review:
   ```
   ## Architecture Review: {system name}

   ### System Overview
   {1-2 paragraph summary of what the system does and how}

   ### Layer Diagram
   {text-based diagram showing layers and their relationships}

   ### Component Inventory
   | Component | Layer | Purpose | Key Files | Dependencies |
   |-----------|-------|---------|-----------|-------------|

   ### API Contracts
   | Endpoint | Method | Auth | Request | Response |
   |----------|--------|------|---------|----------|

   ### Deployment Topology
   {text-based diagram showing services, databases, queues, external deps}

   ### Quality Assessment
   {table from step 7}

   ### Risks & Recommendations
   | Risk | Severity | Recommendation |
   |------|----------|----------------|
   ```

## Definition of Done

- [ ] All architectural layers identified and mapped to code directories
- [ ] Component inventory complete with purpose, boundaries, and dependencies
- [ ] Dependency directions verified — violations flagged
- [ ] API contracts documented with schemas and auth requirements
- [ ] Deployment topology mapped including data stores and communication patterns
- [ ] Quality attributes assessed with evidence from the codebase
- [ ] Architectural risks identified with severity and recommendations
- [ ] Text-based diagrams included for layer structure and deployment topology
