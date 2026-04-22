# Agents

Code Agents ships with **18 pre-configured agents** in the `agents/` directory. Each is defined as a YAML file, exposed as an OpenAI-compatible endpoint, and available in the interactive chat.

```bash
code-agents chat               # pick from numbered menu
code-agents chat code-writer   # go straight to a specific agent
```

The chat auto-detects your git repo from the current directory so the agent works on **your project's code**.

**All 18 agents default to:** Backend: Cursor | Model: Composer 2 Fast

### Inline Agent Delegation

From any active chat session, delegate a one-shot prompt to another agent:

```
you › /code-reviewer Review the auth module for security issues
you › /code-tester Write unit tests for PaymentService
```

- `/<agent> <prompt>` — one-shot, returns to your current agent
- `/<agent>` (no prompt) — switches permanently
- Press **Tab** after `/` to autocomplete agent names

---

## Code Reasoning
**Endpoint:** `/v1/agents/code-reasoning/chat/completions` | Permission: `default` (read-only)

Read-only code analysis and codebase exploration. Use it to explain architecture, trace data flows, compare approaches, plan testing strategies, and answer "how does this work?" questions. Includes codebase exploration capabilities (formerly the explore agent). Cannot modify files.

---

## Code Writer
**Endpoint:** `/v1/agents/code-writer/chat/completions` | Permission: `default`

Generates and modifies code. Writes new files/modules/tests, refactors existing code, implements features, applies fixes. File edits are auto-approved — no user confirmation required.

---

## Code Reviewer
**Endpoint:** `/v1/agents/code-reviewer/chat/completions` | Permission: `default`

Critical code review without rewriting. Identifies bugs and security issues, suggests performance improvements, flags style violations, reviews test quality, and prioritizes issues by severity.

---

## Code Tester
**Endpoint:** `/v1/agents/code-tester/chat/completions` | Permission: `default`

Testing, debugging, and code quality. Writes and refactors tests, debugs issues, optimizes performance, improves readability and maintainability.

---

## Redash Query
**Endpoint:** `/v1/agents/redash-query/chat/completions` | Permission: `default`

Database query agent powered by Redash. Lists data sources, explores table schemas, writes SQL from natural language, executes queries, and iterates on results or errors.

Requires: `REDASH_BASE_URL` and `REDASH_API_KEY` (or `REDASH_USERNAME` + `REDASH_PASSWORD`).

---

## Git Operations
**Endpoint:** `/v1/agents/git-ops/chat/completions` | Permission: `default`

Git operations on a target repository. Lists branches, shows diffs, views commit history, pushes branches, checks working tree status.

Requires: `TARGET_REPO_PATH`.

---

## Test Coverage
**Endpoint:** `/v1/agents/test-coverage/chat/completions` | Permission: `default`

Test execution and coverage analysis with **autonomous mode**. Runs test suites (auto-detects pytest/jest/maven/gradle/go), generates and parses coverage reports, identifies uncovered code, blocks pipeline if below threshold.

**Autonomous mode:** Say "boost coverage" or "increase coverage for X to Y%" and the agent enters a self-driving loop — baseline → gap analysis → prioritize by risk → write tests in batches → verify → iterate until threshold met → branch & commit. Uses session scratchpad (`[REMEMBER:]`) to track progress across turns. No user intervention needed between phases.

**Skills:** `auto-coverage` (entry point), `autonomous-boost` (self-driving loop), `write-python-tests` (pytest), `write-unit-tests` (JUnit), `write-integration-tests` (Spring), `write-e2e-tests` (full flow), `coverage-plan`, `coverage-gate`, `coverage-diff`, `find-gaps`, `run-coverage`, `jacoco-report`.

Requires: `TARGET_REPO_PATH`. Optional: `TARGET_TEST_COMMAND`, `TARGET_COVERAGE_THRESHOLD`.

---

