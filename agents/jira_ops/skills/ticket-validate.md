---
name: ticket-validate
description: SDLC gate — validate ticket has acceptance criteria, assignee, correct status, linked docs, story points
---

## Before You Start

- [ ] Confirm the Jira ticket key to validate
- [ ] Understand which SDLC step is requesting validation (typically Step 1 before any work begins)
- [ ] Know the expected status for the ticket (usually In Progress or To Do)

## Workflow

1. **Fetch the ticket.** Get full details:
   ```bash
   curl -sS "BASE_URL/jira/issue/TICKET_KEY"
   ```

2. **Run validation checks.** Evaluate each gate criterion:

   | Check | Condition | Pass | Fail |
   |-------|-----------|------|------|
   | **Acceptance Criteria** | Description is not empty AND contains testable criteria | Has AC | No AC — cannot verify implementation |
   | **Assignee** | Assignee field is set | Assigned to {name} | Unassigned — no owner |
   | **Status** | Status is In Progress (not Done, Closed, or Cancelled) | In Progress | Wrong status: {status} |
   | **Linked Documentation** | Has linked Confluence page or description references HLD/LLD | Doc linked | No linked docs |
   | **Story Points** | Story points field is set and > 0 | {N} points estimated | No estimate |
   | **Priority** | Priority field is set | {priority} | No priority set |

3. **Check for linked Confluence pages.** Search for related docs:
   ```bash
   curl -sS -X POST BASE_URL/jira/confluence/search \
     -H "Content-Type: application/json" \
     -d '{"cql": "text ~ \"TICKET_KEY\""}'
   ```

4. **Produce verdict.** Summarize all checks:
   ```
   ## Ticket Validation: TICKET_KEY

   | Check | Result | Detail |
   |-------|--------|--------|
   | Acceptance Criteria | PASS | 4 criteria found |
   | Assignee | PASS | Alice |
   | Status | PASS | In Progress |
   | Linked Docs | FAIL | No Confluence page linked |
   | Story Points | PASS | 5 points |
   | Priority | PASS | High |

   **Verdict: FAIL** — 1 check failed
   Missing: Linked Documentation

   Action: Add HLD/LLD Confluence page link before starting implementation.
   ```

5. **Gate decision:**
   - **PASS**: All 6 checks pass. Proceed with SDLC workflow.
   - **FAIL**: List specific missing items. Do NOT proceed until resolved.
   - Report the verdict clearly so the calling workflow (e.g., full-sdlc) can act on it.

## Definition of Done

- [ ] All 6 validation checks executed against the ticket
- [ ] Clear PASS/FAIL verdict with specific missing items listed
- [ ] Actionable fix suggestions provided for each failed check
- [ ] Verdict formatted for machine-readable consumption by calling workflows
