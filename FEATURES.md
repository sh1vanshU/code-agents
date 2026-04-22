# Code Agents — Feature History

A chronological record of every feature built, from the first line of code to where we are today.

---

## Phase 1: Interactive Chat Foundation

1. **Inline Agent Delegation** — Type `/<agent> <prompt>` to send a one-shot prompt to another agent without leaving your session. No more switching agents just to ask a quick question.
2. **Tab-Completion in Chat REPL** — Press Tab after `/` to autocomplete slash commands and agent names. Discover commands without /help.
3. **Readline ANSI Fix** — Fixed tab-completion on macOS by wrapping ANSI escape codes in readline invisible markers. Colors in the prompt were breaking cursor position tracking.

---

## Phase 2: Workspace & Configuration

4. **Centralized .env Configuration** — Two-tier config: global `~/.code-agents/config.env` for API keys/integrations, per-repo `.env.code-agents` for Jenkins/ArgoCD/testing. No more per-repo `.env` conflicts with virtualenv directories.
5. **Migration Command** — `code-agents migrate` splits a legacy `.env` into global + per-repo files automatically. Smooth upgrade path for existing users.
6. **Init Section Flags** — `code-agents init --jenkins` (and `--argocd`, `--jira`, etc.) updates just that section. Don't re-run the full wizard to change one setting.
7. **Cursor Workspace Trust Detection** — Detect "Workspace Trust Required" errors at boot and auto-trust via `cursor-agent --trust`. Handles cryptic errors before chat starts.

---

## Phase 3: Command Execution Engine

8. **Command Detection from Agent Responses** — Agent outputs ` ```bash ` blocks → detected, shown in a box, user prompted to run. Execute without copy-pasting.
9. **Backslash Line Continuation** — Multi-line curl commands with `\` treated as one command, not separate lines.
10. **Placeholder Resolution** — `{job_name}` and `<DATA_SOURCE_ID>` in commands prompt the user to fill in values interactively.
11. **Red Bordered Output Box** — Command output in a bordered box with JSON pretty-printing. Clean visual separation between agent text and command output.
12. **Clipboard Copy** — Command output auto-copied to clipboard (macOS pbcopy).

---

## Phase 4: Agent Rules System

13. **Two-Tier Rules** — Markdown files injected into agent system prompts: global (`~/.code-agents/rules/_global.md`), per-agent, and project-level. Persistent instructions that survive sessions.
14. **Auto-Refresh Rules** — Rules read from disk on every message. Edit a rules file mid-chat — next message picks it up without restart.
15. **Rules CLI** — `code-agents rules list/create/edit/delete`. Easy CRUD without manually creating files.
16. **Auto-Save Approved Commands** — When you approve a command, it's saved to the agent's rules. Next time it auto-approves. Approve once, run forever.

---

## Phase 5: Agentic Loop

17. **Command Output → Agent Feedback** — After running a command, output is automatically sent back to the agent. Agent continues reasoning from the result.
18. **/exec Command** — `/exec <cmd>` runs a command AND feeds output to the agent (unlike `/run` which is silent).
19. **One Command at a Time** — System prompt instructs agents to output exactly one ` ```bash ` block per response then stop — matches Claude Code's propose/approve/execute workflow.

---

## Phase 6: Claude Code-Style UX

20. **Spinner with Live Timer** — Animated spinner while waiting: `⠹ Thinking... 12s`. Elapsed time shown after response.
21. **Command Approval Selector** — Numbered `1. Yes / 2. No` prompt with default-yes. Three-option variant: `1. Yes / 2. Yes & Save to rules / 3. No`.
22. **Full Command Display** — Long commands wrap across multiple lines in the approval box — no truncation. See exactly what you're about to run.
23. **Auto-Collapse Long Responses** — Responses >25 lines collapse to first 8 + last 8. Press Ctrl+O to expand in pager.
24. **Markdown Rendering** — `**bold**`, `` `code` ``, `## Header` rendered in terminal. Agent responses look better without raw markdown syntax.

---

## Phase 7: Agent Welcome Messages & Quality