## Jenkins CI/CD
**Endpoint:** `/v1/agents/jenkins-cicd/chat/completions` | Permission: `default`

Unified Jenkins CI/CD agent (build + deploy + ArgoCD verification). Runs git pre-checks, triggers build/deploy jobs, monitors progress, fetches logs, verifies ArgoCD deployment. Full workflow: git pre-check → build → deploy → verify.

**Upfront questionnaire:** For ambiguous requests (e.g. "push my changes", "help with CI/CD"), the agent asks all relevant questions at once via a tabbed wizard (`[QUESTION:cicd_action]`, `[QUESTION:deploy_environment_class]`, `[QUESTION:cicd_branch]`, `[QUESTION:cicd_java_version]`). For explicit commands ("build", "deploy to qa4"), it skips intake and acts directly.

**Session scratchpad:** Discovered facts (branch, repo, build job, parameters, image tag) are persisted to `/tmp` via `[REMEMBER:key=value]` tags and injected as `[Session Memory]` on every turn. Reusable facts (branch, job path) are cached; build results (image tag, build number) are stored for deploy reference but never prevent a re-build.

Requires: `JENKINS_URL`, `JENKINS_USERNAME`, `JENKINS_API_TOKEN`.

---

## ArgoCD Verify
**Endpoint:** `/v1/agents/argocd-verify/chat/completions` | Permission: `default`

ArgoCD deployment verification and rollback. Checks sync/health status, lists pods, verifies image tags, fetches logs, scans for errors (ERROR/FATAL/Exception/panic), triggers rollback.

Requires: `ARGOCD_URL`, `ARGOCD_AUTH_TOKEN`.

---

## QA Regression
**Endpoint:** `/v1/agents/qa-regression/chat/completions` | Permission: `default`

Principal QA engineer that eliminates manual testing. Runs full regression suites, writes missing tests (reads CLAUDE.md/README.md for context), mocks external dependencies, identifies coverage gaps, creates test plans. Uses the project's existing test framework (pytest/jest/JUnit/Go test).

---

## Auto-Pilot
**Endpoint:** `/v1/agents/auto-pilot/chat/completions` | Permission: `default`

Autonomous orchestrator that delegates to sub-agents and runs full workflows. Includes pipeline orchestration (6-step CI/CD state machine) and agent routing (recommends specialists). Executes complete SDLC pipelines (13 steps: Jira → Analysis → Design → Code → Test → Review → Build → Deploy → Verify → Rollback), chains multi-agent workflows end-to-end.

Also available as REST API: `POST /pipeline/start`, `GET /pipeline/{id}/status`, `POST /pipeline/{id}/advance`, `POST /pipeline/{id}/rollback`.

---

## Jira Ops
**Endpoint:** `/v1/agents/jira-ops/chat/completions` | Permission: `default`

Principal Project Engineer owning the full ticket lifecycle, sprint planning, release tracking, and Confluence docs. Creates/updates/transitions issues, searches with JQL, manages Confluence pages, tracks sprint progress, generates standups, produces release notes, and posts post-deployment updates.

**Skills:** read-ticket, create-ticket, update-status, read-wiki, sprint-manager, release-tracker, standup-report, dependency-map, ticket-validate, progress-updater, release-notes, post-deploy-update

Requires: `JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`.

---

## Security
**Endpoint:** `/v1/agents/security/chat/completions` | Permission: `default`

Head of Cybersecurity Engineer — finds vulnerabilities, misconfigurations, and supply-chain risks. Performs OWASP Top 10 static analysis, dependency CVE auditing, secrets detection, attack surface mapping, and compliance review. Read-only: never modifies files, delegates to code-writer for fixes.

**Skills:** vulnerability-scan, dependency-audit, secrets-detection, attack-surface, compliance-review, security-report

Uses: `code_agents/analysis/security_scanner.py`, `code_agents/dependency_audit.py`.

---

