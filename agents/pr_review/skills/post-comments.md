---
name: post-comments
description: Post inline review comments on specific files/lines in a PR
---

## Workflow

1. **Get PR files and diff:**
   ```bash
   curl -sS "${BASE_URL}/pr-review/pulls/${pr_number}/files"
   ```

2. **For each finding, post an inline comment:**
   ```bash
   curl -sS -X POST ${BASE_URL}/pr-review/pulls/${pr_number}/comments -H "Content-Type: application/json" -d '{"body":"🔴 Security: SQL injection risk...","path":"src/db.py","line":42}'
   ```

3. **Post a summary comment** with all findings:
   ```bash
   curl -sS -X POST ${BASE_URL}/pr-review/pulls/${pr_number}/review -H "Content-Type: application/json" -d '{"event":"COMMENT","body":"## Review Summary\n\n🔴 Critical: 2\n🟡 Warning: 3\n🔵 Suggestion: 1"}'
   ```
