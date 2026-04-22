---
name: design-review
description: Review LLD before coding — flag risks, missing edge cases, suggest alternatives, validate patterns
---

## Before You Start

- [ ] Confirm the design is for a specific, scoped requirement — not a vague idea
- [ ] Identify who authored the design and who will implement it — tailor feedback accordingly
- [ ] Check for related RFCs, ADRs (Architecture Decision Records), or prior designs for this area
- [ ] Understand the production traffic patterns for the affected components (read vs write ratio, peak QPS, data volume)
- [ ] Know the deployment model (monolith, microservices, serverless) — this affects your pattern recommendations

## Workflow

1. **Read the Low-Level Design document.** Understand the proposed approach:
   - What is being built and why
   - Which files will be created or modified
   - What data flows and dependencies are involved
   - What tests are planned

2. **Validate architectural patterns.** Check the design against project conventions:
   - Does it follow existing patterns in the codebase? (e.g., if the project uses repository pattern, does the LLD use it too?)
   - Is the responsibility separation clean? (no god classes, no circular dependencies)
   - Are the right abstraction layers used? (not too deep, not too shallow)
   - Does it respect existing module boundaries?

3. **Flag risks.** Identify potential problems:
   - **Concurrency risks**: shared mutable state, race conditions, deadlocks
   - **Performance risks**: N+1 queries, unbounded loops, large memory allocations
   - **Security risks**: injection points, auth gaps, data exposure
   - **Reliability risks**: missing error handling, no retries, no circuit breakers
   - **Maintainability risks**: tight coupling, hidden dependencies, magic values

4. **Check for missing edge cases.** Look for unhandled scenarios:
   - Null or empty inputs
   - Boundary values (zero, max int, empty string, very long string)
   - Concurrent access (two users doing the same thing at once)
   - Partial failure (what if step 3 of 5 fails?)
   - Timeout and retry behavior
   - Idempotency (can this be safely retried?)

5. **Suggest alternatives.** If you see a better approach:
   - Explain why the current approach is problematic
   - Propose a concrete alternative with file:line references
   - Compare trade-offs: complexity, performance, maintainability
   - Only suggest alternatives for real problems — do not bikeshed

6. **Scalability assessment.** Evaluate how the design behaves under growth:
   - **Data growth**: What happens when the table/collection has 10x, 100x more rows? Are queries indexed?
   - **Traffic growth**: What happens at 10x current QPS? Are there bottlenecks (single DB connection, global lock, synchronous chain)?
   - **Team growth**: Can another team extend this without modifying your code? Is the API surface clean?
   - **Horizontal scaling**: Can this component be scaled by adding more instances? Or does it hold local state?
   - Rate each dimension: `Scales well | Needs work | Will break`

7. **Security threat model.** For any design that handles user input, auth, or data:

   | Threat | Check | Mitigation |
   |--------|-------|------------|
   | **Injection** (SQL, NoSQL, command, LDAP) | Are all inputs parameterized/sanitized? | Use parameterized queries, never string concatenation |
   | **Broken auth** | Is every endpoint authenticated? Are permissions checked at the right layer? | Enforce auth at middleware level, not per-handler |
   | **Data exposure** | Are sensitive fields (PII, tokens, passwords) ever logged, cached, or returned in errors? | Redact in logs, exclude from API responses, encrypt at rest |
   | **SSRF** | Does the design accept URLs or hostnames from user input? | Allowlist permitted domains, never fetch arbitrary URLs |
   | **Mass assignment** | Are request bodies bound directly to database models? | Use explicit DTOs/schemas, never bind raw input to models |

8. **Backward compatibility matrix.** If the design changes existing interfaces:

   | Interface | Change | Backward Compatible? | Migration Required? |
   |-----------|--------|---------------------|-------------------|
   | REST API | New required field | NO — breaks existing clients | Yes: make optional first, then required after clients update |
   | Database schema | New column | YES — if nullable with default | No |
   | Event/message format | Changed field type | NO — breaks consumers | Yes: dual-write old+new format during migration |
   | Internal function | Changed signature | Depends — check all callers | Maybe: use default params for backward compat |

   For any backward-incompatible change, require an explicit migration plan before approving.

9. **Output the design review verdict.** Conclude with one of two outcomes:

   **APPROVED** — The design is sound and ready for implementation.
   ```
   ## Design Review: APPROVED
   - Pattern: {validated pattern} — correct usage
   - Coverage: edge cases adequately handled
   - Notes: {any minor suggestions, not blocking}
   ```

   **NEEDS-CHANGES** — The design has issues that must be addressed before coding.
   ```
   ## Design Review: NEEDS-CHANGES

   ### Blocking Issues
   1. {issue}: {why it is a problem} — Fix: {concrete suggestion}
   2. {issue}: {why it is a problem} — Fix: {concrete suggestion}

   ### Missing Edge Cases
   - {scenario}: not handled — add {specific handling}

   ### Suggested Alternatives
   - {current approach} -> {better approach}: {trade-off analysis}

   ### Scalability
   - Data growth: {assessment}
   - Traffic growth: {assessment}
   - Horizontal scaling: {assessment}

   ### Security
   - {threat}: {status and mitigation}

   ### Backward Compatibility
   - {interface}: {compatible or migration plan required}
   ```

## Quality Gates Checklist

Before issuing APPROVED, verify every item:

- [ ] No architectural pattern violations (follows existing codebase conventions)
- [ ] No circular dependencies introduced
- [ ] Error handling is explicit at every system boundary
- [ ] All new APIs have clear input validation and documented error responses
- [ ] Scalability assessed — no obvious bottlenecks at 10x growth
- [ ] Security threats evaluated — no unmitigated HIGH/CRITICAL threats
- [ ] Backward compatibility confirmed or migration plan provided
- [ ] Observability considered — logging, metrics, and alerting for new paths
- [ ] Rollback plan exists — what happens if this change causes issues in production?

## Trade-Off Documentation

For every "Suggested Alternative" in the review, document the trade-off explicitly:

```
Option A: {current design approach}
  + {advantage 1}
  + {advantage 2}
  - {disadvantage 1}

Option B: {your suggested alternative}
  + {advantage 1}
  + {advantage 2}
  - {disadvantage 1}

Recommendation: {Option A or B} because {specific reasoning tied to project context}
```

Never suggest alternatives without explaining WHY — the goal is to teach the pattern, not just dictate the answer.

## Definition of Done

- [ ] Every section of the design has been reviewed (architecture, security, scalability, compatibility)
- [ ] All blocking issues have concrete fix suggestions (not just "this is wrong")
- [ ] Trade-offs are documented for every suggested alternative
- [ ] The review is actionable — the implementer knows exactly what to change
- [ ] The review tone is constructive — explain the reasoning, not just the verdict