## GitHub Actions
**Endpoint:** `/v1/agents/github-actions/chat/completions` | Permission: `default`

GitHub Actions agent — trigger, monitor, retry, and debug GitHub Actions workflows. Lists workflows, dispatches runs, polls for completion, fetches logs, identifies failures, and retries transient errors.

**Skills:** trigger-workflow, debug-failure, list-workflows, monitor-run, retry-failed

Requires: `GITHUB_TOKEN`, `GITHUB_REPO` (owner/repo format).

---

## Grafana Ops
**Endpoint:** `/v1/agents/grafana-ops/chat/completions` | Permission: `default`

Grafana metrics and alerting agent — search dashboards, query panel data, investigate firing alerts, correlate deployments with metric changes, and create annotations. Uses the existing Grafana router and client.

**Skills:** query-metrics, investigate-alert, correlate-deploy, dashboard-search

Requires: `GRAFANA_URL`, `GRAFANA_USERNAME`, `GRAFANA_PASSWORD`.

---

## Terraform/IaC
**Endpoint:** `/v1/agents/terraform-ops/chat/completions` | Permission: `default`

Terraform infrastructure-as-code agent — init, validate, plan, apply, and destroy with safety gates. Inspects state, detects drift, reviews plans for security and blast radius. NEVER applies without showing plan first and getting user approval.

**Skills:** plan, apply, drift-detect, state-inspect, review-plan

Requires: `terraform` binary in PATH. Optional: `TERRAFORM_WORKING_DIR`, `TERRAFORM_BINARY`.

---

## Postgres/DB
**Endpoint:** `/v1/agents/db-ops/chat/completions` | Permission: `default`

PostgreSQL database agent — safe query execution with EXPLAIN analysis, schema inspection, migration generation, and schema diffing. Enforces read-only by default, requires explicit approval for write operations, auto-adds LIMIT to queries.

**Skills:** safe-query, table-info, generate-migration, schema-diff, explain-plan

Requires: `DATABASE_URL` or `DB_HOST`/`DB_PORT`/`DB_USER`/`DB_PASSWORD`/`DB_NAME`.

---

## PR Review Bot
**Endpoint:** `/v1/agents/pr-review/chat/completions` | Permission: `default`

Automated PR review agent — fetches PRs, diffs, and files from GitHub, analyzes changes against security/correctness/performance standards, posts inline review comments and summary reviews. Categorizes findings as Critical/Warning/Suggestion.

**Skills:** auto-review, post-comments, review-checklist, webhook-handler

Requires: `GITHUB_TOKEN`, `GITHUB_REPO` (owner/repo format).

---

## Debug Agent
**Endpoint:** `/v1/agents/debug-agent/chat/completions` | Permission: `default`

Autonomous debugging specialist — reproduces bugs, traces root causes through call chains, applies minimal targeted fixes, and verifies them. Follows a strict methodology: Reproduce → Trace → Root Cause → Fix → Verify → Blast Radius. Delegates to code-tester, code-writer, and code-reviewer as needed.

**Skills:** reproduce, trace-error, root-cause, bisect, fix-verify

---

## Creating a Custom Agent

Add a YAML file to `agents/` and restart the server:

```yaml
name: my-agent                          # Required: URL-safe identifier
display_name: "My Custom Agent"         # Optional: UI name (defaults to name)
backend: cursor                         # Optional: "cursor" or "claude" (default: cursor)
model: "Composer 2 Fast"                # Optional: LLM model ID
system_prompt: |                        # Optional: supports ${ENV_VAR} expansion
  You are a helpful assistant.
permission_mode: default                # Optional: "default" | "acceptEdits" | "bypassPermissions"
cwd: "."                                # Optional: working directory
api_key: ${CURSOR_API_KEY}              # Optional: API key (env var expansion)
stream_tool_activity: true              # Optional: show tool calls in reasoning_content
include_session: true                   # Optional: return session_id for multi-turn
extra_args:
  mode: ask
```

