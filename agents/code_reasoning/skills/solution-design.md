---
name: solution-design
description: Design solutions for requirements — evaluate approaches, compare trade-offs, recommend pattern, draw sequence diagrams, API design
---

## Before You Start

- [ ] Clarify the requirement: functional (what it does) and non-functional (performance, security, reliability)
- [ ] Identify constraints: timeline, team size, existing tech stack, budget, compliance
- [ ] Understand the existing architecture: read CLAUDE.md, README, and relevant source files
- [ ] Determine the decision scope: greenfield design, extension of existing system, or migration

## Workflow

1. **Parse the requirement.** Break down into:
   - **Functional requirements**: what the system must do (user stories, acceptance criteria)
   - **Non-functional requirements**: performance targets, security needs, availability SLA
   - **Constraints**: must use existing DB, must be backwards compatible, must ship in 2 weeks
   - **Assumptions**: document anything not explicitly stated that you are assuming

2. **Evaluate candidate approaches.** Identify 2-3 viable approaches. For each:
   - Name the pattern or architecture (e.g., event-driven, CQRS, simple CRUD, saga)
   - Describe how it works at a high level
   - List which existing code it builds on vs what is new
   - Estimate implementation effort (days/weeks)

3. **Compare trade-offs.** Build a comparison matrix:
   ```
   | Criterion          | Approach A          | Approach B          | Approach C          |
   |--------------------|--------------------|--------------------|---------------------|
   | Implementation     | 3 days             | 1 week             | 2 weeks             |
   | Performance        | O(n) per request   | O(1) with cache    | O(1) amortized      |
   | Maintainability    | Simple, obvious    | Medium complexity   | High complexity      |
   | Scalability        | Limited to 1K RPS  | 10K+ RPS           | 100K+ RPS           |
   | Risk               | Low                | Medium (new infra) | High (new paradigm) |
   | Backwards compat   | Full               | Partial            | Breaking change      |
   | Testability        | Easy               | Medium             | Hard                 |
   ```

   Explain WHY each rating, not just the rating itself.

4. **Recommend an approach.** State your recommendation and the reasoning:
   - Why this approach best fits the constraints
   - What risks remain and how to mitigate them
   - What you would choose differently if constraints changed (more time, higher scale, etc.)

5. **Design the API.** For the recommended approach:
   - **REST endpoints** (if applicable):
     ```
     POST   /v1/resource          — Create
     GET    /v1/resource/{id}     — Read
     PUT    /v1/resource/{id}     — Update
     DELETE /v1/resource/{id}     — Delete
     GET    /v1/resource?filter=x — List with filtering
     ```
   - **Request/response schemas**: field names, types, required vs optional, validation rules
   - **Error responses**: status codes, error body format, common error scenarios
   - **Authentication**: which endpoints need auth, what level (read vs write)
   - **Pagination**: cursor-based vs offset-based, page size defaults and limits
   - **Versioning strategy**: URL path, header, or query parameter

6. **Draw sequence diagrams.** For the 2-3 most important flows:
   ```
   User -> API Gateway -> Auth Middleware -> Router -> Service -> Database
     |                                                    |
     |                                                    +-> Cache (check)
     |                                                    |
     |                                                    +-> External API
     |                                                    |
     |         <-- 200 OK (response body) <---------------+
   ```
   Include error paths for critical flows (what happens when the external API is down).

7. **Design the data model.** If the solution involves data storage:
   - Entity definitions with fields, types, and constraints
   - Relationships (one-to-one, one-to-many, many-to-many)
   - Indexes needed for query patterns
   - Migration strategy from current schema (if applicable)
   - Data lifecycle: creation, updates, soft delete vs hard delete, archival

8. **Plan for failure.** For each external dependency:
   - What happens when it is slow (timeout strategy)
   - What happens when it is down (fallback, circuit breaker, retry)
   - What happens when it returns unexpected data (validation, graceful degradation)
   - How the failure is communicated to the user

9. **Output the solution design.**
   ```
   ## Solution Design: {requirement summary}

   ### Requirement Summary
   {2-3 sentences describing what needs to be built and why}

   ### Approach Comparison
   {trade-off matrix from step 3}

   ### Recommended Approach
   **{Approach name}** — {1 sentence rationale}

   ### API Design
   | Method | Endpoint | Description | Auth |
   |--------|----------|-------------|------|

   ### Sequence Diagrams
   {text-based diagrams for key flows}

   ### Data Model
   {entity definitions and relationships}

   ### Error Handling
   | Failure Scenario | Detection | Response | Recovery |
   |-----------------|-----------|----------|----------|

   ### Implementation Plan
   | Step | Description | Files | Effort | Dependencies |
   |------|------------|-------|--------|-------------|
   | 1    | {first step} | {files} | {time} | None |
   | 2    | {second step} | {files} | {time} | Step 1 |

   ### Open Questions
   - {anything that needs clarification before implementation}
   ```

## Definition of Done

- [ ] Requirement broken into functional, non-functional, constraints, and assumptions
- [ ] At least 2 candidate approaches evaluated
- [ ] Trade-off matrix completed with reasoning for each rating
- [ ] Clear recommendation with rationale and risk mitigation
- [ ] API design complete with endpoints, schemas, errors, and auth
- [ ] Sequence diagrams drawn for critical flows including error paths
- [ ] Data model designed with indexes and migration strategy (if applicable)
- [ ] Failure scenarios documented with detection, response, and recovery
- [ ] Implementation plan with ordered steps, files, effort, and dependencies
