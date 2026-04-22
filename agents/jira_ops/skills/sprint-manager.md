---
name: sprint-manager
description: Sprint management — list sprints, track velocity, burndown analysis, sprint health
---

## Before You Start

- [ ] Confirm the Jira project key and board ID
- [ ] Verify Jira credentials are configured (`JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`)
- [ ] Identify whether the user wants to view, create, or modify sprints
- [ ] Check if story points field is configured in the project

## Workflow

1. **List active and future sprints.** Query open sprints via JQL:
   ```bash
   curl -sS -X POST BASE_URL/jira/search \
     -H "Content-Type: application/json" \
     -d '{"jql": "sprint in openSprints() AND project = PROJECT_KEY", "max_results": 100}'
   ```
   Parse the response to group tickets by sprint name.

2. **Sprint health check.** For the active sprint, calculate:
   - **Total tickets** and **story points** in the sprint
   - **Status breakdown**: Done / In Progress / To Do (count and points)
   - **% complete** by ticket count and by story points
   - **Days remaining**: compare sprint end date to today
   - **At-risk tickets**: In Progress tickets with no recent activity (>3 days), or To Do tickets in the second half of the sprint

3. **Track velocity.** Query recently closed sprints to compute velocity:
   ```bash
   curl -sS -X POST BASE_URL/jira/search \
     -H "Content-Type: application/json" \
     -d '{"jql": "sprint in closedSprints() AND project = PROJECT_KEY AND status = Done ORDER BY updated DESC", "max_results": 200}'
   ```
   Group by sprint, sum story points per sprint. Report last 3-5 sprints and average velocity.

4. **Burndown analysis.** Compare progress against ideal burndown:
   - **Ideal**: total points / sprint days * days elapsed
   - **Actual**: points completed so far
   - Verdict: **On Track** (within 10% of ideal), **Behind** (>10% below), **Ahead** (>10% above)
   - If behind, list the tickets that are blocking progress

5. **Move tickets between sprints** (if requested):
   - Identify tickets to move and target sprint
   - Update each ticket's sprint field
   - Add a comment explaining why the ticket was moved
   ```bash
   curl -sS -X POST BASE_URL/jira/issue/TICKET_KEY/comment \
     -H "Content-Type: application/json" \
     -d '{"body": "Moved to Sprint X — reason: {reason}"}'
   ```

6. **Present sprint summary** in a structured table:
   ```
   ## Sprint: {name} ({start} - {end})
   | Metric | Value |
   |--------|-------|
   | Total Tickets | X |
   | Story Points | Y |
   | Done | A (B pts) |
   | In Progress | C (D pts) |
   | To Do | E (F pts) |
   | % Complete | G% |
   | Days Remaining | H |
   | Burndown | On Track / Behind / Ahead |
   | Velocity (avg) | Z pts/sprint |
   ```

## Definition of Done

- [ ] Active sprint health reported with % complete and days remaining
- [ ] At-risk tickets identified with specific reasons
- [ ] Velocity calculated from recent closed sprints
- [ ] Burndown verdict provided (on track / behind / ahead)
- [ ] Any requested ticket moves completed with comments
