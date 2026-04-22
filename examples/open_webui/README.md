# Open WebUI Plugins for Code Agents

## Redash Query Tool + Run Action

Two plugins that give Open WebUI the ability to query databases via Redash:

### 1. Redash Tool (`redash_tool.py`)

An **Open WebUI Tool** that gives the LLM four functions:
- `list_data_sources()` — list all Redash databases
- `get_schema(data_source_id)` — get tables + columns
- `run_query(data_source_id, query)` — execute SQL and return results
- `run_saved_query(query_id)` — run a saved Redash query

The LLM calls these autonomously during conversation to explore schemas and execute queries.

### 2. Run SQL Action (`redash_run_action.py`)

An **Open WebUI Action** that adds a **"Run"** button to assistant messages containing SQL. When clicked:
1. Extracts SQL from the message (```sql blocks or inline SELECT)
2. Safety-checks the query (SELECT only, no mutations)
3. Adds LIMIT if missing
4. Executes via Redash API
5. Sends formatted results back to the conversation
6. Agent summarizes the results

## Installation

**Minimum:** Install the Redash Tool (Step 1). The Run Action (Step 2) is optional — the agent executes queries via the tool even without it.

### Step 1: Install the Tool

1. Open WebUI → **Workspace** → **Tools** → **+** (Add Tool)
2. Paste the contents of `redash_tool.py`
3. Save
4. Click the gear icon on the tool → **Valves** → set:
   - `CODE_AGENTS_URL`: `http://localhost:8000` (or wherever Code Agents runs)
   - Or set `REDASH_BASE_URL` + credentials for direct access
   - `DEFAULT_DATA_SOURCE_ID`: your most-used data source (e.g., `70`)

### Step 2: Install the Action (optional)

The Run Action adds a **"Run"** button to assistant messages with SQL. If you don't see **Functions** under Workspace:

- Try **Admin** → **Functions** or **Admin** → **Actions**
- Or **Settings** → **Functions** (depending on your Open WebUI version)
- Some deployments hide Functions; the **Redash Tool alone** is sufficient — the agent can execute queries via the tool without the Run button

If you can add it:

1. Open WebUI → **Workspace** (or **Admin**) → **Functions** → **+** (Add Function)
2. Paste the contents of `redash_run_action.py`
3. Save
4. Click the gear icon → **Valves** → set same connection details as the Tool
5. The action is **global** — the Run button appears on any assistant message with SQL

### Step 3: Enable on your model

1. In a chat, pick the **redash-query** model (or any model)
2. Click the **+** next to the model name → enable **Redash Query Tool**
3. The LLM can now call Redash functions directly

## Usage Flow

```
You: "Show me the top 10 merchants by order count in acqcore0"

Agent: "Let me check the schema first..."
       [calls get_schema(70)]
       "Here's the query:
       ```sql
       SELECT merchant_id, COUNT(*) as order_count
       FROM acq_order_0
       GROUP BY merchant_id
       ORDER BY order_count DESC
       LIMIT 10
       ```"

       [Run ▶] button appears

You: Click [Run ▶]

Agent: "Results:
       | merchant_id | order_count |
       |-------------|-------------|
       | M001        | 45230       |
       | M002        | 38102       |
       ...
       The top merchant M001 has 45K orders, nearly 20% more than #2..."
```

## Configuration

Both plugins try **Code Agents server first** (`http://localhost:8000/redash/*`), then fall back to **direct Redash API** if the server is unreachable.

| Valve | Required | Description |
|-------|----------|-------------|
| `CODE_AGENTS_URL` | recommended | Code Agents server URL |
| `REDASH_BASE_URL` | fallback | Direct Redash URL (e.g., `http://10.215.50.126`) |
| `REDASH_API_KEY` | either | Redash API key |
| `REDASH_USERNAME` | or | Redash login email |
| `REDASH_PASSWORD` | both | Redash login password |
| `DEFAULT_DATA_SOURCE_ID` | optional | Default DB when not specified (default: 70) |
| `QUERY_ROW_LIMIT` | optional | Max rows returned (default: 100, tool only) |

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