**Permission modes:** `default` (agent asks before changes) | `acceptEdits` (auto-approve edits) | `bypassPermissions` (read-only)

**Claude backend — Option A: Claude CLI** (uses your subscription, no API key)
```bash
code-agents init --backend   # choose: Claude CLI
# or set in ~/.code-agents/config.env:
CODE_AGENTS_BACKEND=claude-cli
CODE_AGENTS_CLAUDE_CLI_MODEL=claude-sonnet-4-6
```

**Claude backend — Option B: Claude API** (pay-as-you-go)
Set `ANTHROPIC_API_KEY`, rename `agents/claude_example.yaml.disabled` → `.yaml`, restart.

---

## Agent Resolution

Request fallback chain: exact `name` match → `display_name` match → `model` ID match → first loaded agent. Clients can reference agents by name, display name, or model ID interchangeably.

---

## Multi-Turn Sessions

Chat manages sessions automatically — auto-saved to `~/.code-agents/chat_history/`. Use `/session`, `/history`, `/resume <id>`, or `code-agents chat --resume <id>`.

Via API, pass `session_id` in subsequent requests:
```bash
RESPONSE=$(curl -s -X POST http://localhost:8000/v1/agents/code-reasoning/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Explain the auth module"}]}')
SESSION_ID=$(echo $RESPONSE | jq -r '.session_id')
# Follow-up: add "session_id": "$SESSION_ID" to request body
```

---

## Typical Workflow

Chat commands (~60): `/help /agents /agent <name> /run /exec /rules /skills /tokens /session /clear /history /resume /setup /memory /plan /superpower /export /mcp /btw /bash /stats /layout /confirm /mindmap /review /dep-impact /corrections /bg /tasks /replay /traces /tail /pair /api-docs /translate /profile /schema /changelog /dashboard /txn-flow /recon /pci-scan /idempotency /validate-states /acquirer-health /retry-audit /load-test /postmortem-gen /settlement /migrate-tracing /<agent> <prompt> /<agent>:<skill>`

Agent routing diagram:
```
Auto-Pilot → Code Reasoning | Code Writer | Code Reviewer | Code Tester
           → Redash Query | Git Ops | Test Coverage | Jenkins CI/CD
           → ArgoCD Verify | QA Regression | Jira Ops | Security
           → GitHub Actions | Grafana Ops | Terraform/IaC
           → Postgres/DB | PR Review Bot
```

