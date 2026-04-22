---
dimension: repo-map
severity: warning
---

# Repo Map — Project Structure & Organization

## Purpose
The project structure documented in README.md should match reality. Orphaned files or undocumented directories confuse contributors.

## Rules
- [ ] README.md "Project Structure" tree matches actual file layout
- [ ] No orphaned files in root that should be in subdirectories
- [ ] All Python packages have __init__.py
- [ ] scripts/ directory contents are documented or self-explanatory
- [ ] examples/ directory has its own README or inline docs
- [ ] No generated files committed (build artifacts, __pycache__, .pyc)

## Verification
```bash
# Compare README tree with actual structure
# (visual inspection — automated diff is in run_audit.py)

# Check for __pycache__ or .pyc in git
git ls-files '*.pyc' '__pycache__'

# List root files
ls -1 *.* 2>/dev/null
```

## References
- `README.md` (Project Structure section)
- Root directory listing

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