25. **Welcome Boxes** — Selecting or switching agents shows a bordered box with what the agent can do and example prompts. New users know each agent's purpose without reading docs.
26. **Rewritten System Prompts** — All core agents rewritten with role definition, step-by-step methodology, quality standards, and explicit boundaries. Generic 3-line prompts → detailed 30-line prompts.
27. **QA Regression Agent** — 13th agent: principal QA engineer that runs regression suites, writes missing tests, mocks dependencies.

---

## Phase 8: Jenkins Integration

28. **Job Discovery** — `GET /jenkins/jobs?folder=<path>` lists all jobs in a folder. Browse what's available instead of guessing names.
29. **Parameter Introspection** — `GET /jenkins/jobs/{path}/parameters` fetches parameter definitions (name, type, default, choices) before triggering.
30. **Build-and-Wait** — `POST /jenkins/build-and-wait` triggers build, polls until complete, extracts build version from logs. One call does everything.
31. **Build Version Extraction** — Regex patterns scan console output for Docker tags, Maven versions, `BUILD_VERSION=`. Deploy job gets the version automatically.
32. **Folder Job Path Handling** — `_job_path()` converts Jenkins URL paths to correct API paths and strips accidental `job/` prefixes.

---

## Phase 9: Backend & Infrastructure

33. **Claude CLI Backend** — `CODE_AGENTS_BACKEND=claude-cli` uses your Claude Pro/Max subscription instead of an API key.
34. **Shell Tab-Completion** — `code-agents ru<Tab>` → `rules`. `code-agents rules create --agent <Tab>` → agent names. Install with `code-agents completions --install`.
35. **code-agents update** — `git pull` + `poetry install` in one command with SSH→HTTPS fallback.
36. **code-agents restart** — `shutdown` + `start` in one command. Also available as `/restart` in chat.
37. **10-Bug Code Review Hunt** — Found and fixed 10 real bugs: placeholder commands saved unresolved to rules, Jenkins path stripping legitimate "job" folders, shallow copy mutations leaking across requests, race conditions in rules file read/write (fixed with fcntl locking).

---

## Phase 10: Chat Session Persistence

38. **Chat History** — Sessions auto-save to `~/.code-agents/chat_history/`. Resume with `--resume <id>` or `/resume`. Manage with `code-agents sessions`. Don't lose conversations.
39. **Live Command Timer with Jenkins Polling** — Commands show live elapsed timer. After 120s, polls Jenkins API every 15s and shows build status inline.
40. **Ctrl+O Toggle** — Long responses auto-collapse. Press Ctrl+O to expand inline; press again to collapse.

---

## Phase 11: Intelligence & UX (v0.3)

41. **Plan Mode** — `/plan` full lifecycle: create → propose → approve/reject/edit → execute → complete. Questionnaire: "1. Auto-accept / 2. Manual approve / 3. Give feedback". Like Claude Code's plan mode.
42. **Shift+Tab Mode Cycling** — Cycles Chat → Plan mode → Accept edits on. Only active mode shown in toolbar.
43. **Message Queue** — Type messages while agent is processing — queued FIFO, auto-processed when agent finishes. Shows "⟫ Message queued (position N)".
44. **prompt_toolkit Input** — Replaces readline `input()` with `PromptSession`. Fixed input bar at bottom, output scrolls above, dropdown autocomplete. Graceful fallback if unavailable.
45. **Endpoint DTO Extraction + OpenAPI** — Generated curl payloads use actual Java DTO field names/types or OpenAPI/Swagger schemas. Priority: OpenAPI → DTO → heuristic. Meaningful payloads instead of `{"TODO": "fill fields"}`.
46. **Pipeline Rollback** — `rollback_to_revision()` accepts git SHA or deployment ID. `run_smoke_test()` HTTP health check. Auto-rollback on verify failure.
47. **AI-Powered Incident RCA** — `--analyze` flag delegates investigation findings to agent for root cause, fix, and prevention recommendations.
48. **AI-Powered Test Completion** — `build_test_completion_prompt()` feeds TODO skeletons to code-tester agent to fill in actual test logic.
49. **Sprint Velocity Predictions** — `predict_velocity()` linear regression, `estimate_completion()` with confidence scoring. Forecasting, not just historical reporting.
50. **Startup Backend Validation** — Actually calls `validate_backend()` to test if the AI backend responds. Shows "(verified)" or "⚠" with error — was only checking if config exists.
51. **Silent Error Handler Audit** — Replaced 30 silent `except: pass` blocks with proper logging across 11 files. Failures were invisible.
52. **MCP Plugin Hardening** — Tool schema validation before execution. SSE retry with exponential backoff. Stdio read timeout. Calls now validated, retried, and timed out properly.
53. **Gita Shlokas Bold Rainbow** — Sanskrit in bold rainbow; English meaning in matching rainbow colors.

