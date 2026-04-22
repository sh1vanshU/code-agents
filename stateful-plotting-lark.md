# Hybrid Migration Plan: TypeScript Terminal Client for Code Agents

## Context

The Python server (FastAPI, agents, integrations, parsers) stays untouched — it's the headless engine. Only the terminal-facing code (CLI + Chat REPL + TUI, ~15-20K LOC) gets rewritten in TypeScript using **oclif** (CLI) and **Ink** (React for terminals). This gives us rich, composable terminal UIs (split panes, animated streaming, interactive widgets, syntax highlighting) that Python's prompt-toolkit/Textual cannot achieve natively.

**Architecture**: Two processes. `code-agents start` → Python server on localhost:8000. `code-agents chat` → Node.js/TS terminal client consuming the HTTP/SSE API.

**Branch**: `typescript-terminal` off `main`
**Directory**: `terminal/` at repo root (self-contained package)

---

## How TS Wires Up with Python (The Integration Model)

### Two Processes, One Product
```
$ code-agents start          ← Spawns Python FastAPI server (background, port 8000)
$ code-agents chat --ts      ← Launches Node.js/TS terminal client (foreground)
```

No new IPC protocol, no sockets, no shared memory. **Just HTTP + shared files** — the same way the VS Code/Chrome/IntelliJ extensions already work.

### Wire Protocol (already exists — OpenAI-compatible)
```
TS Terminal                                    Python Server
───────────                                    ─────────────
POST /v1/agents/{name}/chat/completions  ───►  FastAPI router
  { messages, stream: true, session_id, cwd }
                                          ◄───  SSE stream:
                                                data: {"choices":[{"delta":{"content":"token"}}]}
                                                data: {"choices":[...],"usage":{...},"duration_ms":3200}
                                                data: [DONE]

GET  /health                             ───►  { status: "ok" }
GET  /v1/agents                          ───►  Agent list
GET  /knowledge-graph/*                  ───►  Codebase index
POST /git/*, /jenkins/*, /testing/*      ───►  Integrations (35+ routers)
```

