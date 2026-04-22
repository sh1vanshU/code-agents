# Security Agent

Head of Cybersecurity Engineer — finds vulnerabilities, misconfigurations, and supply-chain risks.

## Capabilities

- **OWASP Top 10** static analysis (injection, XSS, SSRF, broken auth)
- **Dependency audit** — CVEs, outdated packages, license compliance
- **Secrets detection** — hardcoded API keys, tokens, credentials
- **Attack surface mapping** — endpoints, auth boundaries, input validation
- **Compliance review** — encryption, data handling, infrastructure security
- **Security report** — comprehensive posture summary with prioritized action plan

## Skills

| Skill | Description |
|-------|-------------|
| `vulnerability-scan` | OWASP Top 10 static analysis |
| `dependency-audit` | CVE, license, and outdated package checks |
| `secrets-detection` | Hardcoded secrets and credential detection |
| `attack-surface` | Endpoint mapping and auth review |
| `compliance-review` | Encryption, data handling, infrastructure checks |
| `security-report` | Full security posture report |

## Usage

```bash
# Via chat
code-agents chat
/security Run a full security scan on this repo

# Via CLI
code-agents chat -a security "Scan for hardcoded secrets"

# Via API
curl -X POST http://localhost:8000/v1/agents/security/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Run a security audit"}]}'
```

## Delegation

- **Read-only** — never modifies files (permission_mode: default, mode: ask)
- Delegates to `code-writer` for applying fixes
- Delegates to `code-tester` for writing security tests
- Delegates to `code-reviewer` for deeper review context

## Integrations

Uses existing modules:
- `code_agents/analysis/security_scanner.py` — OWASP static analysis engine
- `code_agents/dependency_audit.py` — CVE and license auditing
