---
name: supply-chain
trigger: "supply chain, dependency risk, package audit, npm audit, pip audit, lockfile"
---

# Supply Chain Security Audit

## Workflow

1. **Dependency inventory**
   - List all direct + transitive dependencies
   - Check for pinned versions (exact, not ranges)
   - Verify lockfile exists and is committed (package-lock.json, poetry.lock)

2. **Vulnerability scan**
   ```bash
   # Python
   pip audit
   poetry run safety check
   
   # Node.js
   npm audit
   
   # General
   trivy fs .
   ```

3. **Risk assessment**
   - Abandoned packages (no updates in 2+ years)?
   - Single-maintainer packages?
   - Typosquatting risk (similar package names)?
   - Unnecessary dependencies (can be removed)?

4. **License compliance**
   - Any copyleft licenses (GPL) in proprietary project?
   - License compatibility between dependencies?

5. **Remediation plan**
   - Prioritize by severity (CRITICAL first)
   - Provide upgrade commands
   - Flag breaking changes in major version bumps
