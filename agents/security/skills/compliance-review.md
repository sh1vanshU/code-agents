---
name: compliance-review
description: Review code for security compliance — encryption, data handling, auth patterns
---

## Workflow

1. **Check encryption practices:**
   - Data at rest: databases, file storage, backups
   - Data in transit: TLS/HTTPS enforced, no HTTP fallback
   - Algorithms: no MD5/SHA1 for security, no DES/RC4, use AES-256/ChaCha20
   - Key management: rotation policy, no hardcoded keys

2. **Check authentication patterns:**
   - Password hashing: bcrypt/argon2/scrypt (not MD5/SHA1/plain)
   - Session management: secure flags, httponly, samesite
   - Token handling: short-lived tokens, secure storage, rotation
   - Multi-factor authentication: available for sensitive operations

3. **Check data handling:**
   - PII: identified, classified, and protected
   - Logging: no sensitive data (passwords, tokens, PII) in logs
   - Error messages: no stack traces or internal details exposed to users
   - Data retention: defined policies, automated cleanup

4. **Check infrastructure security:**
   - Docker: non-root user, minimal base image, no secrets in layers
   - Kubernetes: network policies, resource limits, RBAC
   - CI/CD: secrets not exposed in logs, pinned action versions
   - Dependencies: lock files committed, integrity checks enabled

5. **Check security headers (web applications):**
   - Content-Security-Policy, X-Frame-Options, X-Content-Type-Options
   - Strict-Transport-Security, Referrer-Policy
   - CORS: restrictive origin policy, not wildcard

6. **Compliance summary:** checklist of pass/fail items with remediation for each failure.
