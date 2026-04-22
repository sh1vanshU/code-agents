---
name: release
description: End-to-end release automation — branch, test, changelog, version bump, build, deploy, verify
---

## Workflow

1. **Confirm release version and options.**
   Ask: "What version?" (e.g. v8.1.0). "Skip any steps? (deploy, jira, tests)"

2. **Create release branch from main.**
   ```bash
   git fetch origin main && git checkout -b release/VERSION main
   ```
   If branch already exists, switch to it.

3. **Run tests:**
   ```bash
   curl -sS -X POST ${BASE_URL}/testing/run -H "Content-Type: application/json" -d '{"branch": "release/VERSION"}'
   ```
   If tests fail, stop and report.

4. **Generate changelog** from git log since last tag:
   ```bash
   git describe --tags --abbrev=0 && git log $(git describe --tags --abbrev=0)..HEAD --oneline --no-merges
   ```
   Group by conventional-commit prefix (feat/fix/docs). Prepend to CHANGELOG.md.

5. **Bump version** in project files: `__version__.py`, `pyproject.toml`, `package.json`, `pom.xml`.

6. **Commit and push release branch.** Confirm with user first.
   ```bash
   git add -A && git commit -m "chore: release VERSION" && git push -u origin release/VERSION
   ```

7. **Trigger build:** [DELEGATE:jenkins-cicd] with [SKILL:build]

8. **Deploy to staging:** [DELEGATE:jenkins-cicd] with [SKILL:deploy]

9. **Run sanity checks:** [DELEGATE:argocd-verify] with [SKILL:sanity-check]

10. **Update Jira tickets.** Extract ticket IDs from commits:
    [DELEGATE:jira-ops] -- transition each to Done.

11. **Report:** version, branch, changelog entries, build/deploy status, Jira updates.
    Suggest next steps: create PR, get review, merge, tag.

## CLI Shortcut

```bash
code-agents release v8.1.0
code-agents release v8.1.0 --dry-run
code-agents release v8.1.0 --skip-deploy --skip-jira
```

## Rollback

If any step fails: switch back to original branch, delete local release branch, report which steps completed.
