# Roadmap — Code Agents

Future ideas and planned implementations. Items move to CHANGELOG.md once shipped.

---

## Production Deployment Support

**Priority: High**

Currently the jenkins-cicd agent only deploys to non-prod environments (dev, dev-stable, staging, qa, uat). Production deployments need:

- Strict approval gates — require explicit confirmation from authorized users
- Rollback plan — mandatory rollback strategy documented before deploy
- Canary/blue-green support — gradual rollout with health checks
- Post-deploy monitoring — automatic ArgoCD + Grafana checks after production deploy
- Audit trail — log who deployed what, when, with which approval

---

## Planned Features

### Agent Improvements
- [x] Multi-model routing, agent memory, agent chaining, cross-agent skill sharing — shipped
- [x] Agent benchmarking — compare agent quality across backends/models — shipped v0.7.0
- [x] Confidence scoring — auto-suggests delegation to specialist on low scores — shipped
- [ ] Parallel agent execution — run code-reviewer + test-coverage simultaneously
- [ ] Agent confidence calibration — auto-tune confidence thresholds from user feedback
- [ ] Multi-agent consensus — run N agents on same prompt, merge best answers
- [ ] Automatic skill generation — learn new skills from repeated user workflows
- [ ] Prompt optimization — A/B test system prompts for quality improvement

### CI/CD Pipeline
- [ ] Production deployment with approval gates
- [ ] Multi-environment promotion (dev → staging → prod)
- [ ] Rollback automation — one-click rollback with ArgoCD
- [ ] Pipeline templates — pre-built flows for common patterns
- [ ] Build cache optimization — skip redundant builds

### From PENDING.md — Future Feature Ideas

#### Dev Productivity
- [ ] Git Bisect Agent (`bisect`) — automated git bisect with AI diagnosis
- [ ] Merge Conflict Resolver (`/resolve-conflicts`) — AI-powered semantic merge

#### Infrastructure & DevOps
- [ ] Dockerfile Optimizer (`optimize-docker`) — layer caching, multi-stage, security
- [ ] K8s Manifest Validator (`k8s-validate`) — resource limits, probes, PDB, privileged
- [ ] Terraform Plan Analyzer (`tf-analyze`) — destructive changes, cost impact
- [ ] CI/CD Pipeline Optimizer (`ci-optimize`) — slow stages, missing cache, parallelism
- [ ] Log Pattern Classifier (`log-classify`) — error taxonomy from log files
- [ ] Infra Cost Estimator (`infra-cost`) — monthly cost from K8s + terraform
- [ ] Database Query Optimizer (`query-optimize`) — missing indexes, full scans, N+1
- [ ] Feature Flag Cleanup (`feature-flags`) — stale flags, unreferenced
- [ ] Service Dependency Graph (`service-graph`) — cross-repo service map, circular deps
- [ ] Disaster Recovery Validator (`dr-validate`) — backup configs, RTO/RPO, failover

#### Payment Gateway Advanced
- [ ] Payment Flow Simulator (`simulate`) — end-to-end payment flow against staging
- [ ] BIN Range Validator (`bin-validate`) — check BIN tables against Visa/MC/RuPay
- [ ] Merchant Onboarding Validator (`merchant-validate`) — config, risk tier, webhook, KYC
- [ ] Payment Gateway Health Score (`pg-health`) — overall health combining all metrics
- [ ] Transaction Anomaly Detector (`txn-anomaly`) — volume spikes, new errors, velocity
- [ ] Refund Chain Tracker (`refund-trace`) — refund lifecycle tracing
- [ ] Multi-Currency Test Suite (`currency-test`) — decimal precision, FX, rounding
- [ ] Payment API Versioning Checker (`api-version-check`) — schema drift between environments
- [ ] Acquirer Failover Simulator (`failover-sim`) — primary failure → fallback routing
- [ ] Chargeback Prevention Advisor (`chargeback-advisor`) — pattern analysis + prevention rules

#### Architecture Improvements (Wiring)
- [ ] Audit quality gates from `.foundry/casts/` — wire into audit_orchestrator gate checks
- [ ] Agent corrections injection — wire `inject_corrections()` into system prompt builder
- [ ] RAG context injection — wire `RAGContextInjector.get_context()` into message preparation
- [ ] Trace recording — wire `TraceRecorder.record_step()` into chat_response.py

