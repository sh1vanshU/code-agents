# Pending Items — Code Agents v0.7.0

Last updated: 2026-04-09

---

## Infrastructure / Quality

| # | Item | Priority | Effort |
|---|------|----------|--------|
| 1 | **Full test suite run** — `poetry run pytest tests/` end-to-end verification | High | 5 min |
| 2 | **Import smoke test** — verify all 80+ modules import without error | High | 5 min |
| 3 | **Integration test file** — `tests/test_integration_wiring.py` to verify all registrations (CLI registry, slash registry, completions, loggers, CLAUDE.md) | Medium | 30 min |
| 4 | **Logging Phase 5** — add OTel spans to agent calls, CI/CD clients, skill loading | Low | 2 hr |
| 5 | **Pre-existing test fix** — `test_backend.py::TestClaudeCliStreamEdgeCases::test_stream_timeout` fails due to renamed `_stream_claude_cli` | Low | 10 min |

## Documentation Updates

| # | Item | Priority | Effort |
|---|------|----------|--------|
| 6 | **RELEASE-NOTES.md** — add v0.7.0 entry (currently only has v0.4.0) | Medium | 15 min |
| 7 | **ROADMAP.md** — mark 80 features as completed, update future roadmap | Medium | 15 min |
| 8 | **CURSOR.md** — sync with CLAUDE.md (add last 52 modules) | Medium | 10 min |
| 9 | **GEMINI.md** — sync with CLAUDE.md (add last 52 modules) | Medium | 10 min |

## Features Discussed But Not Implemented

### Dev Productivity (from 50 feature suggestions)
| # | Feature | CLI | Description |
|---|---------|-----|-------------|
| 10 | Git Bisect Agent | `bisect` | Automated git bisect with AI diagnosis |
| 11 | Merge Conflict Resolver | — | `/resolve-conflicts` AI-powered semantic merge |

### Infrastructure & DevOps (from 50 feature suggestions)
| # | Feature | CLI | Description |
|---|---------|-----|-------------|
| 12 | Dockerfile Optimizer | `optimize-docker` | Layer caching, multi-stage, security |
| 13 | K8s Manifest Validator | `k8s-validate` | Resource limits, probes, PDB, privileged |
| 14 | Terraform Plan Analyzer | `tf-analyze` | Destructive changes, cost impact |
| 15 | CI/CD Pipeline Optimizer | `ci-optimize` | Slow stages, missing cache, parallelism |
| 16 | Log Pattern Classifier | `log-classify` | Error taxonomy from log files |
| 17 | Infra Cost Estimator | `infra-cost` | Monthly cost from K8s + terraform |
| 18 | Database Query Optimizer | `query-optimize` | Missing indexes, full scans, N+1 |
| 19 | Feature Flag Cleanup | `feature-flags` | Stale flags, unreferenced |
| 20 | Service Dependency Graph | `service-graph` | Cross-repo service map, circular deps |
| 21 | Disaster Recovery Validator | `dr-validate` | Backup configs, RTO/RPO, failover |

### Payment Gateway Advanced (from 50 feature suggestions)
| # | Feature | CLI | Description |
|---|---------|-----|-------------|
| 22 | Payment Flow Simulator | `simulate` | End-to-end payment flow against staging |
| 23 | BIN Range Validator | `bin-validate` | Check BIN tables against Visa/MC/RuPay |
| 24 | Merchant Onboarding Validator | `merchant-validate` | Config, risk tier, webhook, KYC |
| 25 | Payment Gateway Health Score | `pg-health` | Overall health combining all metrics |
| 26 | Transaction Anomaly Detector | `txn-anomaly` | Volume spikes, new errors, velocity |
| 27 | Refund Chain Tracker | `refund-trace` | Refund lifecycle tracing |
| 28 | Multi-Currency Test Suite | `currency-test` | Decimal precision, FX, rounding |
| 29 | Payment API Versioning Checker | `api-version-check` | Schema drift between environments |
| 30 | Acquirer Failover Simulator | `failover-sim` | Primary failure → fallback routing |
| 31 | Chargeback Prevention Advisor | `chargeback-advisor` | Pattern analysis + prevention rules |

## UI Issues

| # | Item | Priority |
|---|------|----------|
| 32 | Background Agent Detail View — live token/tool counters need real data feed from execute_fn callback | Medium |
| 33 | Questionnaire — test the alignment fix end-to-end in live chat session | Low |

## Architecture Improvements

| # | Item | Priority |
|---|------|----------|
| 34 | **Audit quality gates from .foundry/casts/** — 15 gates defined in plan, need to wire into audit_orchestrator gate checks with actual foundry cast file reading | High |
| 35 | **Agent corrections injection** — wire `inject_corrections()` into `chat_context.py` system prompt builder | Medium |
| 36 | **RAG context injection** — wire `RAGContextInjector.get_context()` into message preparation before agent calls | Medium |
| 37 | **Trace recording** — wire `TraceRecorder.record_step()` into `chat_response.py` after each message | Medium |

---

*This file tracks all pending work. Check items off as completed.*
