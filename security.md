# Security Audit Findings

Audit date: 2026-04-05

---

## CRITICAL

### 1. Secrets committed in `.env`
- **File:** `.env` (tracked in git)
- **Details:** Real credentials committed to source control:
  - `REDASH_PASSWORD` — plaintext password
  - `ATLASSIAN_OAUTH_CLIENT_SECRET` — OAuth client secret
  - `CURSOR_API_KEY` — API key
  - Jenkins credentials and internal URLs
- **Action:** Untrack `.env` from git, add to `.gitignore`, rotate all exposed secrets immediately.

---

## HIGH

### 2. `.webui_secret_key` not in `.gitignore`
- **File:** `.webui_secret_key`
- **Details:** Contains a secret token, currently untracked but not gitignored. One `git add .` away from being committed.
- **Action:** Add `.webui_secret_key` to `.gitignore`.

### 3. Wildcard CORS with credentials
- **File:** `code_agents/app.py` (lines 130–136)
- **Details:** `allow_origins=["*"]` combined with `allow_credentials=True` allows any website to make authenticated cross-origin requests.
- **Action:** Restrict `allow_origins` to trusted domains, or set `allow_credentials=False`.

---

## MEDIUM

### 4. Orphan/debris files in root
| File | Issue |
|------|-------|
| `coverage.json`, `coverage_fresh.json`, `coverage_run.json` | Stale test artifacts (~1MB each) |
| `code_agents/_tmp_stub_test.py` | Temp stub file, unreferenced anywhere |
| `.coverage` | pytest-cov DB, should be gitignored |
- **Action:** Delete debris files, add `coverage*.json`, `.coverage`, and `_tmp_stub_test.py` to `.gitignore`.

### 5. Duplicate function definitions
| Function | Location 1 | Location 2 |
|----------|-----------|-----------|
| `_server_url()` | `chat/chat_server.py:14` | `cli/cli_helpers.py:32` |
| `_resolve_repo_path()` | `routers/git_ops.py:20` | `routers/testing.py:20` |
| `_check_workspace_trust()` | `chat/chat_server.py:35` | `cli/cli_helpers.py:75` |
- **Action:** Extract into shared utility module and import from both locations.

### 6. Unsafe command splitting
- **File:** `code_agents/tools/pre_push.py` (line 114)
- **Details:** `test_cmd.split()` on user-controlled env var `CODE_AGENTS_TEST_CMD`. Breaks on quoted arguments and special characters.
- **Action:** Replace with `shlex.split(test_cmd)`.

---

## LOW

### 7. Bogus URL placeholder
- **File:** `code_agents/backend.py` (line 141)
- **Details:** `https://github.com/gitcnd/cursor-agent-sdk-python/issues/XXX` — placeholder issue number never filled in.
- **Action:** Replace with actual issue URL or remove.

### 8. Hardcoded internal company URLs
- **Files:** `cli/cli.py`, `cli/cli_tools.py`, `chat/chat_slash_nav.py`, `setup/setup.py`
- **Details:** Hardcoded `example.com` / `example.com` URLs leak internal infrastructure topology.
- **Action:** Move to environment variables or replace with generic examples in source code.

---

## Security Hardening — Session 2026-04-09

The following security improvements were implemented this session:

### 9. Secret masking in command display
- **File:** `code_agents/chat/chat_commands.py`
- **Details:** Added `mask_secrets()` function that detects and masks API keys, tokens, passwords, and other sensitive values before displaying commands in the terminal. Patterns include `*_API_KEY`, `*_TOKEN`, `*_PASSWORD`, `*_SECRET`, and Bearer tokens.
- **Status:** FIXED

### 10. Path traversal prevention
- **Files:** `code_agents/app.py`, `code_agents/chat/watch_mode.py`, `code_agents/cicd/terraform_client.py`
- **Details:** All user-supplied file paths now go through `Path.resolve()` followed by a bounds check ensuring the resolved path is within the allowed project directory. Prevents `../../etc/passwd` style attacks via `X-Repo-Path` header, watch mode file paths, and terraform `var_file` parameters.
- **Status:** FIXED

### 11. SQL injection fix (parameterized LIMIT)
- **File:** `code_agents/cicd/db_client.py`
- **Details:** LIMIT clause was built via string interpolation (`f"LIMIT {limit}"`). Replaced with parameterized query (`LIMIT %s` with bind parameter) to prevent SQL injection.
- **Status:** FIXED

### 12. SSRF prevention (Slack URL validation)
- **File:** `code_agents/routers/slack_bot.py`
- **Details:** Slack `response_url` was used without validation, allowing an attacker to redirect webhook responses to arbitrary internal services. Added allowlist validation requiring the URL to match `https://hooks.slack.com/*`.
- **Status:** FIXED

### 13. PCI compliance scanner added
- **File:** `code_agents/pci_scanner.py`
- **Details:** New module that scans code and configuration for PCI-DSS compliance violations: unencrypted PAN storage, missing audit logging, weak cryptography, insecure key management, and prohibited data retention.
- **Status:** NEW

### 14. Query logging redacted
- **File:** `code_agents/cicd/db_client.py`
- **Details:** SQL queries are no longer logged in full. Query parameters are redacted in log output to prevent sensitive data (user IDs, account numbers) from appearing in log files.
- **Status:** FIXED

### 15. Atomic file writes in watch_mode
- **File:** `code_agents/chat/watch_mode.py`
- **Details:** File writes now use atomic write pattern (write to temp file, then rename) to prevent partial writes on crash or interruption, which could leave config files in a corrupted state.
- **Status:** FIXED
