---
name: dependency-audit
description: Audit dependencies for CVEs, outdated versions, and license issues
---

## Workflow

1. **Detect the package ecosystem:**
   - Python: `pyproject.toml`, `requirements.txt`, `Pipfile`
   - Java: `pom.xml`, `build.gradle`
   - JavaScript: `package.json`, `package-lock.json`
   - Go: `go.mod`

2. **Run the DependencyAuditor:**
   ```python
   from code_agents.dependency_audit import DependencyAuditor
   auditor = DependencyAuditor(cwd=".")
   report = auditor.audit()
   ```

3. **Check for known CVEs** against the built-in vulnerability database and external sources:
   - Compare installed versions against known vulnerable ranges
   - Flag CRITICAL CVEs (Log4Shell, Spring4Shell, etc.) with highest priority
   - For each CVE: report the package, installed version, fixed version, and severity

4. **Check for outdated packages:**
   - Flag packages more than 2 major versions behind
   - Flag packages with no updates in 2+ years (potential abandonment)
   - Prioritize: security-critical packages (crypto, auth, web frameworks)

5. **License compliance:**
   - Flag copyleft licenses (GPL, AGPL) in commercial projects
   - Flag unknown or missing licenses
   - Report license distribution summary

6. **Supply chain risks:**
   - Flag packages with very few maintainers
   - Flag packages recently transferred to new owners
   - Flag typosquatting candidates (similar names to popular packages)

7. **Report format:**
   | Package | Version | Issue | Severity | Fix |
   |---------|---------|-------|----------|-----|
   | example | 1.2.3   | CVE-2024-XXX | HIGH | Upgrade to 1.2.4+ |