### Tab Selector v2 — Claude Code Style Approval

**Priority: High**

Redesign the Tab selector to match Claude Code's approval flow:

```
  ┌────────────────────────────────────────────────────┐
  │ $ mvn clean install -DskipTests                     │
  └────────────────────────────────────────────────────┘
  ❯ 1. Yes
    2. Yes, allow all during session (shift+tab)
    3. No

  Esc to cancel · Tab to amend
```

- [ ] **Tab to amend** — pressing Tab tells agent what to change
- [ ] **Shift+Tab = allow all** — auto-approve all similar commands for this session
- [ ] **Esc to cancel** — cancel the command (same as No)
- [ ] **Numbered options** — 1/2/3 keys for quick selection
- [ ] **Session memory** — "allow all" remembers command patterns
- [ ] **Implementation**: Modify `_tab_selector()` in `chat_ui.py` or TS `CommandApproval.tsx`

### Claude CLI Style Activity Indicators

**Priority: High**

When agents are executing, show Claude CLI-style blinking activity dot:

```
  ⏺ Update(code_agents/cli/cli.py)
  ⏺ Reading(src/PaymentService.java)
  ⏺ Writing(src/PaymentServiceTest.java)
  ⏺ Running(mvn test)
```

- [ ] **Blinking activity dot** — `⏺` blinks while agent is streaming/executing
- [ ] **Action labels** — `Update()`, `Reading()`, `Writing()`, `Running()`, `Analyzing()` parsed from SSE stream
- [ ] **Spinner replacement** — replace current "Thinking..." spinner with blinking dot + action label
- [ ] **Implementation**: Modify `_spinner()` in `chat_ui.py`, parse `reasoning_content` from SSE stream

### Agent Response Box Formatting

**Priority: High**

- [ ] **Terminal** — wrap agent streaming output in box with agent name + color (post-stream)
- [ ] **Web UI** — agent message bubbles with colored header bar showing agent name
- [ ] **Sub-agent delegation** — show sub-agent response in nested/indented box

### TUI Rewrite — Fixed Input at Bottom

**Priority: High** — Python Phase 1 COMPLETED, TypeScript terminal COMPLETED (v0.7.0)

- [x] `prompt_toolkit` dependency, REPL rewrite, autocomplete dropdown, `CODE_AGENTS_SIMPLE_UI=true` fallback — shipped
- [x] **TypeScript terminal client** — oclif + Ink, split-screen layout, streaming, multi-line input — shipped v0.7.0
- [x] **Background agents (Ctrl+B)** — push tasks to background, Ctrl+F to foreground, parallel execution — shipped v0.4.0
- [ ] **Fixed bottom toolbar** (Python TUI) — shows agent name, user role, superpower status, token count
- [ ] **Keybindings** (Python TUI) — Tab to amend, Esc to cancel, Ctrl+C interrupt

### Integrations
- [x] GitHub Actions support — alongside Jenkins — shipped v0.4.0
- [ ] GitLab CI support
- [ ] Kubernetes direct deploy — bypass ArgoCD for simple cases
- [x] Grafana dashboard integration — check metrics post-deploy — shipped v0.4.0
- [ ] SonarQube code quality gates
- [ ] Artifactory/Nexus artifact management

### Endpoint & Contract Auto-Discovery
- [x] Auto-discover endpoints, generate test suite, `/endpoints` slash command, endpoint runner — shipped
- [x] **Integration test file** — `tests/test_integration_wiring.py` verifies CLI registry, routers, agent YAMLs, imports, loggers — shipped v0.7.0
- [ ] **DB query discovery** — scan repo for JPA repositories, MyBatis mappers, raw SQL. Cache alongside endpoints. Feed to redash-query agent. `/endpoints db` to list.

### Sanity Check Sub-Agent
- [x] `sanity_checker.py`, Kibana log monitoring, custom per-repo rules, format report — shipped
- [ ] **Auto-trigger** — sanity check runs automatically after ArgoCD deploy. `CODE_AGENTS_AUTO_SANITY=true`.

### Web UI Fixes

**Priority: High**

- [ ] **Enter key** — verify sendMessage fires on Enter, not Shift+Enter
- [ ] **Streaming display** — verify SSE parsing matches server output format
- [ ] **Mobile responsive** — sidebar toggle, input area on small screens
- [ ] **Error states** — show meaningful errors when API calls fail

