# Atlassian MCP (Jira + Confluence) — OAuth 2.0 (3LO) only

This example uses **Atlassian Cloud OAuth 2.0 (3LO)** only — the **same pattern** as the **Cursor Atlassian integration**: user signs in in the **browser**, approves access, and Atlassian **redirects to your callback URL** with an **authorization code**. Your app exchanges that code for **access** (and optionally **refresh**) tokens, then calls **Atlassian Rovo MCP** with `Authorization: Bearer …`.

Two ways to run that flow here:

| Flow | What it does |
|------|----------------|
| **CLI** (`atlassian_mcp_client.py` + `atlassian_oauth.py`) | Starts a tiny local HTTP server for the callback, opens the browser automatically (good for scripts). |
| **Web “plugin”** (`atlassian_oauth_server.py`) | FastAPI app: home page → **Sign in with Atlassian** → same OAuth redirect → callback saves tokens (like a small hosted integration). |

Use **one** callback URL in the Developer Console for the flow you choose (paths differ: CLI default vs web server — see below).

References:

- [Implementing OAuth 2.0 (3LO)](https://developer.atlassian.com/cloud/oauth/getting-started/implementing-oauth-3lo/)
- [Refresh tokens](https://developer.atlassian.com/cloud/oauth/getting-started/refresh-tokens/)
- [Rovo MCP](https://support.atlassian.com/rovo/docs/getting-started-with-the-atlassian-remote-mcp-server/) (endpoint `https://mcp.atlassian.com/v1/mcp`)

## 1. Create an OAuth app (Developer Console)

1. Open [Atlassian Developer Console](https://developer.atlassian.com/console/myapps/) → your app (or create one).
2. **Authorization** → OAuth 2.0 (3LO) → **Configure**.
3. **Callback URL**: must match what this client uses, e.g. **`http://127.0.0.1:8766/callback`** (scheme, host, port, and path must match **exactly**).
4. **Permissions**: add the Jira / Confluence (and any other) APIs your scopes require.
5. Copy **Client ID** and **Client secret** from **Settings**.

## 2. Scopes

Set **`ATLASSIAN_OAUTH_SCOPES`** to a space-separated list of scopes your app was granted. Include product scopes you need (see [Determining scopes](https://developer.atlassian.com/cloud/oauth/getting-started/determining-scopes)).

For **refresh tokens** (recommended), include **`offline_access`** in the scope string (see [Refresh tokens](https://developer.atlassian.com/cloud/oauth/getting-started/refresh-tokens/)).

Example (adjust to your app’s enabled APIs):

```bash
export ATLASSIAN_OAUTH_SCOPES="offline_access read:jira-user read:jira-work read:confluence-content.all"
```

## 3a. Web sign-in (with Open WebUI / Code Agents on port 8000)

**Recommended:** Register callback **`https://code-agents.example.com:8000/oauth/atlassian/callback`** (or your `HOST`/`PORT`).
Set **`ATLASSIAN_OAUTH_CLIENT_ID`**, **`ATLASSIAN_OAUTH_CLIENT_SECRET`**, **`ATLASSIAN_OAUTH_SCOPES`** in `.env`, then start Code Agents (`poetry run code-agents`). Open:

**`http://localhost:8000/oauth/atlassian/`**

Click **Sign in with Atlassian** → same redirect/callback as the Cursor-style flow. Tokens are saved to the **same file** as the CLI (`~/.code-agents-atlassian-oauth.json` by default).

Open WebUI (e.g. `http://localhost:8080`) stays on **Chat**; use another tab for **`/oauth/atlassian/`** on port **8000** — same host as the OpenAI base URL without `/v1`.

If you start the stack with **`./scripts/start-with-open-webui.sh`**, **`OPEN_WEBUI_PUBLIC_URL`** is set to **`http://localhost:8080`** before Code Agents starts so the post-login page links to Open WebUI. With **`poetry run code-agents`** only, add **`OPEN_WEBUI_PUBLIC_URL`** to `.env` if you want the same link (see `.env.example`).

**Standalone** (optional): `poetry run uvicorn examples.atlassian_oauth_server:app --host 127.0.0.1 --port 8766` — register callback **`http://127.0.0.1:8766/oauth/atlassian/callback`** instead.

Optional behind a reverse proxy: set **`ATLASSIAN_OAUTH_PUBLIC_BASE_URL`** to your public origin so `redirect_uri` matches the Developer Console.

## 3. Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ATLASSIAN_OAUTH_CLIENT_ID` | yes | OAuth client ID from the Developer Console |
| `ATLASSIAN_OAUTH_CLIENT_SECRET` | yes | OAuth client secret |
| `ATLASSIAN_OAUTH_SCOPES` | yes | Space-separated scopes (include `offline_access` for refresh) |
| `ATLASSIAN_OAUTH_REDIRECT_URI` | no | CLI-only: defaults to `http://127.0.0.1:8766/callback` if unset; must match Callback URL in the console **exactly** |
| `CODE_AGENTS_PUBLIC_BASE_URL` | no | Public origin of Code Agents (e.g. `https://code-agents.example.com:8000` or your tunnel). Used for OAuth redirect and docs; Open WebUI uses this + `/v1`. |
| `ATLASSIAN_CLOUD_SITE_URL` | no | Your Jira/Confluence site, e.g. `https://acme.atlassian.net` — **not** the OAuth callback host. |
| `ATLASSIAN_OAUTH_TOKEN_CACHE` | no | Path to JSON token cache (default: `~/.code-agents-atlassian-oauth.json`) |
| `ATLASSIAN_MCP_URL` | no | MCP URL (default: `https://mcp.atlassian.com/v1/mcp`) |
| `SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE` | no | Path to a PEM CA bundle; use if you see `CERTIFICATE_VERIFY_FAILED` when exchanging the OAuth code (common with corporate TLS inspection) |
| `CODE_AGENTS_HTTPS_VERIFY` / `ATLASSIAN_OAUTH_HTTPS_VERIFY` | no | Set to `0` / `false` to disable TLS verification for Atlassian token HTTP calls only (**insecure**; local troubleshooting). Prefer fixing `SSL_CERT_FILE` instead. |
| `OPEN_WEBUI_PUBLIC_URL` / `OPEN_WEBUI_URL` | no | Open WebUI origin (e.g. `http://localhost:8080`). Shown on `/oauth/atlassian/` and used on the “Signed in” page so you are not sent to `/` on port 8000. **`scripts/start-with-open-webui.sh`** sets this to `http://localhost:8080` by default. |
| `ATLASSIAN_OAUTH_SUCCESS_REDIRECT` | no | After a **successful** token save, respond with **HTTP 302** to this URL (e.g. `http://localhost:8080/`) instead of the HTML “Signed in” page. The **start-with-open-webui** script defaults this to `OPEN_WEBUI_PUBLIC_URL` so the browser returns to chat. |


## 4. Install and run

```bash
cd /path/to/code-agents
poetry install --with dev

export ATLASSIAN_OAUTH_CLIENT_ID="your-client-id"
export ATLASSIAN_OAUTH_CLIENT_SECRET="your-client-secret"
export ATLASSIAN_OAUTH_SCOPES="offline_access read:jira-user read:jira-work read:confluence-content.all"
# Optional: must match Developer Console callback URL
# export ATLASSIAN_OAUTH_REDIRECT_URI="http://127.0.0.1:8766/callback"

poetry run python examples/atlassian_mcp_client.py --list-tools
```

First run opens a browser for login; tokens are cached for later runs. Force a new login:

```bash
poetry run python examples/atlassian_mcp_client.py --force-login --list-tools
```

Clear cached tokens:

```bash
poetry run python examples/atlassian_mcp_client.py --clear-token-cache
```

Call a tool (names come from `--list-tools`):

```bash
poetry run python examples/atlassian_mcp_client.py \
  --tool "<tool_name>" \
  --args '{"limit": 5}'
```

## 5. Files

| File | Role |
|------|------|
| `examples/atlassian_oauth.py` | OAuth authorize URL, localhost callback server, code exchange, refresh, token cache |
| `examples/atlassian_mcp_client.py` | Gets access token via OAuth, connects MCP Streamable HTTP, lists/calls tools |

## 6. Security

- Do **not** commit `ATLASSIAN_OAUTH_CLIENT_SECRET` or token cache files.
- Token cache is chmod `600` where supported.
- This is **not** your Cursor API key; it is **Atlassian OAuth** for your Developer Console app.

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

