---
name: webhook-handler
description: Handle incoming PR webhook events — auto-review on PR open
---

## Trigger Conditions

This skill is triggered by the webhook endpoint when:
- A PR is opened (action: opened)
- A PR is updated with new commits (action: synchronize)
- A review is requested (action: review_requested)

## Workflow

1. **Parse webhook payload:** Extract PR number, action, author, branch.

2. **Skip conditions:**
   - Draft PRs (skip unless explicitly requested)
   - PRs by bots (dependabot, renovate)
   - PRs with [skip-review] in title

3. **Run auto-review:** Invoke [SKILL:auto-review] with the extracted PR number.

4. **Post review** on the PR with findings.