### Slack + Gmail MCP OAuth Chain

**Priority: Medium**

- [ ] OAuth orchestration: Gmail OAuth → Slack OAuth → store tokens in `~/.code-agents/oauth/`
- [ ] OAuth callback server — temporary local HTTP server for OAuth callbacks
- [ ] MCP config auto-setup after OAuth success
- [ ] Token refresh — auto-refresh expired tokens
- [ ] `/setup slack` and `/setup gmail` in-chat OAuth flows

### Slack Bot Integration (Bidirectional)

**Priority: Medium**

- [ ] Slack → code-agents (incoming) — `@code-agents deploy pg-acquiring-biz to dev` forwarded to auto-pilot
- [ ] Thread context — multi-turn agent chat within a Slack thread
- [ ] `/deploy`, `/status`, `/review` Slack slash commands
- [ ] MCP Slack integration for read/write Slack channels

### Auto-Run QA Regression on Init

**Priority: High**

- [ ] Background regression baseline on `code-agents init` — test suite, endpoint discovery, perf baseline, DB query scan
- [ ] On next `code-agents chat` — agent sees baseline summary
- [ ] Auto-trigger on code change — suggest re-running regression when `git diff` detects changes

### Infrastructure
- [ ] Multi-user support — shared server with user authentication
- [ ] Caching layer — cache common agent responses
- [ ] Plugin system — third-party agent plugins

### Sanskrit Naming Conventions

**Priority: Medium**

- [ ] Agent display names — Sanskrit titles alongside English (Sarathi, Rachnakar, Parikshak, etc.)
- [ ] CLI branding — optional alias "dev-sarathi"
- [ ] Welcome messages — Sanskrit greeting "नमस्ते" before welcome box

### One-Command Curl Install

**Priority: Low (blocked by company restrictions)**

- [ ] Curl install once repo is public or proxy is set up
- [ ] Alternative: host `install.sh` on internal CDN/S3
- [ ] Homebrew tap: `brew install code-agents-org/tap/code-agents`

---

## Major Refactor: Claude Code Architecture Alignment — COMPLETED

