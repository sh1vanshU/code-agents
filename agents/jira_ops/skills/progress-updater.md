---
name: progress-updater
description: Auto-comment SDLC progress on Jira ticket — status transitions after each step
---

## Before You Start

- [ ] Confirm the Jira ticket key to update
- [ ] Identify which SDLC step just completed and its result (PASS/FAIL)
- [ ] Have the relevant details ready: build number, version, test results, review findings
- [ ] Know the current ticket status and the expected next status

## Workflow

1. **Determine the update type.** Based on the SDLC step that just completed:

   | SDLC Step | Comment Template | Transition |
   |-----------|-----------------|------------|
   | Ticket Validated | Ticket validation PASSED — all checks green | To Do -> In Progress |
   | System Analysis | System analysis complete — {N} files identified, LLD ready | — |
   | Design Review | Design review {APPROVED/NEEDS-CHANGES} — {details} | — |
   | Implementation | Code implementation complete — {N} files changed, {M} lines | — |
   | Tests | Tests {PASSED/FAILED} — {pass}/{total} tests, {coverage}% coverage | — |
   | Security Review | Security review {PASSED/FAILED} — {N} findings ({critical} critical) | — |
   | Code Review | Code review {APPROVED/REQUEST_CHANGES} — {N} findings, {resolved} resolved | In Progress -> In Review |
   | Build | Build #{number} {SUCCESS/FAILED} — version {version} | — |
   | Deploy | Deployed to {env} — version {version}, {pod_count} pods healthy | — |
   | QA Regression | QA regression {PASSED/FAILED} — {details} | — |
   | Done | All SDLC steps complete — ready for production | In Review -> Done |

2. **Post the comment.** Add a structured comment to the ticket:
   ```bash
   curl -sS -X POST BASE_URL/jira/issue/TICKET_KEY/comment \
     -H "Content-Type: application/json" \
     -d '{"body": "SDLC Progress Update\n\nStep: {step_name}\nResult: {PASS/FAIL}\nDetails: {details}\nTimestamp: {ISO timestamp}"}'
   ```

3. **Transition the ticket** (if the step triggers a status change):
   First, fetch available transitions:
   ```bash
   curl -sS "BASE_URL/jira/issue/TICKET_KEY/transitions"
   ```
   Then transition to the appropriate status:
   ```bash
   curl -sS -X POST BASE_URL/jira/issue/TICKET_KEY/transition \
     -H "Content-Type: application/json" \
     -d '{"transition_id": "TRANSITION_ID", "comment": "Auto-transitioned by SDLC pipeline — {step} {result}"}'
   ```

4. **Handle failures.** If the SDLC step FAILED:
   - Post the failure details as a comment with error specifics
   - Do NOT transition the ticket forward
   - Add a comment noting what needs to be fixed before retrying
   - Format: "SDLC step {name} FAILED — {error details}. Fix required before proceeding."

5. **Cumulative progress tracking.** Include a running summary in each comment:
   ```
   SDLC Pipeline Progress:
   [1] Ticket Validated  — PASS
   [2] System Analysis   — PASS
   [3] Design Review     — PASS
   [4] Implementation    — PASS
   [5] Tests             — PASS
   [6] Security Review   — PASS
   [7] Code Review       — IN PROGRESS  <-- current step
   ```

## Definition of Done

- [ ] Jira comment posted with step name, result, and details
- [ ] Ticket transitioned to correct status (if applicable)
- [ ] Failure details clearly documented with fix suggestions
- [ ] Cumulative progress summary included in comment