**Platform Tools** (28 features — all CLI + slash commands):
| Tool | CLI | Slash | Purpose |
|------|-----|-------|---------|
| Repo Mindmap | `mindmap` | `/mindmap` | Visual repo structure (ASCII/Mermaid/HTML) |
| Code Review | `review` | `/review` | Inline annotated diff with findings |
| Dep Impact | `impact` | `/dep-impact` | Dependency upgrade impact scanner |
| Agent Corrections | — | `/corrections` | Learn from user corrections |
| Multi-Repo | `workspace` | `/workspace-cross-deps` | Cross-repo deps, coordinated PRs |
| Git Hooks | `install-hooks` | — | AI pre-commit/pre-push analysis |
| Agent Replay | `replay` | `/replay` | Time travel debugging |
| RAG Context | `index` | — | Vector store for smart context |
| Live Tail | `tail` | `/tail` | Real-time log streaming + anomaly detection |
| Pair Mode | `pair` | `/pair` | Real-time file watcher + suggestions |
| API Docs | `api-docs` | `/api-docs` | Generate OpenAPI/Markdown/HTML |
| Code Translator | `translate` | `/translate` | Cross-language translation |
| Profiler | `profiler` | `/profile` | cProfile + optimization suggestions |
| Schema Viz | `schema` | `/schema` | ER diagrams from DB/SQL |
| Changelog | `changelog-gen` | `/changelog` | Auto changelog from git/PRs |
| Dashboard | `dashboard` | `/dashboard` | Tests + coverage + complexity + PRs |
| Background Tasks | `bg` | `/bg` | Manage background agents |
| **Payment Gateway** | | | |
| Txn Flow | `txn-flow` | `/txn-flow` | Transaction journey visualizer |
| Recon Debugger | `recon` | `/recon` | Order vs settlement reconciliation |
| PCI Scanner | `pci-scan` | `/pci-scan` | PCI-DSS compliance checks |
| Idempotency Audit | `audit-idempotency` | `/idempotency` | Payment endpoint safety |
| State Machine | `validate-states` | `/validate-states` | State transition validator |
| Acquirer Health | `acquirer-health` | `/acquirer-health` | Acquirer success rates + alerts |
| Retry Analyzer | `retry-audit` | `/retry-audit` | Payment retry strategy audit |
| Load Test Gen | `load-test` | `/load-test` | k6/Locust/JMeter generation |
| Postmortem Gen | `postmortem-gen` | `/postmortem-gen` | Incident postmortem builder |
| Settlement Parser | `settlement` | `/settlement` | Visa/MC/UPI file parsing |
| OTel Migration | `migrate-tracing` | `/migrate-tracing` | Jaeger/DD/Zipkin → OpenTelemetry |
| **Code Intelligence** | | | |
| Code Explainer | `explain-code` | `/explain-code` | Call chains, side effects, complexity |
| Code Smell | `smell` | `/smell` | God class, long method, deep nesting |
| Tech Debt | `tech-debt` | `/tech-debt` | Debt score 0-100 with trend tracking |
| Import Optimizer | `imports` | `/imports` | Unused, circular, wildcard imports |
| Dead Code | `dead-code-eliminate` | `/dead-code-eliminate` | Find + remove unused code |
| Clone Detector | `clones` | `/clones` | Token-based duplicate detection |
| Naming Audit | `naming-audit` | `/naming-audit` | Convention consistency checker |
| ADR Generator | `adr` | `/adr` | Architecture Decision Records |
| Comment Audit | `comment-audit` | `/comment-audit` | Outdated, obvious, TODO comments |
| Type Adder | `add-types` | `/add-types` | Infer + add Python type annotations |
| **Testing** | | | |
| Mutation Testing | `mutate-test` | `/mutate-test` | Inject mutations, find weak tests |
| Property Tests | `prop-test` | `/prop-test` | Hypothesis test generation |
| Test Style | `test-style` | `/test-style` | Detect AAA/BDD patterns, generate matching |
| Visual Regression | `visual-test` | `/visual-test` | HTML snapshot capture + diff |
| **Security & Compliance** | | | |
| OWASP Scanner | `owasp-scan` | `/owasp-scan` | All 10 OWASP categories |
| Encryption Audit | `encryption-audit` | `/encryption-audit` | Weak crypto, ECB, hardcoded keys |
| Vuln Chain | `vuln-chain` | `/vuln-chain` | Transitive vulnerability tracing |
| Input Audit | `input-audit` | `/input-audit` | Endpoint validation coverage |
| Rate Limit Audit | `rate-limit-audit` | `/rate-limit-audit` | Missing rate limits on auth/payment |
| Privacy Scanner | `privacy-scan` | `/privacy-scan` | PII detection, GDPR/DPDP compliance |
| Session Audit | `session-audit` | `/session-audit` | JWT expiry, cookie flags, logout |
| ACL Matrix | `acl-matrix` | `/acl-matrix` | Role→endpoint matrix, escalation paths |
| Secret Rotation | `secret-rotation` | `/secret-rotation` | Stale secret detection + runbooks |
| Compliance Report | `compliance-report` | `/compliance-report` | PCI/SOC2/GDPR compliance mapping |
| **DevOps & CI** | | | |
| CI Self-Healing | `ci-heal` | `/ci-heal` | Autonomous red-to-green loop |
| Headless/CI Mode | `ci-run` | — | Non-interactive pipeline tasks |
| Batch Operations | `batch` | `/batch` | Apply instruction across files |
| **Developer Productivity** | | | |
| Snippet Library | `snippet` | `/snippet` | Save/search reusable code snippets |
| Env Diff | `env-diff` | `/env-diff` | Compare environments |
| Code Ownership | `ownership` | `/ownership` | Git blame analysis + CODEOWNERS |
| Velocity Predict | `velocity-predict` | `/velocity-predict` | Sprint capacity prediction |
| PR Split | `pr-split` | `/pr-split` | Split large PRs by risk/independence |
| License Audit | `license-audit` | `/license-audit` | Dependency license compliance + SBOM |
| Config Validator | `validate-config` | `/validate-config` | YAML/JSON/TOML/.env validation |
| Release Notes | `release-notes` | `/release-notes` | Humanized changelog for PMs |
| **Frontier** | | | |
| Spec Validator | `spec-validate` | `/spec-validate` | PRD/Jira vs code gap analysis |
| Screenshot-to-Code | `screenshot` | `/screenshot` | UI code from descriptions/templates |
| Code Archaeology | `archaeology` | `/archaeology` | Git blame → PR → issue → intent |
| Perf Proof | `perf-proof` | `/perf-proof` | Before/after benchmarks with stats |
| Contract Testing | `contract-test` | `/contract-test` | Pact/Schema tests from API routes |
| Self-Benchmark | `self-bench` | `/self-bench` | Agent quality self-evaluation |
| Lang Migration | `lang-migrate` | `/lang-migrate` | Migrate modules between languages |
| **Enterprise** | | | |
| PR Thread Agent | `pr-respond` | `/pr-respond` | Respond to PR review comments |
| Team KB | `team-kb` | `/team-kb` | Git-tracked team knowledge base |
| Onboarding | `onboard-tour` | `/onboard` | Guided codebase tour for new devs |
| Browser Agent | `browse` | `/browse` | Fetch pages, extract API docs |
| Live Preview | `preview` | `/preview` | Serve frontend on localhost |
| **Global** | | | |
| Full Audit | `full-audit` | `/full-audit` | All scanners + 15 quality gates |
| Smart Commands | — | `/commands <query>` | Intent → agent + command routing |

