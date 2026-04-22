---
name: post-deploy-update
description: Post-deployment Jira update — transition to Done, add deploy details, update fixVersion, add labels
---

## Before You Start

- [ ] Confirm the Jira ticket key
- [ ] Have deployment details ready: environment, version, timestamp
- [ ] Have CI/CD links: Jenkins build URL, ArgoCD app URL
- [ ] Know whether this is a non-prod or production deployment

## Workflow

1. **Fetch current ticket state.** Verify the ticket exists and get current status:
   ```bash
   curl -sS "BASE_URL/jira/issue/TICKET_KEY"
   ```
   Confirm the ticket is not already Done/Closed.

2. **Add deployment comment.** Post detailed deployment information:
   ```bash
   curl -sS -X POST BASE_URL/jira/issue/TICKET_KEY/comment \
     -H "Content-Type: application/json" \
     -d '{"body": "Deployment Complete\n\nEnvironment: {env}\nVersion: {version}\nTimestamp: {ISO timestamp}\nBuild: {jenkins_build_url}\nArgoCD: {argocd_app_url}\nPods: {pod_count} healthy\nDeployed by: SDLC pipeline"}'
   ```

3. **Transition ticket to Done.** Fetch transitions and move to Done:
   ```bash
   curl -sS "BASE_URL/jira/issue/TICKET_KEY/transitions"
   ```
   Find the transition ID for "Done" and execute:
   ```bash
   curl -sS -X POST BASE_URL/jira/issue/TICKET_KEY/transition \
     -H "Content-Type: application/json" \
     -d '{"transition_id": "DONE_TRANSITION_ID", "comment": "Deployed to {env} — version {version}. All SDLC steps completed."}'
   ```

4. **Update fixVersion.** Ensure the ticket has the correct release version:
   - If fixVersion is not set, note it in the comment for manual update
   - Report: "fixVersion should be set to {version}" if it needs updating

5. **Production-specific actions.** If deployed to production:
   - Add "Released" label to the ticket (note in comment for manual update)
   - Include production URL or health check endpoint in the comment
   - Note the release date for tracking

6. **Post-deploy summary:**
   ```
   ## Post-Deploy Update: TICKET_KEY

   | Field | Value |
   |-------|-------|
   | Status | Done |
   | Environment | {env} |
   | Version | {version} |
   | Build URL | {jenkins_url} |
   | ArgoCD App | {argocd_url} |
   | Deploy Time | {timestamp} |
   | Labels | Released (if prod) |
   | fixVersion | {version} |
   ```

## Definition of Done

- [ ] Deployment comment added with environment, version, timestamp, and CI/CD links
- [ ] Ticket transitioned to Done status
- [ ] fixVersion field updated or flagged for manual update
- [ ] "Released" label added for production deployments
- [ ] Post-deploy summary presented to the user
