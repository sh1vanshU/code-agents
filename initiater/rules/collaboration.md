---
dimension: collaboration
severity: info
---

# Collaboration — Contributing & Code Ownership

## Purpose
Clear contribution guidelines reduce friction for new contributors and maintain quality.

## Rules
- [ ] CONTRIBUTING.md or contributing section exists
- [ ] PR process is documented
- [ ] Branch naming convention is stated
- [ ] Code review expectations are set
- [ ] Issue/bug reporting process is documented
- [ ] License file exists and is referenced
- [ ] Development setup instructions work (poetry install, pytest)

## Verification
```bash
# Check for contributing docs
test -f CONTRIBUTING.md && echo "exists" || grep -l 'Contributing' README.md

# Check license
test -f LICENSE && echo "LICENSE exists"

# Verify dev setup
poetry install --with dev 2>&1 | tail -3
```

## References
- `README.md` (Contributing section)
- `LICENSE`
- `pyproject.toml`

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

