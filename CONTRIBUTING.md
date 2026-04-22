# Contributing to Code Agents

Copyright (c) 2026 Code Agents Contributors (Regulated by RBI)

## Change Checklist

When making changes to the project, use this checklist to ensure everything stays in sync.
Not all items apply to every change — only update what's relevant.

### Adding a New Agent

- [ ] Create `agents/<name>.yaml`
- [ ] Add to `agents/agent_router.yaml` system prompt (specialists list)
- [ ] Add role to `AGENT_ROLES` dict in `code_agents/chat/chat.py`
- [ ] Add example prompts to `_AGENT_EXAMPLES` dict in `code_agents/cli/cli.py`
- [ ] Add to `Agents.md` with its own section
- [ ] Add to `README.md` agents table
- [ ] Add to `CLAUDE.md` architecture section
- [ ] Add to `cursor.md` architecture section
- [ ] Add tests if agent has special behavior
- [ ] Run: `poetry run python initiater/run_audit.py --rules workflow`

### Adding a New CLI Command

- [ ] Add function `cmd_<name>()` in `code_agents/cli.py`
- [ ] Add to `COMMANDS` dict in `cli.py`
- [ ] Add to `cmd_help()` — with full args, description, and examples
- [ ] Add to dispatcher in `main()` function
- [ ] Add tests in `tests/test_cli.py`
- [ ] Update `README.md` CLI commands table
- [ ] Update `CLAUDE.md` quick reference
- [ ] Update `cursor.md` quick reference

### Adding a New Chat Slash Command

- [ ] Add handler in `_handle_command()` in `code_agents/chat.py`
- [ ] Add to `/help` output inside `_handle_command()`
- [ ] Add to `cmd_help()` chat slash commands section in `cli.py`
- [ ] Add to tab-completion list in `_slash_commands` inside `chat_main()`
- [ ] Add tests in `tests/test_chat.py` TestSlashCommands class
- [ ] Update `Agents.md` chat commands list

### Adding a New REST API / Router

- [ ] Create `code_agents/routers/<name>.py`
- [ ] Create client `code_agents/<name>_client.py` (if external API)
- [ ] Register router in `code_agents/app.py`
- [ ] Add curl examples to `_print_curl_sections()` in `cli.py`
- [ ] Add category to `cmd_curls()` categories list
- [ ] Add to `code-agents curls` help text
- [ ] Add tests in `tests/test_routers.py`
- [ ] Add env vars to `.env.example`
- [ ] Add to `code-agents doctor` checks in `cli.py`
- [ ] Update `README.md` — REST APIs section, env vars table
- [ ] Update `CLAUDE.md` architecture section
- [ ] Update `cursor.md` architecture section

### Adding a New Integration (Jenkins, ArgoCD, etc.)

- [ ] Create client module `code_agents/<name>_client.py`
- [ ] Create router `code_agents/routers/<name>.py`
- [ ] Create agent YAML `agents/<name>.yaml`
- [ ] Add env vars to `.env.example` and `.env` template in `setup.py`
- [ ] Add to `code-agents doctor` checks
- [ ] Add to `code-agents curls` sections
- [ ] Add to `code-agents init` prompts in `cli.py` or `setup.py`
- [ ] Follow "Adding a New Agent" checklist above
- [ ] Follow "Adding a New REST API" checklist above

### Changing Environment Variables

- [ ] Update `.env.example` with description
- [ ] Update `code_agents/setup.py` prompts (if user-facing)
- [ ] Update `code_agents/cli.py` `cmd_init()` prompts
- [ ] Update `code-agents doctor` checks
- [ ] Update `README.md` env vars table
- [ ] Update `CLAUDE.md` environment section
- [ ] Update `cursor.md` environment section

### Updating Tests

- [ ] Run: `poetry run pytest` — all tests must pass
- [ ] Update test count in: `README.md`, `CLAUDE.md`, `cursor.md`
- [ ] If new test file: add to `README.md` project structure

---

## Files That Reference Each Other

These files must stay in sync. When you change one, check the others:

