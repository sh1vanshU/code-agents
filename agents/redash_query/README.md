# Redash Query Agent

> Principal Data Engineer — database operations, query optimization, and data investigation via Redash

## Identity

| Field | Value |
|-------|-------|
| **Name** | `redash-query` |
| **YAML** | `redash_query.yaml` |
| **Backend** | `${CODE_AGENTS_BACKEND:cursor}` |
| **Model** | `${CODE_AGENTS_MODEL:Composer 2 Fast}` |
| **Permission** | `default` — ask before each action |

## Capabilities

- List available data sources (databases/shards)
- Fetch table schemas (tables + columns) for any data source
- Write SQL queries from natural language and execute them
- Run saved Redash queries by ID
- Explain query results clearly with formatted output
- Scan repo JPA entities and map to DB schema with ER diagrams
- Run EXPLAIN on queries and suggest index/query optimizations
- Post-deploy data validation (row counts, FK integrity, business rules)
- Verify Flyway/Liquibase migrations with before/after comparison
- Investigate data incidents by tracing records across tables

## Important Rules

- ALWAYS uses SELECT queries only — never modifies data
- ALWAYS adds LIMIT (default 100) to prevent huge result sets
- When tables are sharded, queries a single shard — no UNION across shards
- Shows the SQL before executing
- Database context: acquiring/payments system (MySQL), horizontally sharded tables

## Tools & Endpoints

- `GET /redash/data-sources` — list all data sources (id, name, type)
- `GET /redash/data-sources/{id}/schema` — get tables + columns for a data source
- `POST /redash/run-query` — execute a query: `{"data_source_id": <id>, "query": "<SQL>", "max_age": 0}`
- `POST /redash/run-saved-query` — run a saved query by ID: `{"query_id": <id>, "max_age": 0}`

## Skills

### Own Skills

| Skill | Description |
|-------|-------------|
| `explore-schema` | List data sources, explore table schemas and relationships |
| `write-query` | Write SQL from natural language, explain the query, execute it |
| `saved-queries` | List and run saved Redash queries |
| `query-builder` | Write SQL from natural language, analyze repo schema (JPA entities), execute on Redash, format results |
| `schema-analysis` | Scan repo for @Entity/@Table/@Column, map to DB via Redash, build ER map, identify mismatches |
| `query-optimizer` | Run EXPLAIN on queries, identify full scans and missing indexes, suggest optimizations |
| `data-validation` | Post-deploy data checks: row counts, FK integrity, business rules, enum validity |
| `migration-verify` | Verify Flyway/Liquibase migrations: snapshot before/after, verify schema changes, rollback plan |
| `incident-investigate` | Data investigation: query DB for affected records, trace data flow, identify root cause |

### Shared Engineering Skills

Shared skills from `agents/_shared/skills/` are also available to this agent: architecture, code-review, debug, deploy-checklist, documentation, incident-response, standup, system-design, tech-debt, testing-strategy.

## Usage

### Chat REPL
```bash
code-agents chat redash-query
```

### Inline Delegation (from another agent)
```
/redash-query <your prompt>
```

### Skill Invocation
```
/redash-query:explore-schema
/redash-query:write-query <your prompt>
/redash-query:saved-queries
/redash-query:query-builder <your prompt>
/redash-query:schema-analysis
/redash-query:query-optimizer
/redash-query:data-validation
/redash-query:migration-verify
/redash-query:incident-investigate
```

### API
```bash
curl -X POST http://localhost:8000/v1/agents/redash-query/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "your prompt"}], "stream": true}'
```

## Example Prompts

1. "Show me all data sources available"
2. "Write a query for the top 10 users by order count"
3. "What tables are in the acqcore0 database?"
4. "Scan the repo and map JPA entities to the DB schema"
5. "Run EXPLAIN on this query and suggest optimizations"
6. "Validate data integrity after the v2.3.1 deployment"
7. "Verify the latest Flyway migration ran correctly"
8. "Investigate why transaction TXN-12345 is stuck in PROCESSING"

## Autorun Config

This agent has an `autorun.yaml` that defines allowed and blocked commands for auto-execution.

## Rules

Custom rules to guide this agent's behavior:

| Scope | Path |
|-------|------|
| Global | `~/.code-agents/rules/redash-query.md` |
| Project | `.code-agents/rules/redash-query.md` |

See `code-agents rules create --agent redash-query` to create rules.

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

