---
name: release-notes
description: Generate release notes — group by type, include authors and PR links, markdown output
---

## Before You Start

- [ ] Confirm the release version or release branch to generate notes for
- [ ] Identify the Jira project key
- [ ] Determine the output format: Confluence page, Slack message, email, or raw markdown
- [ ] Check if previous release notes exist for format consistency

## Workflow

1. **Fetch all tickets in the release.** Query by fixVersion:
   ```bash
   curl -sS -X POST BASE_URL/jira/search \
     -H "Content-Type: application/json" \
     -d '{"jql": "fixVersion = \"VERSION\" AND project = PROJECT_KEY ORDER BY issuetype ASC", "max_results": 200}'
   ```

2. **Enrich with git data.** Get merge commits for the release branch:
   ```bash
   curl -sS BASE_URL/git/log
   ```
   Map commits to ticket keys. Extract: author, PR number/link, merge date.

3. **Categorize tickets by type.** Group into standard release note sections:
   - **Features** — Story, New Feature issue types
   - **Bug Fixes** — Bug issue type
   - **Improvements** — Improvement, Task issue types
   - **Breaking Changes** — tickets with "breaking-change" label
   - **Internal** — Tech Debt, Chore (optional, often excluded from external notes)

4. **Format each entry.** For every ticket:
   ```
   - **[TICKET-123](jira_url/TICKET-123)**: {summary} — @{author} ([PR #{num}](pr_url))
   ```

5. **Assemble the release notes:**
   ```markdown
   # Release Notes — {version}
   **Date:** {release_date}
   **Tickets:** {total_count}
   **Contributors:** {unique_authors}

   ## Features
   - **[TICKET-123](url)**: Add payment retry logic — @alice ([PR #45](url))
   - **[TICKET-124](url)**: New dashboard widget — @bob ([PR #46](url))

   ## Bug Fixes
   - **[TICKET-130](url)**: Fix null pointer in checkout flow — @charlie ([PR #50](url))

   ## Improvements
   - **[TICKET-140](url)**: Optimize database queries for reports — @alice ([PR #52](url))

   ## Breaking Changes
   - **[TICKET-150](url)**: Migrate from v1 to v2 API format — @dave ([PR #55](url))
     - **Migration guide:** Update all clients to use `/api/v2/` endpoints

   ---
   Full changelog: [compare link](git_compare_url)
   ```

6. **Deliver the output.** Based on the requested format:
   - **Confluence**: create or update a Confluence page with the notes
   - **Slack**: format as a concise message with key highlights
   - **Raw markdown**: output directly for copy-paste

## Definition of Done

- [ ] All tickets in the release fetched and categorized by type
- [ ] Each entry includes ticket link, summary, author, and PR link
- [ ] Breaking changes highlighted with migration guidance
- [ ] Release notes formatted in clean markdown
- [ ] Output delivered in the requested format (Confluence/Slack/markdown)
