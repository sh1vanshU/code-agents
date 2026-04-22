---
name: api-security
trigger: "API security, endpoint security, authentication audit, authorization check"
---

# API Security Audit

## Workflow

1. **Authentication review**
   - Are all endpoints authenticated? (check for unprotected routes)
   - Token validation: JWT expiry, signature verification
   - API key rotation policy documented?
   - No credentials in query parameters (use headers)

2. **Authorization check**
   - Role-based access control (RBAC) implemented?
   - Privilege escalation paths?
   - Resource-level permissions (users can only access their data)

3. **Input validation**
   - All inputs sanitized (SQL injection, XSS, command injection)
   - Request size limits configured
   - Content-Type validation
   - Rate limiting per endpoint

4. **Transport security**
   - TLS enforced (no plain HTTP in production)
   - CORS configured (not wildcard)
   - Security headers: HSTS, X-Content-Type-Options, X-Frame-Options

5. **Report** with OWASP Top 10 mapping and fix recommendations
