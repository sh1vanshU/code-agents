---
name: release-tracker
description: Release tracking — tickets by fixVersion, readiness check, deploy gate
---

## Before You Start

- [ ] Confirm the release version string (e.g., `v1.2.0`)
- [ ] Verify the Jira project key
- [ ] Identify the release branch name for git cross-reference
- [ ] Confirm whether this is a readiness check or a deploy gate decision

## Workflow

1. **Fetch all tickets in the release.** Query by fixVersion:
   ```bash
   curl -sS -X POST BASE_URL/jira/search \
     -H "Content-Type: application/json" \
     -d '{"jql": "fixVersion = \"VERSION\" AND project = PROJECT_KEY", "max_results": 200}'
   ```

2. **Status breakdown.** For each ticket, extract status and categorize:
   - **Done**: ready for release
   - **In Progress**: still being worked on
   - **To Do**: not started
   - **Blocked**: has blocker flag or Blocked status
   Count tickets and story points per category.

3. **Release readiness score.** Calculate:
   - `X / Y tickets complete` (Done count / total count)
   - `Z story points remaining` (non-Done points)
   - **Ready** if all tickets are Done
   - **Not Ready** if any ticket is not Done — list the blockers

4. **Deploy gate decision.** If this is a deploy gate:
   - **PASS**: all tickets Done, no blockers
   - **FAIL**: list each non-Done ticket with key, summary, status, assignee
   - If FAIL, suggest: which tickets to remove from the release, or which to fast-track

5. **Cross-reference with git.** Check if all ticket branches are merged:
   ```bash
   curl -sS BASE_URL/git/branches
   ```
   For each ticket key, check if a branch named `feature/TICKET_KEY` or similar exists and whether it has been merged into the release branch.

6. **Present release summary:**
   ```
   ## Release: {version}
   | Status | Tickets | Story Points |
   |--------|---------|--------------|
   | Done | A | B |
   | In Progress | C | D |
   | To Do | E | F |
   | Blocked | G | H |

   Readiness: X/Y tickets complete
   Deploy Gate: PASS / FAIL
   Unmerged branches: [list]
   ```

## Definition of Done

- [ ] All tickets in release version fetched and categorized by status
- [ ] Release readiness score calculated (X/Y complete, Z points remaining)
- [ ] Deploy gate verdict provided (PASS/FAIL) with specific blockers if FAIL
- [ ] Git branch merge status cross-referenced
- [ ] Actionable recommendations provided for any blockers
