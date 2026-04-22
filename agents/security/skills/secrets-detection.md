---
name: secrets-detection
description: Detect hardcoded secrets, API keys, tokens, and credentials in code
---

## Workflow

1. **Scan all source files** for patterns indicating hardcoded secrets:
   - API keys: `AKIA...`, `sk-...`, `ghp_...`, `xoxb-...`
   - Passwords: `password = "..."`, `passwd`, `secret`
   - Tokens: `token = "..."`, `bearer ...`, `jwt ...`
   - Connection strings: `postgres://user:pass@...`, `mongodb://...`
   - Private keys: `-----BEGIN RSA PRIVATE KEY-----`
   - AWS credentials: access key IDs, secret access keys

2. **Check configuration files:**
   - `.env` files committed to git (should be in `.gitignore`)
   - `docker-compose.yml` with inline credentials
   - CI/CD configs (`.github/workflows/`, `Jenkinsfile`) with secrets
   - Kubernetes manifests with plaintext secrets (not sealed/external)

3. **Check git history** for leaked secrets:
   ```bash
   git log --all --diff-filter=A -p -- "*.env" "*.key" "*.pem"
   git log --all -S "password" --oneline
   ```

4. **For each finding:**
   - Location: `file:line`
   - Secret type: API key, password, token, connection string, private key
   - Risk: what access this secret grants
   - Fix: use environment variables, vault, or sealed secrets instead

5. **Check for proper secret management:**
   - `.gitignore` includes `.env`, `*.key`, `*.pem`
   - Application reads secrets from env vars, not hardcoded values
   - CI/CD uses secret management (GitHub Secrets, Jenkins credentials, etc.)
