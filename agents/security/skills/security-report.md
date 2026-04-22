---
name: security-report
description: Generate a comprehensive security posture report for the repository
---

## Workflow

1. **Run all security checks** by invoking each skill:
   - `[SKILL:vulnerability-scan]` — OWASP Top 10 static analysis
   - `[SKILL:dependency-audit]` — CVEs, outdated packages, licenses
   - `[SKILL:secrets-detection]` — hardcoded secrets and credentials
   - `[SKILL:attack-surface]` — endpoint mapping and auth review
   - `[SKILL:compliance-review]` — encryption, data handling, infrastructure

2. **Compile findings** into a unified report:

   ### Security Posture Summary
   | Severity | Count |
   |----------|-------|
   | CRITICAL | X     |
   | HIGH     | X     |
   | MEDIUM   | X     |
   | LOW      | X     |
   | INFO     | X     |

   **Overall Risk Rating:** Critical / High / Medium / Low

3. **Top 5 Priority Fixes:** List the 5 most impactful issues to fix first, with concrete remediation steps.

4. **Positive findings:** Acknowledge security practices that are done well (encourages maintaining them).

5. **Recommendations:** Prioritized action plan:
   - Immediate (fix today): CRITICAL and HIGH findings
   - Short-term (this sprint): MEDIUM findings
   - Long-term (next quarter): LOW findings and security improvements

6. **Delegate fixes:** For each actionable finding, recommend:
   - `[DELEGATE:code-writer]` for code-level fixes
   - `[DELEGATE:code-tester]` for security test creation
   - Manual action for infrastructure or process changes
