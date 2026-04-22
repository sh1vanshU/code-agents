---
name: code-injection
trigger: "injection, SQL injection, XSS, command injection, SSTI, deserialization"
---

# Code Injection Analysis

## Workflow

1. **Identify injection surfaces**
   - User inputs: forms, query params, headers, file uploads
   - External data: API responses, database reads, file contents
   - Template rendering contexts

2. **Check injection types**
   - **SQL injection**: parameterized queries? ORM usage? raw SQL with string concat?
   - **XSS**: output encoding? CSP headers? innerHTML usage?
   - **Command injection**: subprocess with shell=True? unsanitized paths?
   - **SSTI**: template engines with user-controlled input?
   - **Deserialization**: pickle/yaml.load without safe_load?
   - **Path traversal**: `..` in file paths? symlink following?

3. **Verify defenses**
   - Input validation (allowlist > blocklist)
   - Output encoding (context-appropriate: HTML, URL, JS, CSS)
   - Parameterized queries (no string interpolation in SQL)
   - CSP headers configured

4. **Report** each finding with:
   - Vulnerability type and CWE number
   - Affected file + line
   - Proof of concept (safe demonstration)
   - Fix recommendation with code example