Use `code-agents curls <agent-name>` for copy-pasteable curl commands.

**Agent Rules** — persistent rules injected into system prompts:
```bash
code-agents rules create                      # project rule, all agents
code-agents rules create --agent code-writer  # project rule, specific agent
code-agents rules create --global             # global rule, all agents
```
Rules live in `~/.code-agents/rules/` (global) and `myrepo/.code-agents/rules/` (project). Auto-refresh on every message — edit mid-chat and the next message picks it up. Use `/rules` in chat to see active rules.

---

## Maintenance

When adding a new agent:

1. Add agent YAML to `agents/`
2. Document in this file following the format above
3. Add role to `AGENT_ROLES` in `code_agents/chat.py`
4. Add examples to `_AGENT_EXAMPLES` in `code_agents/cli.py`
5. Update `agents/auto-pilot/auto-pilot.yaml` — add to specialists list
6. Update `README.md`, `CLAUDE.md`, `cursor.md` — agents table and architecture sections
7. Add tests in `tests/`

Run `poetry run python initiater/run_audit.py --rules workflow` to verify sync.
Run `poetry run pytest` to verify all tests pass.

**Key files referencing agent lists:** `agents/auto-pilot/auto-pilot.yaml`, `code_agents/chat.py` (`AGENT_ROLES`), `code_agents/cli.py` (`_AGENT_EXAMPLES`), `README.md`, `AGENTS.md`, `CLAUDE.md`/`cursor.md`

---

Copyright (c) 2026 Code Agents Contributors (Regulated by RBI)
