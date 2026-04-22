# Code Agents — VS Code Extension

## Overview

VS Code extension that provides a full-featured chat sidebar connected to the code-agents server. Access all 13 specialist AI agents directly from your editor with streaming responses, inline diffs, plan mode, and 50+ slash commands.

## Features

- **Chat Sidebar** — Interactive chat with streaming SSE responses, markdown rendering, syntax-highlighted code blocks with Copy/Apply buttons
- **13 Agents** — Agent picker with categorized dropdown (Orchestration, Code, Testing, DevOps, Data & Ops)
- **Right-Click Actions** — Review Code, Write Tests, Explain Code, Fix Bug, Security Scan, Build & Deploy
- **Plan Mode** — Step-by-step execution plans with progress tracking, approve/reject workflow
- **50+ Slash Commands** — Full access to code-agents features via `/command` palette with keyboard navigation
- **@-Mentions** — Reference files and agents inline with autocomplete
- **Inline Diffs** — Accept/Reject code changes with colored diff view
- **Theme Support** — Auto (inherits VS Code theme), Dark, Light, High Contrast — all WCAG AA compliant
- **Agent Accent Colors** — Each agent gets a unique color for easy identification
- **Session History** — Search, resume, and export past conversations
- **Token Tracking** — Session and daily token usage display
- **Server Status** — Status bar indicator with auto-reconnect
- **Debug Logging** — Full structured logging via "Code Agents" output channel

---

## Prerequisites

Before setting up the extension, ensure you have:

1. **Node.js 18+** — [nodejs.org](https://nodejs.org/)
2. **npm 9+** — comes with Node.js
3. **VS Code 1.85+** — [code.visualstudio.com](https://code.visualstudio.com/)
4. **Code Agents server** — running at `http://localhost:8000` (see main project README)

```bash
# Verify prerequisites
node --version    # v18.x or higher
npm --version     # 9.x or higher
code --version    # 1.85.x or higher
```

---

## Setup — Development Mode

### Step 1: Install dependencies

```bash
cd extensions/vscode

# Install extension dependencies
npm install

# Install webview UI dependencies
cd webview-ui && npm install && cd ..
```

### Step 2: Build the webview UI

```bash
npm run build:webview
```

This compiles the shared chat UI (TypeScript + CSS) into `webview-ui/build/`.

### Step 3: Compile the extension

```bash
npm run compile
```

This bundles `src/extension.ts` into `dist/extension.js` via esbuild.

### Step 4: Launch in VS Code

1. Open the `extensions/vscode/` folder in VS Code
2. Press **F5** (or Run > Start Debugging)
3. A new VS Code window opens — the **Extension Development Host**
4. Click the Code Agents icon in the Activity Bar (left sidebar)
5. The chat panel opens — start chatting with agents

### Step 5: Start the code-agents server

In a separate terminal:

```bash
cd /path/to/your-project
code-agents start
```

The status dot in the extension toolbar turns green when connected.

---

## Setup — Install from .vsix Package

### Step 1: Build the package

```bash
cd extensions/vscode
npm run package    # Builds webview + extension → creates .vsix
```

### Step 2: Install the .vsix

**Option A: Command line**
```bash
code --install-extension code-agents-1.0.0.vsix
```

**Option B: VS Code UI**
1. Open VS Code
2. Go to Extensions panel (Cmd+Shift+X)
3. Click `...` menu (top-right) → **Install from VSIX...**
4. Select the `.vsix` file
5. Reload VS Code when prompted

### Step 3: Configure

Open Settings (Cmd+,) and search for "Code Agents":

| Setting | Default | Description |
|---------|---------|-------------|
| `codeAgents.serverUrl` | `http://localhost:8000` | Code Agents server URL |
| `codeAgents.defaultAgent` | `auto-pilot` | Default agent for new chats |
| `codeAgents.theme` | `auto` | Chat theme (auto/dark/light/high-contrast) |
| `codeAgents.autoStartServer` | `false` | Auto-start server on activation |
| `codeAgents.autoRun` | `true` | Auto-execute safe commands |
| `codeAgents.requireConfirm` | `true` | Require confirmation before execution |
| `codeAgents.contextWindow` | `5` | Conversation pairs to keep in context |
| `codeAgents.statusPollingInterval` | `15000` | Health check interval (ms) |

---

## Publish to VS Code Marketplace

### Step 1: Create a publisher account

1. Go to [marketplace.visualstudio.com/manage](https://marketplace.visualstudio.com/manage)
2. Sign in with your Microsoft account (or create one)
3. Click **Create Publisher**
4. Fill in publisher ID (e.g., `acme`) and display name
5. Verify your email

### Step 2: Get a Personal Access Token (PAT)

1. Go to [dev.azure.com](https://dev.azure.com/)
2. Sign in → User Settings → **Personal Access Tokens**
3. Click **New Token**
4. Set:
   - Name: `vscode-marketplace`
   - Organization: **All accessible organizations**
   - Scopes: **Custom defined** → check **Marketplace > Manage**
   - Expiration: 1 year
5. Click **Create** → copy the token (you won't see it again)

### Step 3: Login with vsce

```bash
# Install vsce (VS Code Extension CLI)
npm install -g @vscode/vsce

# Login with your publisher ID and PAT
vsce login acme
# Paste your Personal Access Token when prompted
```

### Step 4: Update package.json

Edit `extensions/vscode/package.json`:

```json
{
  "publisher": "code-agents",
  "repository": {
    "type": "git",
    "url": "https://github.com/code-agents-org/code-agents"
  },
  "icon": "assets/icon.png"
}
```

> Note: The marketplace requires a 128x128 PNG icon at `assets/icon.png`.

### Step 5: Package and publish

```bash
# Package (creates .vsix)
vsce package

# Publish to marketplace
vsce publish

# Or publish a specific version
vsce publish 1.0.0
```

### Step 6: Verify

Your extension will appear at:
```
https://marketplace.visualstudio.com/items?itemName=acme.code-agents
```

Users can now install via:
```bash
code --install-extension acme.code-agents
```

Or search "Code Agents" in the VS Code Extensions panel.

### Updating the extension

```bash
# Bump version and publish
vsce publish patch   # 1.0.0 → 1.0.1
vsce publish minor   # 1.0.0 → 1.1.0
vsce publish major   # 1.0.0 → 2.0.0
```

---

## Commands

| Command | Shortcut | Description |
|---------|----------|-------------|
| Open Chat | `Cmd+'` | Open chat sidebar |
| Add to Chat | `Cmd+Shift+'` | Send selection to chat |
| New Chat | `Cmd+Shift+N` | Start new conversation |
| Switch Agent | — | QuickPick agent selector |
| Review Code | Right-click | → code-reviewer |
| Write Tests | Right-click | → code-tester |
| Explain Code | Right-click | → code-reasoning |
| Fix Bug | Right-click | → code-writer |
| Security Scan | Right-click | → security |
| Build & Deploy | Right-click | → jenkins-cicd |

---

## Testing

```bash
# Run all tests (webview + security)
npm test

# Run with verbose output
cd webview-ui && npm test

# Full verification (lint + test + build)
npm run verify
```

Test suites:
- `state.test.ts` — Reactive store CRUD, subscriptions, streaming state
- `renderer.test.ts` — Markdown rendering, XSS prevention
- `security.test.ts` — Path traversal, URL sanitization, state injection

---

## Debug Logging

The extension logs to the **"Code Agents"** output channel in VS Code:

1. Open Output panel (Cmd+Shift+U)
2. Select **"Code Agents"** from the dropdown
3. View structured logs:
   ```
   [2026-04-08T14:30:00.000Z] [INFO] [Extension] Activating Code Agents
   [2026-04-08T14:30:01.000Z] [INFO] [ServerMonitor] Server connected
   [2026-04-08T14:30:01.500Z] [DEBUG] [AgentService] Loaded 13 agents
   [2026-04-08T14:30:05.000Z] [INFO] [ChatView] Sending message {"agent":"auto-pilot"}
   [2026-04-08T14:30:05.100Z] [INFO] [ApiClient] Starting SSE stream
   ```

For webview debugging:
1. Open Command Palette (Cmd+Shift+P)
2. Run **"Developer: Open Webview Developer Tools"**
3. Check the Console tab for colored log output

---

## Architecture

```
src/
├── extension.ts              # Activation, command registration
├── providers/
│   └── ChatViewProvider.ts   # WebviewViewProvider sidebar
├── services/
│   ├── ApiClient.ts          # HTTP + SSE streaming
│   ├── AgentService.ts       # Agent list & switching
│   ├── ServerMonitor.ts      # Health polling + status bar
│   └── Logger.ts             # Structured output channel logger
├── commands/
│   ├── codeActions.ts        # Right-click menu handlers
│   └── chatCommands.ts       # Open, new, switch commands
├── protocol.ts               # Typed message interfaces
└── utils.ts                  # CSP nonce, URI helpers

webview-ui/                   # Shared UI (also used by IntelliJ)
├── src/
│   ├── app.ts                # Root component + message handler
│   ├── state.ts              # Reactive state store
│   ├── api.ts                # IDE bridge abstraction
│   ├── logger.ts             # Webview console logger
│   ├── views/                # ChatView, SettingsView, HistoryView
│   ├── components/           # Toolbar, MessageBubble, ChatInput, etc.
│   ├── markdown/             # Custom markdown renderer
│   ├── styles/               # Theme, base, chat, input, overlays
│   └── __tests__/            # Vitest test suite
├── vitest.config.ts
└── build/                    # Vite output
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Chat panel is blank | Run `npm run build:webview` first, then reload VS Code |
| "Server disconnected" | Start the server: `code-agents start` in your project |
| No agents in dropdown | Server must be running; check URL in settings |
| Right-click menu missing | Select text in the editor first (some actions require selection) |
| Extension not loading | Check VS Code version (1.85+); check Output > "Code Agents" for errors |
| Theme looks wrong | Change `codeAgents.theme` setting or set to `auto` |