**Phases 1–5 shipped.** Package reorganization into `analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` with backward-compat re-exports; CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (#15) + `SubagentDispatcher`; `BashTool` for shell execution; slim chat modules (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). All tests pass. Full history in CHANGELOG.md.

Remaining open item from this refactor:
- [ ] Numbered keys (1/2/3) for quick selection in tab selectors (see Tab Selector v2 above)

---

## Completed (moved to CHANGELOG.md)

All items below shipped; see CHANGELOG.md for details.

- Token tracking, Claude CLI backend, agent rules, auto-pilot, git pre-check, backend/model env vars → v0.2.0
- On-demand skill loading, agent subfolders with skills/ → v0.2.0
- Jira/Confluence, Kibana, Plan mode, Superpower mode, smart test failure classification → unreleased
- SDLC pipeline, local build support, Tab Selector Edit option, full git operations → unreleased
- Ctrl+C graceful interrupt, command validation filter, interactive questionnaire → unreleased
- User profile & designation, telemetry dashboard, voice input, endpoint runner → unreleased
- Terminal layout, Web UI redesign, Init Quick Links → unreleased
- Major refactor Phases 1–5 (package reorg, command registry, explore agent, BashTool, slim chat) → unreleased
- Session scratchpad, upfront CI/CD questionnaire, Enter-to-submit, `[REMEMBER:]` tag system → v0.3.0
- 28 platform features (mindmap, code review, dep impact, corrections, multi-repo, git hooks, replay, RAG, live tail, pair mode, background agents, API docs, code translator, profiler, schema viz, changelog, health dashboard, txn flow, recon debugger, PCI scanner, idempotency auditor, state machine validator, acquirer health, retry analyzer, load test gen, postmortem gen, settlement parser, OTel migration) → v0.4.0
- 5 new agents (GitHub Actions, Grafana Ops, Terraform/IaC, DB Ops, PR Review Bot, Debug Agent) → v0.4.0
- Bug fixes: ANSI rendering, command panel, spinner, skill tags, input prompt, response indentation, curl quoting, command execution errors → v0.4.0
- Module reorganization: 174 flat files → 12 subdirectories, 819 imports updated → v0.7.0
- TypeScript terminal client: 10 phases, 54 files, 79 tests → v0.7.0
- 71 new developer productivity tools (Sessions 4-10): security, reviews, testing, observability, knowledge, DevOps, git ops → v0.7.0
- Integration health checks: credential + connectivity for all 7 integrations → v0.7.0
- Security hardening: 9 fixes in TS terminal → v0.7.0
- OTel span wiring: backend, stream, skill_loader → v0.7.0
- 600+ new tests → v0.7.0
- Integration wiring test (CLI, routers, agents, imports, loggers) → v0.7.0
- RELEASE-NOTES.md v0.7.0 entry, ROADMAP.md update, CURSOR.md/GEMINI.md sync → v0.7.0

---

## Future Roadmap (50 Features)

### Agent Intelligence
- [ ] Agent confidence calibration — auto-tune confidence thresholds from user feedback
- [ ] Multi-agent consensus — run N agents on same prompt, merge best answers
- [ ] Agent personality profiles — configurable tone (formal/casual/terse)
- [ ] Automatic skill generation — learn new skills from repeated user workflows
- [ ] Context-aware agent routing — auto-select agent based on file types in diff
- [x] Agent benchmarking — compare agent quality across backends/models — shipped v0.7.0
- [ ] Prompt optimization — A/B test system prompts for quality improvement
- [ ] Agent collaboration graph — visualize which agents delegate to which

### Code Quality
- [x] Mutation testing — inject bugs, verify tests catch them — shipped v0.7.0
- [ ] Architecture fitness functions — validate architectural rules on every commit
- [x] Tech debt scoring — quantify and track technical debt over time — shipped v0.7.0
- [x] Code smell detection — Martin Fowler catalog with auto-fix suggestions — shipped v0.7.0
- [x] Dependency license compliance — SPDX validation + policy enforcement — shipped v0.7.0
- [x] API contract testing — Pact/consumer-driven contract generation — shipped v0.7.0
- [x] Visual regression testing — screenshot comparison for web UIs — shipped v0.7.0
- [ ] Flaky test detector — identify and quarantine non-deterministic tests

### Developer Experience
- [ ] AI code completion server — LSP-compatible completion provider
- [ ] Smart search — semantic code search across repos (not just grep)
- [ ] Commit message generator v2 — multi-line with issue linking
- [ ] PR auto-labeler — categorize PRs by type/area from diff analysis
- [ ] Code tour generator — interactive walkthroughs for onboarding
- [ ] Refactoring catalog — named refactorings with preview and undo
- [ ] Terminal UI v2 — split panes (code + chat side by side)
- [ ] Session sharing — share agent sessions with teammates via URL
- [ ] Offline mode — local LLM fallback when API is unavailable

### Infrastructure & DevOps
- [ ] GitLab CI support — alongside Jenkins and GitHub Actions
- [ ] AWS CloudFormation support — alongside Terraform
- [ ] Pulumi IaC support — TypeScript/Python infrastructure
- [ ] Kubernetes direct deploy — bypass ArgoCD for simple cases
- [ ] SonarQube quality gates — block deploys on quality threshold
- [ ] Artifactory/Nexus artifact management
- [ ] Docker Compose orchestration — local multi-service management
- [ ] Service mesh debugging — Istio/Linkerd traffic analysis
- [ ] Cost optimization — cloud spend analysis and recommendations

### Payment Domain
- [ ] Chargeback analyzer — dispute pattern detection and response templates
- [ ] Fraud rule engine — create and test fraud detection rules
- [ ] Currency conversion auditor — FX rate validation and margin checks
- [ ] Webhook delivery monitor — track and retry failed payment webhooks
- [ ] 3DS authentication flow debugger — trace challenge/frictionless flows
- [ ] Tokenization vault inspector — verify token lifecycle and rotation
- [ ] Multi-acquirer routing optimizer — suggest optimal routing rules

### Platform
- [ ] Multi-user support — shared server with authentication
- [ ] Plugin marketplace — third-party agent and skill distribution
- [ ] Slack bot v2 — thread-based multi-turn conversations
- [ ] Discord bot — same as Slack but for Discord communities
- [ ] Homebrew tap — `brew install code-agents-org/tap/code-agents`
- [ ] Curl install — one-line install when repo goes public
- [ ] OAuth chain — Gmail + Slack + GitHub OAuth orchestration
- [ ] MCP server mode — `code-agents serve --mcp` for external tool use