54. **Session Scratchpad** — `/tmp`-based key-value store persists discovered facts (branch, job path, image tag) across agent turns. Agents write `[REMEMBER:key=value]`, Python code captures and injects as `[Session Memory]` block. Reusable facts cached, build results stored for reference but never prevent re-builds. 1-hour TTL, clears on agent switch.
55. **Upfront Questionnaire for Jenkins-CICD** — Ambiguous requests trigger multi-question tabbed wizard (`cicd_action`, `deploy_environment_class`, `cicd_branch`, `cicd_java_version`). Explicit commands skip intake. Multiple `[QUESTION:]` tags batched into single wizard with Enter-to-submit.
56. **Enter-to-Submit Questionnaire** — Replaced Y/n confirmation with "Press Enter to submit · Ctrl+C to cancel" for faster flow.

---

## Codebase Refactor (Phases 1–5) — Completed

Package reorganization into `analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` with backward-compat re-exports. CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`). Explore agent (15th) + `SubagentDispatcher`. `BashTool` for shell execution. Slimmer chat REPL split into `chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`. Full detail in `ROADMAP.md`.

---

## Phase 12: Platform Intelligence (v0.4)

57. **Repo Mindmap** — `code-agents mindmap` / `/mindmap` generates a visual repository structure in ASCII, Mermaid, or HTML format. Understand project layout at a glance.
58. **AI Code Review** — `code-agents review` / `/review` produces inline annotated terminal diffs with categorized findings (Critical/Warning/Suggestion). Review code without leaving the terminal.
59. **Dependency Impact Scanner** — `code-agents impact` / `/dep-impact` analyzes the blast radius of dependency upgrades across the codebase. Know what breaks before you upgrade.
60. **Agent Corrections** — `/corrections` lets agents learn from user corrections mid-session. Corrections persist and improve future responses.
61. **Multi-Repo Orchestration** — `code-agents workspace` / `/workspace-cross-deps` manages cross-repo dependencies, blast radius analysis, and coordinated PRs across multiple repositories.
62. **Git Hooks Agent** — `code-agents install-hooks` installs AI-powered pre-commit and pre-push hooks that analyze staged changes for issues before they reach the remote.
63. **Agent Replay** — `code-agents replay` / `/replay` enables time travel debugging by recording and replaying session traces. Reproduce exact agent behavior for debugging.
64. **RAG Context Injection** — `code-agents index` builds a vector store index of the codebase for smart context retrieval. Agents get relevant code snippets without manual file references.
65. **Live Tail Mode** — `code-agents tail` / `/tail` streams logs in real-time with AI-powered anomaly detection. Spot errors as they happen.
66. **Pair Programming Mode** — `code-agents pair` / `/pair` watches files in real-time and provides proactive AI suggestions as you code. Like having a senior engineer looking over your shoulder.
67. **Background Agents** — `code-agents bg` / `/bg` pushes running tasks to the background. Bottom toolbar shows status. Ctrl+F or `/fg` to bring back. Multiple agents run in parallel with macOS notifications on completion.

---

## Phase 13: Developer Productivity (v0.4)

68. **API Docs Generator** — `code-agents api-docs` / `/api-docs` auto-generates OpenAPI, Markdown, or HTML documentation from your API routes. Keep docs in sync with code.
69. **Code Translator** — `code-agents translate` / `/translate` translates code between languages using regex-based language pair transformation. Migrate Python to Go, Java to Kotlin, etc.
70. **Performance Profiler** — `code-agents profiler` / `/profile` runs cProfile analysis and provides optimization suggestions ranked by impact. Find bottlenecks fast.
71. **Database Schema Visualizer** — `code-agents schema` / `/schema` generates ER diagrams from live database connections or SQL files. Visualize your data model.
72. **Automated Changelog** — `code-agents changelog-gen` / `/changelog` generates changelogs from git history and PR metadata. Conventional commits mapped to categories automatically.
73. **Code Health Dashboard** — `code-agents dashboard` / `/dashboard` shows tests, coverage, complexity, and open PRs in a single unified view. One command for project health.

---

## Phase 14: Payment Gateway Tools (v0.4)

74. **Transaction Flow Visualizer** — `code-agents txn-flow` / `/txn-flow` traces a transaction's journey through microservices, showing each hop with status, latency, and payload.
75. **Reconciliation Debugger** — `code-agents recon` / `/recon` compares order records against settlement files to find mismatches, missing entries, and amount discrepancies.
76. **PCI-DSS Compliance Scanner** — `code-agents pci-scan` / `/pci-scan` scans payment gateway code for PCI-DSS violations: unencrypted PAN storage, insecure logging, missing tokenization.
77. **Idempotency Key Auditor** — `code-agents audit-idempotency` / `/idempotency` checks payment endpoints for proper idempotency key handling to prevent duplicate charges.
78. **Transaction State Machine Validator** — `code-agents validate-states` / `/validate-states` extracts, validates, and visualizes state transitions to catch impossible state changes.
79. **Acquirer Integration Health Monitor** — `code-agents acquirer-health` / `/acquirer-health` monitors acquirer success rates, latency percentiles, and triggers alerts on degradation.
80. **Payment Retry Strategy Analyzer** — `code-agents retry-audit` / `/retry-audit` audits retry logic for exponential backoff, max attempts, and idempotency safety.
81. **Load Test Scenario Generator** — `code-agents load-test` / `/load-test` generates k6, Locust, or JMeter scenarios from discovered API routes with realistic payment payloads.
82. **Incident Postmortem Generator** — `code-agents postmortem-gen` / `/postmortem-gen` builds structured postmortems with timeline, root cause, impact analysis, and action items.
83. **Settlement File Parser** — `code-agents settlement` / `/settlement` parses and validates Visa, Mastercard, and UPI settlement files, flagging format errors and amount mismatches.

---

## Phase 15: Migration & Observability (v0.4)

84. **OpenTelemetry Migration Tool** — `code-agents migrate-tracing` / `/migrate-tracing` migrates instrumentation from Jaeger, Datadog, or Zipkin to OpenTelemetry. Rewrites imports, span creation, and context propagation.

## Phase 16: Code Understanding & Navigation (v0.5)

85. **Code Explainer** — `code-agents explain-code` / `/explain-code` analyzes any function/class/module with AST parsing. Shows signature, complexity, edge cases, side effects, dependencies, and callers.
86. **Usage Tracer** — `code-agents usage-trace` / `/usage-trace` finds every usage of any symbol across the codebase, grouped by type (import, call, test, config, reference).
87. **Codebase Navigator** — `code-agents nav` / `/nav` semantic search using natural language queries like "where does authentication happen?" with concept expansion and relevance scoring.
88. **Git Story** — `code-agents git-story` / `/git-story` reconstructs the full story behind any line of code: blame, PR, Jira ticket, contributor timeline.
89. **Call Chain Analyzer** — `code-agents call-chain` / `/call-chain` traces full call tree (callers + callees) for any function with depth control and recursion detection.
90. **Code Example Finder** — `code-agents examples` / `/examples` finds real code examples for any concept/library, grouped by pattern (import, definition, call, context_manager).
91. **Dependency Graph Visualizer** — Enhanced `dep-graph` with Mermaid and Graphviz DOT output formats for dependency visualization.
92. **Shared AST Helpers** — Reusable AST parsing utilities (`_ast_helpers.py`) for function/class/import/call extraction used by 15+ modules.
93. **Shared Git Helpers** — Reusable git operation utilities (`_git_helpers.py`) for structured log/blame/diff/branch operations.
94. **Shared Pattern Matchers** — Reusable codebase search utilities (`_pattern_matchers.py`) for grep, usage sites, file matching.
95. **MCP Server Generator Skill** — Skill for generating complete MCP servers from REST/gRPC API specs (OpenAPI, Proto, live URL, source code).

## Phase 17: Debugging & Testing Tools (v0.5)

96. **Stack Trace Decoder** — `code-agents stack-decode` / `/stack-decode` parses Python/Java/JS/Go stack traces, maps to local files, explains the error, suggests fix.
97. **Log Analyzer** — `code-agents log-analyze` / `/log-analyze` parses JSON and plain text logs, correlates by trace ID, builds timeline, identifies root cause.
98. **Environment Differ** — `code-agents env-diff` / `/env-diff` compares env configs between environments with secret masking and critical key detection.
99. **Memory Leak Scanner** — `code-agents leak-scan` / `/leak-scan` detects unclosed resources, growing caches, missing context managers, listener leaks.
100. **Deadlock/Concurrency Scanner** — `code-agents deadlock-scan` / `/deadlock-scan` finds race conditions, lock ordering issues, time.sleep in async, fire-and-forget tasks.
101. **Edge Case Suggester** — `code-agents edge-cases` / `/edge-cases` analyzes function arguments and source to suggest null, empty, boundary, unicode, and error edge cases.
102. **Mock Builder** — `code-agents mock-build` / `/mock-build` generates mock classes with realistic return values and error scenarios from AST analysis.
103. **Test Fixer** — `code-agents test-fix` / `/test-fix` parses pytest failures, diagnoses root cause (code vs test), suggests targeted fixes.
104. **Integration Test Scaffolder** — `code-agents integration-scaffold` / `/integration-scaffold` generates docker-compose, conftest fixtures, and example tests for PostgreSQL, Redis, Kafka, Elasticsearch, MongoDB, RabbitMQ, MySQL, MinIO.

---

## Phase 18: API & Database Tools (v0.6)

105. **Endpoint Generator** — `code-agents endpoint-gen` / `/endpoint-gen` generates complete CRUD endpoints (routes, models, tests) for FastAPI, Express, Flask, Django.
106. **API Spec Sync Checker** — `code-agents api-sync` / `/api-sync` detects drift between OpenAPI/Swagger specs and actual code routes, with sync scoring.
107. **Response Optimizer** — `code-agents response-optimize` / `/response-optimize` scans API endpoints for missing pagination, N+1 queries, no field selection, missing caching.
108. **REST to gRPC Converter** — `code-agents rest-to-grpc` / `/rest-to-grpc` scans REST endpoints and generates `.proto` definitions with proper service grouping and RPC naming.
109. **API Changelog Generator** — `code-agents api-changelog` / `/api-changelog` diffs two OpenAPI spec versions, detects added/removed/modified endpoints, flags breaking changes.
110. **SQL Query Optimizer** — `code-agents query-optimize` / `/query-optimize` static analysis of SQL queries for SELECT *, missing LIMIT, leading wildcards, missing indexes.
111. **Database Schema Designer** — `code-agents schema-design` / `/schema-design` transforms entity JSON into complete schemas with tables, foreign keys, indexes, constraints, SQL output.
112. **ORM Anti-Pattern Reviewer** — `code-agents orm-review` / `/orm-review` scans ORM code for N+1 queries, raw SQL injection, lazy loading in loops, missing eager loading.
113. **API & DB Tool Routers** — `/api-tools/` and `/db-tools/` API endpoints for all 8 tools with Pydantic request models.

---

## Phase 19: Security & Compliance Suite (v0.5)

114. **OWASP Top 10 Scanner** — `code-agents owasp-scan` checks all 10 categories with offline CVE database
115. **Encryption Audit** — `code-agents encryption-audit` flags weak hash/cipher/ECB/static IV/hardcoded keys
116. **Vulnerability Dependency Chain** — `code-agents vuln-chain` traces CVEs through transitive deps
117. **Input Validation Coverage** — `code-agents input-audit` checks endpoint validation completeness
118. **Rate Limit Audit** — `code-agents rate-limit-audit` flags auth/payment endpoints without limits
119. **Privacy Scanner** — `code-agents privacy-scan` detects PII in logs, GDPR/DPDP compliance
120. **Session Management Audit** — `code-agents session-audit` checks JWT expiry, cookie flags, logout
121. **ACL Matrix Generator** — `code-agents acl-matrix` builds role→endpoint matrix, finds escalation
122. **Secret Rotation Tracker** — `code-agents secret-rotation` detects stale secrets, generates runbooks
123. **Compliance Report** — `code-agents compliance-report --standard pci|soc2|gdpr` with control mapping

## Phase 20: Code Quality & Intelligence (v0.5)

124. **Code Smell Detector** — `code-agents smell` finds god classes, long methods, deep nesting
125. **Technical Debt Tracker** — `code-agents tech-debt` scores 0-100 with trend tracking
126. **Import Optimizer** — `code-agents imports --fix` removes unused, finds circular imports
127. **Dead Code Eliminator** — `code-agents dead-code-eliminate --apply` with proof of death
128. **Clone Detector** — `code-agents clones` token-based duplicate detection
129. **Naming Convention Enforcer** — `code-agents naming-audit` checks consistency
130. **ADR Generator** — `code-agents adr` creates Architecture Decision Records
131. **Comment Quality Analyzer** — `code-agents comment-audit` flags outdated/obvious comments
132. **Type Annotation Adder** — `code-agents add-types` infers + adds Python type hints

## Phase 21: Testing & Quality (v0.5)

133. **Mutation Testing** — `code-agents mutate-test` injects code mutations to find weak tests
134. **Property-Based Test Synthesis** — `code-agents prop-test` generates Hypothesis tests
135. **Test Style Matching** — `code-agents test-style` detects AAA/BDD patterns, generates matching
136. **Visual Regression Testing** — `code-agents visual-test` HTML snapshot + diff

## Phase 22: DevOps & Automation (v0.5)

137. **CI Pipeline Self-Healing** — `code-agents ci-heal` autonomous red-to-green loop
138. **Headless/CI Mode** — `code-agents ci-run fix-lint gen-tests review` for pipelines
139. **Batch Operations** — `code-agents batch --instruction "add docstrings" --pattern *.py`

## Phase 23: Frontier Features (v0.5)

140. **Spec-to-Implementation Validator** — `code-agents spec-validate` PRD vs code gap analysis
141. **Screenshot-to-Code** — `code-agents screenshot` UI code from templates
142. **Code Archaeology** — `code-agents archaeology` git blame → PR → issue → intent
143. **Performance Proof** — `code-agents perf-proof` before/after benchmarks with stats
144. **API Contract Testing** — `code-agents contract-test` Pact/Schema test generation
145. **Self-Benchmarking** — `code-agents self-bench` agent quality self-evaluation
146. **Multi-Language Migration** — `code-agents lang-migrate` module migration between languages

## Phase 24: Enterprise & Collaboration (v0.5)

147. **PR Review Threads Agent** — `code-agents pr-respond` responds to PR comments, pushes fixes
148. **Team Knowledge Base** — `code-agents team-kb` git-tracked team KB with search
149. **Onboarding Agent** — `code-agents onboard-tour` guided codebase tour
150. **Browser Interaction Agent** — `code-agents browse` fetch pages, extract API docs
151. **Live Preview Server** — `code-agents preview` serve frontend on localhost

## Phase 25: Developer Productivity (v0.5)

152. **Snippet Library** — `code-agents snippet` save/search reusable code snippets
153. **Environment Diff** — `code-agents env-diff` compare .env across environments
154. **Code Ownership Map** — `code-agents ownership` git blame analysis + CODEOWNERS
155. **Velocity Predictor** — `code-agents velocity-predict` sprint capacity from git history
156. **PR Size Optimizer** — `code-agents pr-split` split PRs by risk/independence
157. **License Audit** — `code-agents license-audit` dependency license compliance + SBOM
158. **Config Validator** — `code-agents validate-config` YAML/JSON/TOML/.env validation
159. **Release Notes AI** — `code-agents release-notes` humanized changelogs

## Phase 26: Global Orchestration (v0.5)

160. **Global Audit Orchestrator** — `code-agents full-audit` runs 14 scanners + 15 quality gates
161. **Smart /commands** — `/commands build` maps intents to agents + relevant commands
162. **Background Agent Detail View** — drill-down with progress, tokens, files, prompt preview

---

## Stats

| Metric | Count |
|--------|-------|
| Commits | 200+ |
| Files changed | 350+ |
| Tests | 8000+ |
| Test coverage | 80% |
| Agents | 18 |
| CLI commands | 130+ |
| Chat slash commands | 140+ |
| Backends | 3 (cursor, claude API, claude CLI) |
| Features | 162 |

---

*Built with Claude Code — every feature designed, implemented, tested, and documented in conversation.*
