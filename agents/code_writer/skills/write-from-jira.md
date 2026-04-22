---
name: write-from-jira
description: Read Jira ticket, implement code, write tests, verify — end-to-end from ticket to working code
---

## Before You Start

- [ ] Confirm the ticket is in the correct status (e.g., "In Progress") — do not start work on a ticket still in "Backlog" or "Blocked"
- [ ] Check for linked tickets (blockers, related work, duplicates) — another team may be working on the same area
- [ ] Identify the ticket reporter and assignee — know who to ask if requirements are unclear
- [ ] Review the ticket's comments and history for context and prior decisions
- [ ] Verify you have access to all referenced systems (APIs, databases, design docs)

## Workflow

1. **Fetch the Jira ticket.** Read the ticket details to understand the requirement:
   ```bash
   curl -s ${BASE_URL}/jira/issue/KEY-123
   ```
   Extract: summary, description, acceptance criteria, attachments, linked issues.

2. **Extract and validate acceptance criteria.** Parse the ticket for:
   - Functional requirements (what the code must do)
   - Non-functional requirements (performance, security, error handling)
   - Edge cases mentioned in the description or comments
   - Any linked design documents or specifications

   **Requirement validation** — Before proceeding, check for these red flags:
   - Ambiguous language ("should handle errors gracefully" — what does gracefully mean?)
   - Missing acceptance criteria (no clear definition of "done")
   - Conflicting requirements (ticket says X, linked design doc says Y)
   - Unstated assumptions (does this require a DB migration? A config change? A feature flag?)
   - If ANY of these exist, add a comment on the ticket asking for clarification BEFORE coding

3. **Analyze the codebase.** Before writing code:
   - Identify which files, modules, and layers need changes
   - Find similar existing features to use as a pattern
   - Check for existing utilities, helpers, or base classes to reuse
   - Map data flows that will be affected

4. **Implement the feature.** Write the code:
   - Follow existing project conventions and style exactly
   - Write minimal, focused diffs — only what the ticket requires
   - Handle errors at system boundaries
   - Add type hints if the project uses them

5. **Write tests for the new code.** Create test cases covering:
   - Each acceptance criterion from the Jira ticket
   - Happy path for each new function or endpoint
   - Edge cases (empty input, null, boundary values, error paths)
   - Use the project's existing test framework and patterns

6. **Run tests to verify everything passes.**
   ```bash
   curl -s -X POST ${BASE_URL}/testing/run \
     -H "Content-Type: application/json" \
     -d '{"branch": null, "test_command": null, "coverage_threshold": 80}'
   ```
   If tests fail, fix and re-run (max 3 cycles).

7. **Run the local build.** Verify the project compiles and builds cleanly:
   Use [SKILL:local-build] to detect build tool and run build.

8. **Update the Jira ticket with a comment.** Post implementation summary:
   ```bash
   curl -s -X POST ${BASE_URL}/jira/issue/KEY-123/comment \
     -H "Content-Type: application/json" \
     -d '{"body": "Implementation complete. Files changed: [...]. Tests added: [...]. All tests passing."}'
   ```
   Include: files changed, tests added, any deviations from the original requirements.

## Edge Case Analysis Checklist

Before marking implementation complete, verify each category:

| Category | Examples | Status |
|----------|----------|--------|
| **Empty/null inputs** | Empty strings, null fields, missing optional params | Handled? |
| **Boundary values** | Zero, negative, MAX_INT, empty collections, single-element lists | Handled? |
| **Concurrent access** | Two users triggering the same action simultaneously | Handled? |
| **Partial failure** | Network timeout mid-operation, DB write succeeds but cache update fails | Handled? |
| **Duplicate requests** | Same request sent twice (idempotency) | Handled? |
| **Permission edge cases** | User with partial permissions, expired tokens mid-session | Handled? |
| **Data migration** | Does existing data in production work with the new code? | Verified? |

## Acceptance Criteria Traceability

For every acceptance criterion in the Jira ticket, you MUST have:
1. At least one test that directly validates it
2. A comment in the Jira ticket mapping criterion to test name
3. If a criterion cannot be automated, note it as "manual verification required"

## Cross-Team Impact Assessment

Before pushing code, ask:
- Does this change affect a shared library, utility, or base class? If yes, who else uses it?
- Does this change an API contract? If yes, who are the consumers?
- Does this require a config change in another service or environment?
- Does this need a feature flag for safe rollout?

## Definition of Done

- [ ] Every acceptance criterion from the Jira ticket has a corresponding test
- [ ] All tests pass, coverage meets or exceeds threshold
- [ ] Build succeeds locally
- [ ] Jira ticket updated with implementation summary
- [ ] No unaddressed edge cases from the checklist above
- [ ] Cross-team impacts identified and communicated (if any)
- [ ] Code follows existing project patterns — no new patterns introduced without justification