### Chat Message Flow
1. User types in TS terminal (Ink TextInput)
2. TS client POSTs to `http://localhost:8000/v1/agents/{agent}/chat/completions`
3. Python server: loads agent config → injects rules/memory → calls Claude/Cursor backend → streams SSE
4. TS client renders tokens in real-time (Ink StreamingResponse component)
5. If response contains ```bash blocks → TS shows approval widget → executes locally via `child_process`
6. Command output fed back to server as next message (agentic loop)

### What Runs Where
| Concern | TS (Node.js) | Python (server) |
|---------|-------------|-----------------|
| Terminal UI, input, rendering | Yes | — |
| Slash command dispatch | Yes | — |
| Mode cycling (Chat/Plan/Edit) | Yes | — |
| Session history (read/write JSON) | Yes | — |
| Bash command execution | Yes | — |
| Agent routing & AI calls | — | Yes |
| Skill loading & injection | — | Yes |
| Backend dispatch (Claude/Cursor) | — | Yes |
| SSE streaming generation | — | Yes |
| Knowledge graph building | — | Yes |
| CI/CD integrations | — | Yes |

### Server Spawning (`start` command)
```typescript
// TS spawns Python as a detached subprocess
const server = spawn('poetry', ['run', 'python', '-m', 'code_agents.main'], {
  cwd: codeAgentsDir,  // ~/.code-agents
  env: { ...process.env, HOST: '0.0.0.0', PORT: '8000' },
  detached: true, stdio: 'ignore'
});
server.unref();
// Then poll GET /health until 200
```

### Shared State (file-based, both read/write same format)
- `~/.code-agents/chat_history/*.json` — Session persistence (interoperable)
- `~/.code-agents/agent_memory/*.txt` — Long-term agent facts
- `/tmp/code-agents/<sid>/state.json` — Session scratchpad
- `~/.code-agents/config.env` — Global config
- `<repo>/.env.code-agents` — Per-repo config

---

## Phase 1: Repo Setup + Build Infrastructure
**Complexity: S | ~1-2 days**

### Create branch and directory structure:
```
git checkout -b typescript-terminal

terminal/
├── package.json            # oclif + ink + react + zod + dependencies
├── tsconfig.json           # strict, ESM, target ES2022, paths aliases
├── tsup.config.ts          # Bundle to dist/
├── vitest.config.ts        # Test runner
├── bin/
│   └── run.ts              # oclif CLI entry (#!/usr/bin/env tsx)
├── src/
│   └── index.ts            # Re-exports
└── tests/
    └── fixtures/           # Canned SSE payloads, mock agent data
```

### Dependencies:
```
dependencies:
  @oclif/core, @oclif/plugin-help, @oclif/plugin-autocomplete
  ink (^5), @inkjs/ui, ink-text-input, ink-select-input, ink-spinner
  react (^18), react-dom
  zod, chalk (^5), zustand
  better-sqlite3, undici
  marked, marked-terminal, shiki

devDependencies:
  typescript (^5.5), tsx, tsup
  vitest, ink-testing-library, @types/react, @types/better-sqlite3
```

### Config:
- ESM-only (`"type": "module"`)
- Node >= 18 (native fetch, AbortController, ReadableStream)
- tsup bundles to `dist/`, bin entry is `bin/run.js`

---

## Phase 2: Core Client Layer (API + Server Communication)
**Complexity: M | ~3-4 days**

### Files:
```
terminal/src/client/
  ApiClient.ts              # HTTP + SSE streaming
  AgentService.ts           # Agent list, current agent, defaults
  ServerMonitor.ts          # Health polling
  types.ts                  # Zod schemas for API responses
```

### Source: Reuse from VS Code extension
- Copy `/extensions/vscode/src/services/ApiClient.ts` as starting point
- Already has: SSE streaming, buffer overflow protection (1MB), stream timeout (120s), cancellation via AbortController, health check

### Modifications needed:
1. Remove `vscode` dependency → pure Node.js
2. Switch from Node `http`/`https` to `undici` or native `fetch` (cleaner async generator pattern, inspired by Chrome extension's `extensions/chrome/shared/api.js` async generator)
3. Add full SSE event parsing from `chat_server.py`: `text`, `reasoning`, `session_id`, `usage`, `duration_ms`, `error` (VS Code client only handles `content` deltas)
4. Add `session_id`, `cwd`, `include_session`, `stream_tool_activity` to request body
5. Export as async generator: `async function* streamChat()` yielding typed events

### Replaces Python:
- `chat_server.py` (health check, agent fetch, SSE streaming)
- `chat_validation.py` (server connectivity checks)
- `cli_helpers.py` (`_api_get`, `_api_post`, `_server_url`)

### types.ts — Zod Schemas:
```typescript
// Agent, SSEChunk, ChatMessage, CompletionRequest, SessionInfo, PlanStep
// Must match Python models.py exactly for API compatibility
```

---

## Phase 3: State Management
**Complexity: M | ~3-4 days**

### Files:
```
terminal/src/state/
  store.ts                  # Zustand store (session, mode, agent, messages)
  SessionHistory.ts         # JSON file persistence (~/.code-agents/chat_history/)
  TokenTracker.ts           # Token usage tracking
  Scratchpad.ts             # /tmp/code-agents/<sid>/state.json
  AgentMemory.ts            # ~/.code-agents/agent_memory/<agent>.txt
  config.ts                 # Env loading, server URL resolution
```

### store.ts — Zustand Store:
```typescript
interface ChatStore {
  agent: string;
  sessionId: string | null;
  repoPath: string;
  mode: 'chat' | 'plan' | 'edit';
  messages: ChatMessage[];
  messageQueue: string[];
  isBusy: boolean;
  superpower: boolean;
  tokenUsage: { input: number; output: number; cached: number };
  // Actions
  cycleMode: () => void;
  setAgent: (name: string) => void;
  addMessage: (msg: ChatMessage) => void;
  enqueueMessage: (text: string) => void;
  dequeueMessage: () => string | undefined;
}
```

### SessionHistory.ts — Interoperable with Python:
- Same directory: `~/.code-agents/chat_history/`
- Same JSON schema as `chat_history.py`: `{id, agent, repo_path, title, created_at, updated_at, messages: [{role, content, timestamp}]}`
- Sessions created in Python can be resumed in TS and vice versa

### Replaces Python:
- `chat_state.py` → `store.ts`
- `chat_history.py` → `SessionHistory.ts`
- `token_tracker.py` → `TokenTracker.ts`
- `session_scratchpad.py` → `Scratchpad.ts`
- `env_loader.py` (client-side parts) → `config.ts`

---

## Phase 4: Chat REPL — Ink Components (THE MAIN WIN)
**Complexity: L | ~8-10 days**

### Files:
```
terminal/src/chat/
  ChatApp.tsx               # Root Ink app
  ChatInput.tsx             # Input box + mode indicator + Shift+Tab
  ChatOutput.tsx            # Scrolling output (markdown rendering)
  StreamingResponse.tsx     # SSE token display with spinner/timer
  ResponseBox.tsx           # Bordered response display
  CommandApproval.tsx       # Approve/reject extracted bash commands
  ActivityIndicator.tsx     # Blinking dot + timer while waiting
  ModeIndicator.tsx         # Chat/Plan/Edit badge
  WelcomeMessage.tsx        # Agent welcome box
  MarkdownRenderer.tsx      # Rich markdown via marked-terminal + shiki
  hooks/
    useChat.ts              # Main chat logic (send, stream, handle response)
    useStreaming.ts          # SSE streaming hook with abort
    useKeyBindings.ts       # Shift+Tab, Ctrl+C, Escape
    useMessageQueue.ts      # Queue input while agent busy
    useAgenticLoop.ts       # Command extraction → approval → execute → feed back
```

### Layout:
```
┌─────────────────────────────────────────┐
│  WelcomeMessage                         │
│  ─────────────────────────              │
│  ChatOutput (scrolling responses)       │
│    ResponseBox (bordered agent reply)   │
│    CommandApproval (approve bash cmds)  │
│  ─────────────────────────              │
│  [Chat] > prompt...          [3.2k tkn] │
│  ModeIndicator + ChatInput + TokenBadge │
└─────────────────────────────────────────┘
```

### Key Hook: useAgenticLoop.ts
State machine replacing `chat_repl.py`:
```
IDLE → USER_INPUT → STREAMING → RESPONSE_RECEIVED
  → COMMANDS_FOUND → AWAITING_APPROVAL → EXECUTING → FEEDING_BACK
  → STREAMING (loop, max CODE_AGENTS_MAX_LOOPS) → IDLE
```

### Command Extraction (portable regex from `chat_commands.py`):
```typescript
const CODE_BLOCK_RE = /```(?:bash|sh|shell|zsh|console)\s*\n(.*?)```/gs;
const SKILL_TAG_RE = /\[SKILL:(\w[\w-]*):(\w[\w-]*)\]/g;
const DELEGATE_TAG_RE = /\[DELEGATE:(\w[\w-]*)\]/g;
const REMEMBER_TAG_RE = /\[REMEMBER:(\w+)=(.*?)\]/g;
```

### Replaces Python:
- `chat.py` → `ChatApp.tsx` + `useChat.ts`
- `chat_input.py` → `ChatInput.tsx` + `useKeyBindings.ts`
- `chat_streaming.py` → `StreamingResponse.tsx` + `useStreaming.ts`
- `chat_response.py` → `ResponseBox.tsx`
- `chat_commands.py` → `useAgenticLoop.ts`
- `chat_repl.py` → `useAgenticLoop.ts`
- `chat_ui.py` → `chalk` + `marked-terminal` + `MarkdownRenderer.tsx`
- `chat_welcome.py` → `WelcomeMessage.tsx`

---

## Phase 5: Slash Command System
**Complexity: M | ~4-5 days**

### Files:
```
terminal/src/slash/
  registry.ts               # SlashEntry type + SLASH_REGISTRY map
  router.ts                 # Dispatch to handler by prefix
  handlers/
    nav.ts                  # /help, /quit, /restart, /open, /setup
    session.ts              # /session, /clear, /history, /resume, /export
    agents.ts               # /agent, /agents, /rules, /skills, /tokens, /memory
    ops.ts                  # /run, /bash, /btw, /repo, /superpower, /plan, /mcp
    config.ts               # /model, /backend
    analysis.ts             # /investigate, /blame, /generate-tests, /refactor, etc.
    tools.ts                # /pair, /coverage-boost, /mutate, /profile, etc.
```

### Pattern:
```typescript
interface SlashEntry {
  help: string;
  group: 'nav' | 'session' | 'agent' | 'ops' | 'config' | 'analysis' | 'tools';
  handler: (arg: string, store: ChatStore, api: ApiClient) => Promise<SlashResult>;
  aliases: string[];
}
type SlashResult = { action: 'continue' } | { action: 'quit' } | { action: 'send'; message: string };
```

### Replaces Python:
- `slash_registry.py` (49+ commands) → `registry.ts`
- `chat_slash.py` → `router.ts`
- 7 `chat_slash_*.py` handler modules → 7 handler files

---

## Phase 6: Interactive Features
**Complexity: L | ~6-8 days**

### Files:
```
terminal/src/chat/
  PlanMode.tsx              # Plan lifecycle display + approval questionnaire
  Questionnaire.tsx         # Multi-choice interactive forms
  CommandPanel.tsx          # Arrow-key option selector
  RequirementConfirmation.tsx  # Spec-before-execution gate
  DelegationHandler.ts      # Parse /<agent>:skill syntax

terminal/src/chat/hooks/
  usePlan.ts                # Plan state machine (DRAFT→PROPOSED→APPROVED→EXECUTING→COMPLETED)
  useQuestionnaire.ts       # Q&A flow
```

### Key Win: CommandPanel.tsx
Python's `command_panel.py` is 227 LOC of raw `tty.setraw()` + ANSI escape codes. Ink replaces it entirely:
```tsx
<SelectInput items={options} onSelect={onSelect} />
```

### Replaces Python:
- `command_panel.py` (227 LOC raw terminal) → `CommandPanel.tsx` (~30 LOC Ink)
- `questionnaire.py` → `Questionnaire.tsx`
- `requirement_confirm.py` (client parts) → `RequirementConfirmation.tsx`
- `plan_manager.py` (client parts) → `PlanMode.tsx` + `usePlan.ts`
- `chat_delegation.py` → `DelegationHandler.ts`

---

## Phase 7: CLI Commands (oclif)
**Complexity: L | ~8-10 days**

### Files:
```
terminal/src/commands/
  chat.ts                   # Launch Ink REPL (THE main command)
  start.ts                  # Start Python server (spawn subprocess)
  stop.ts                   # Stop server
  status.ts                 # Server health + config
  agents.ts                 # List agents
  init.ts                   # Delegates to Python `code-agents init` initially
  doctor.ts                 # Health diagnostics
  config.ts                 # Show/edit config
  # ... ~50 more thin wrapper commands (Tier 2-3)
```

### Priority Tiers:
- **Tier 1 (MVP)**: `chat`, `start`, `stop`, `status`, `agents`, `doctor`, `init`, `config`
- **Tier 2 (week 2)**: `diff`, `test`, `review`, `cost`, `logs`, `standup`
- **Tier 3 (week 3+)**: All remaining ~50 commands (thin API wrappers, can be semi-generated)

### Special Cases:
- `start` → spawns Python server via `child_process.spawn()` (same command as `cli_server.py`)
- `init` → delegates to Python initially, TS rewrite later
- `chat` → renders the full Ink ChatApp from Phase 4

### Replaces Python:
- All 77 `cli_*.py` files
- `cli.py` main dispatcher

---

## Phase 8: Rich TUI Components (the visual payoff)
**Complexity: M | ~4-5 days**

### Files:
```
terminal/src/tui/
  FullScreenApp.tsx         # Full-screen Ink app (replaces Textual ChatTUI)
  StatusBar.tsx             # Bottom bar: mode, agent, tokens, time
  ThinkingIndicator.tsx     # Animated spinner during streaming
  DiffView.tsx              # Side-by-side or inline diff with colors
  FileTree.tsx              # Collapsible project file tree
  ProgressDashboard.tsx     # Multi-step operation progress
  SyntaxHighlight.tsx       # Code blocks via shiki
  TokenBudgetBar.tsx        # Visual token usage gauge
```

### Why Ink > Textual here:
- No bridge/proxy layer needed (Textual's `bridge.py` + `proxy.py` eliminated)
- React composition model: `<DiffView>` inside `<ResponseBox>` inside `<ChatOutput>` — natural nesting
- Flexbox layout via `<Box>` — no CSS file needed
- Third-party Ink components ecosystem (ink-table, ink-gradient, ink-big-text)

### Replaces Python:
- `tui/app.py` → `FullScreenApp.tsx`
- `tui/bridge.py` → NOT NEEDED
- `tui/proxy.py` → NOT NEEDED
- `tui/css.py` → Inline Ink styles
- All TUI widgets → Ink components

---

## Phase 9: Testing Strategy
**Complexity: M | Ongoing, ~4-5 days initial**

### Files:
```
terminal/tests/
  client/ApiClient.test.ts, AgentService.test.ts
  state/store.test.ts, SessionHistory.test.ts, TokenTracker.test.ts
  chat/ChatApp.test.tsx, ChatInput.test.tsx, StreamingResponse.test.tsx
  slash/registry.test.ts, router.test.ts, handlers/*.test.ts
  cli/chat.test.ts, start.test.ts
  helpers/mock-server.ts        # In-process HTTP server for integration tests
  fixtures/sse-responses.ts     # Canned SSE payloads
```

### Approaches:
- **Unit**: Vitest for pure logic (SSE parsing, command extraction, state)
- **Component**: ink-testing-library for Ink components
- **Integration**: mock-server.ts returning canned SSE responses
- **CLI**: oclif built-in test helpers
- **Snapshot**: Rendered markdown, welcome messages, help text

---

## Phase 10: Install Integration
**Complexity: S | ~1 day**

### Dispatch Logic:
```bash
code-agents chat                          # Python REPL (default, unchanged)
code-agents chat --ts                     # TypeScript REPL
CODE_AGENTS_TERMINAL=ts code-agents chat  # Via env var
code-agents-ts chat                       # Direct TS entry
```

### install.sh addition (after Poetry step):
```bash
if command -v node &>/dev/null && [ "$(node -v | sed 's/v//' | cut -d. -f1)" -ge 18 ]; then
    step "5/6" "Building TypeScript terminal..."
    cd "$CODE_AGENTS_DIR/terminal" && npm ci && npm run build
fi
```

---

## Dependency Graph

```
Phase 1 (setup)
    ↓
Phase 2 (client) ──────────┐
    ↓                       │
Phase 3 (state)             │
    ↓                       │
Phase 4 (chat REPL) ◄──────┘
    ↓
    ├── Phase 5 (slash) ─────── can parallel
    ├── Phase 6 (interactive) ── can parallel
    ├── Phase 7 (CLI) ────────── can parallel
    └── Phase 8 (rich TUI) ──── can parallel
         ↓
Phase 9 (testing) ── runs alongside Phases 4-8
         ↓
Phase 10 (install) ── final
```

---

## Verification Plan

1. **Phase 2 gate**: `npm test` passes, `ApiClient` can stream from running Python server
2. **Phase 4 gate**: `code-agents-ts chat` launches, can send a message, see streaming response
3. **Phase 5 gate**: All 49+ slash commands work identically to Python REPL
4. **Phase 7 gate**: `code-agents-ts start` spawns Python server, `code-agents-ts status` shows health
5. **End-to-end**: Full session (start server → chat → slash commands → session resume → quit) works identically to Python client
6. **Interop test**: Create session in Python client, resume in TS client (and vice versa)

---

## Timeline

| Phase | Duration | Cumulative |
|-------|----------|------------|
| 1. Setup | 1-2 days | Week 1 |
| 2. Client | 3-4 days | Week 1 |
| 3. State | 3-4 days | Week 2 |
| 4. Chat REPL | 8-10 days | Week 3-4 |
| 5-8 (parallel) | 10-14 days | Week 4-6 |
| 9. Testing | ongoing | Week 3-6 |
| 10. Install | 1 day | Week 6 |
| **MVP (Phases 1-4)** | **~3 weeks** | |
| **Full** | **~6-8 weeks** | |
