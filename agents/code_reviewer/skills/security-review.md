---
name: security-review
description: Review code for OWASP top 10, auth issues, injection vulnerabilities
---

## Workflow

1. **Identify the attack surface.** Read the code and map all entry points: API endpoints, form handlers, file uploads, URL parameters, headers, cookies.

2. **Check for injection vulnerabilities (OWASP A03).**
   - SQL injection: look for string interpolation in SQL queries instead of parameterized queries
   - Command injection: look for `os.system()`, `subprocess.call()` with user input
   - XSS: look for unescaped user input rendered in HTML responses
   - LDAP/XML injection: look for user input in LDAP filters or XML parsers

3. **Check authentication and authorization (OWASP A01, A07).**
   - Missing auth checks on endpoints
   - Broken access control: can user A access user B's data?
   - Hard-coded credentials or API keys in source code
   - Weak password requirements or missing rate limiting
   - Session management issues: insecure cookies, missing expiration

4. **Check for sensitive data exposure (OWASP A02).**
   - Secrets in logs (passwords, tokens, PII)
   - Missing encryption for sensitive data at rest or in transit
   - Verbose error messages leaking internal details
   - API responses returning more data than needed

5. **Check for security misconfiguration (OWASP A05).**
   - CORS set to `*` (allow all origins)
   - Debug mode enabled in production
   - Default credentials or unnecessary features enabled
   - Missing security headers (CSP, HSTS, X-Frame-Options)

6. **Check for insecure dependencies (OWASP A06).**
   - Known vulnerable library versions in requirements.txt, package.json, pom.xml
   - Outdated frameworks with known CVEs

7. **Report each finding** with severity, file:line, explanation, and concrete fix:
   ```
   CRITICAL: SQL Injection in user_search()
   File: src/api/users.py:42
   Problem: User input interpolated directly into SQL query
   Fix: Use parameterized queries with placeholders
   ```

8. **Summarize** with a count by severity and an overall security posture assessment.