| What changed | Files to update |
|-------------|----------------|
| Agent list | `agent_router.yaml`, `chat.py` (AGENT_ROLES), `cli.py` (_AGENT_EXAMPLES + help), `Agents.md`, `README.md`, `CLAUDE.md`, `cursor.md` |
| CLI commands | `cli.py` (function + COMMANDS + help + dispatcher), `README.md`, `CLAUDE.md`, `cursor.md` |
| Chat slash commands | `chat.py` (_handle_command + /help + _slash_commands list), `cli.py` (cmd_help chat section), `test_chat.py`, `Agents.md` |
| Chat history | `chat_history.py` (CRUD), `chat.py` (auto-save + /history + /resume), `stream.py` (build_prompt), `cli.py` (cmd_sessions), `test_chat_history.py` |
| REST endpoints | `routers/*.py`, `cli.py` (curls), `README.md`, `CLAUDE.md`, `cursor.md` |
| Env variables | `.env.example`, `setup.py`, `cli.py` (init + doctor), `README.md`, `CLAUDE.md`, `cursor.md` |
| Backends | `backend.py` (dispatch), `cli.py` (init --backend), `env_loader.py` (GLOBAL_VARS), `CLAUDE.md`, `README.md`, `Agents.md`, `cursor.md` |
| Agent rules | `rules_loader.py` (loader), `chat.py` (injection + /rules), `stream.py` (server-side injection), `cli.py` (cmd_rules), `README.md`, `Agents.md`, `CLAUDE.md`, `cursor.md` |
| Test count | `README.md` (badge + text), `CLAUDE.md`, `cursor.md` |
| Copyright | `LICENSE`, `README.md` footer, `Agents.md` footer |
| Install URL | `install.sh`, `cli.py` (cmd_help), `README.md` |
| IDE extensions | `extensions/vscode/`, `extensions/intellij/`, `install.sh` (build section), `cli.py` (cmd_plugin), `cli_doctor.py` (IDE section), `cli_completions.py`, `README.md`, `ARCHITECTURE.md`, `CLAUDE.md`, `cursor.md` |

---

## IDE Extension Development

### VS Code Extension

```bash
cd extensions/vscode
npm install && cd webview-ui && npm install && cd ..
npm run build:webview    # Build shared chat UI (Vite)
npm run compile          # Bundle extension (esbuild)
npm run lint             # Type-check (tsc --noEmit)
npm test                 # Run 42 tests (vitest)
# Press F5 in VS Code → Extension Development Host
```

### IntelliJ Plugin

```bash
cd extensions/intellij
# Copy webview first (shared with VS Code):
cd ../vscode/webview-ui && npm run build && cd ../../intellij
cp -r ../vscode/webview-ui/build/* src/main/resources/webview/
./gradlew buildPlugin    # Compile Kotlin + package
./gradlew runIde         # Launch sandboxed IDE
./gradlew test           # Run tests
```

### Shared Webview UI

The chat UI at `extensions/vscode/webview-ui/` is shared by VS Code (WebviewViewProvider), IntelliJ (JCEF), and Chrome (side panel). Changes here affect all three. The `window.IDE` bridge abstraction detects the host environment automatically.

### Using the Makefile

```bash
cd extensions
make all         # Build both
make test        # Test both
make package     # Create .vsix + .zip
make clean       # Remove artifacts
```

---

## Adding a New Feature Module

The standard pattern for adding a new feature (used for all 28 modules added in the 2026-04-09 session):

1. **Core module** — Create `code_agents/<module>.py` with the feature logic. Keep it lazy-loadable (no heavy imports at module level).
2. **CLI handler** — Add `cmd_<name>()` function in the appropriate `code_agents/cli/cli_*.py` file. Register in `COMMANDS` dict and dispatcher.
3. **Slash command handler** — Add handler in `code_agents/chat/chat_slash_*.py` (ops, tools, or agents depending on category). Register in the slash command registry.
4. **Registry entry** — Add to `code_agents/cli/registry.py` so the command appears in help and discovery.
5. **Shell completions** — Add to `code_agents/cli/cli_completions.py` so the command tab-completes in bash/zsh/fish.
6. **Tests** — Create `tests/test_<module>.py` with unit tests using mocks (no external services). Match the module name.
7. **Documentation** — Update `ARCHITECTURE.md`, `CLAUDE.md`, `CURSOR.md`, `GEMINI.md`, and `PROJECT_OVERVIEW.md` with the new module.

Example (adding `profiler.py`):
```
code_agents/profiler.py          # Core logic
code_agents/cli/cli_analysis.py  # cmd_profile() added
code_agents/chat/chat_slash_tools.py  # /profile handler
code_agents/cli/registry.py     # "profile" entry
code_agents/cli/cli_completions.py  # "profile" in completions
tests/test_profiler.py           # Unit tests
```

This pattern ensures every feature is discoverable via CLI, chat, and tab-completion from day one.

---

## Dev Workflow

```bash
# Install dev dependencies
poetry install --with dev

# Run tests
poetry run pytest

# Check project quality
poetry run python initiater/run_audit.py

# Verify CLI works
code-agents help
code-agents doctor
code-agents agents

# Test a change interactively
code-agents start
code-agents chat
```

---

## Commit Message Format

```
<type>: <short description>

<body — what changed and why>

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`


