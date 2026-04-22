---
name: standup-report
description: Daily standup generation — yesterday done, today planned, blockers, per-person format
---

## Before You Start

- [ ] Confirm the Jira project key and team members (or use assignee filter)
- [ ] Verify git remote access for commit log
- [ ] Identify the reporting period (default: last 24 hours)
- [ ] Check if PR status and build/deploy status should be included

## Workflow

1. **Yesterday: completed work.** Fetch tickets transitioned to Done in the last 24 hours:
   ```bash
   curl -sS -X POST BASE_URL/jira/search \
     -H "Content-Type: application/json" \
     -d '{"jql": "project = PROJECT_KEY AND status changed to Done AFTER -1d", "max_results": 100}'
   ```

2. **Yesterday: git activity.** Fetch recent commits:
   ```bash
   curl -sS BASE_URL/git/log
   ```
   Filter commits from the last 24 hours. Map commit messages to ticket keys where possible.

3. **Today: planned work.** Fetch tickets currently In Progress:
   ```bash
   curl -sS -X POST BASE_URL/jira/search \
     -H "Content-Type: application/json" \
     -d '{"jql": "project = PROJECT_KEY AND status = \"In Progress\" AND sprint in openSprints()", "max_results": 100}'
   ```

4. **Blockers.** Fetch blocked tickets:
   ```bash
   curl -sS -X POST BASE_URL/jira/search \
     -H "Content-Type: application/json" \
     -d '{"jql": "project = PROJECT_KEY AND (status = Blocked OR priority = Blocker) AND sprint in openSprints()", "max_results": 50}'
   ```

5. **Enrich with CI/CD status** (if available):
   - Check latest build status from Jenkins
   - Check deployment status from ArgoCD
   - Note any failed builds or unhealthy deployments

6. **Format per-person standup.** Group all data by assignee:
   ```
   ## Daily Standup — {date}

   ### {Person Name}
   **Done yesterday:**
   - [TICKET-123] Implemented retry logic (merged PR #45)
   - [TICKET-124] Fixed null pointer in payment flow

   **Doing today:**
   - [TICKET-125] API rate limiting (In Progress)

   **Blockers:**
   - [TICKET-126] Blocked — waiting on DB migration approval

   ---
   ### Build/Deploy Status
   - Latest build: #456 SUCCESS
   - Staging: healthy (v1.2.3)
   ```

## Definition of Done

- [ ] Yesterday's completed work listed per person (Jira transitions + git commits)
- [ ] Today's planned work listed per person (In Progress tickets)
- [ ] Blockers identified with ticket keys and reasons
- [ ] CI/CD status included (build, deploy health)
- [ ] Report formatted in clean per-person markdown
