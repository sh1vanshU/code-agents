# Code Agents — IntelliJ Plugin

## Overview

IntelliJ Platform plugin that provides a chat tool window connected to the code-agents server. Works in **all JetBrains IDEs**: IntelliJ IDEA, PyCharm, WebStorm, Android Studio, GoLand, PhpStorm, RubyMine, CLion, Rider, and DataGrip. Uses JCEF (embedded Chromium) to render the same UI as the VS Code extension.

## Features

- **Chat Tool Window** — Dockable right-side panel with streaming responses, markdown, code blocks
- **13 Agents** — Full agent picker with categorized groups
- **Right-Click Actions** — Review Code, Write Tests, Explain Code, Fix Bug, Security Scan, Build & Deploy, Add to Chat
- **Plan Mode** — Step-by-step plans with progress tracking
- **50+ Slash Commands** — Full code-agents command palette with keyboard navigation
- **Theme Support** — Auto, Dark, Light, High Contrast
- **Status Bar Widget** — Server connection status indicator (async, non-blocking)
- **Settings Panel** — Settings > Tools > Code Agents
- **Cross-IDE** — Works in all JetBrains IDEs (platform-only dependency)
- **Debug Logging** — Full structured logging via IntelliJ diagnostic logger

---

## Prerequisites

Before setting up the plugin, ensure you have:

1. **Java 17+** (JDK) — [adoptium.net](https://adoptium.net/)
2. **Node.js 18+** — needed to build the shared webview UI
3. **IntelliJ Platform IDE 2024.1+** — any JetBrains IDE
4. **Code Agents server** — running at `http://localhost:8000`

```bash
# Verify prerequisites
java --version    # 17.x or higher
node --version    # v18.x or higher
```

---

## Setup — Development Mode

### Step 1: Build the shared webview UI

The chat UI is shared with the VS Code extension. Build it first:

```bash
cd extensions/vscode/webview-ui
npm install
npm run build
```

### Step 2: Copy webview to plugin resources

```bash
cd extensions/intellij
mkdir -p src/main/resources/webview/assets
cp ../vscode/webview-ui/build/index.html src/main/resources/webview/
cp -r ../vscode/webview-ui/build/assets/* src/main/resources/webview/assets/
```

Or use the Makefile shortcut:
```bash
cd extensions
make intellij-webview
```

### Step 3: Initialize Gradle wrapper

```bash
cd extensions/intellij
gradle wrapper --gradle-version=8.13
```

### Step 4: Build the plugin

```bash
./gradlew buildPlugin
```

This downloads the IntelliJ Platform SDK, compiles Kotlin, and produces a plugin ZIP.

### Step 5: Launch sandboxed IDE

```bash
./gradlew runIde
```

This opens a sandboxed instance of IntelliJ IDEA with the plugin pre-installed. The Code Agents tool window appears on the right sidebar.

### Step 6: Start the code-agents server

In a separate terminal:
```bash
cd /path/to/your-project
code-agents start
```

---

## Setup — Install from Plugin ZIP

### Step 1: Build the plugin package

```bash
cd extensions
make intellij    # Or manually: build webview → copy → gradlew buildPlugin
```

The plugin ZIP is at `extensions/intellij/build/distributions/code-agents-intellij-1.0.0.zip`.

### Step 2: Install in your JetBrains IDE

1. Open your IDE (IntelliJ, PyCharm, WebStorm, etc.)
2. Go to **Settings** (Cmd+, on macOS / Ctrl+Alt+S on Linux/Windows)
3. Navigate to **Plugins**
4. Click the gear icon (top-right) → **Install Plugin from Disk...**
5. Select the `.zip` file from `build/distributions/`
6. Click **OK** → **Restart IDE** when prompted

### Step 3: Configure

After restart:

1. Go to **Settings > Tools > Code Agents**
2. Configure:

| Setting | Default | Description |
|---------|---------|-------------|
| Server URL | `http://localhost:8000` | Code Agents server URL |
| Default Agent | `auto-pilot` | Default agent for new chats |
| Theme | `auto` | Chat panel theme |
| Auto-start server | `false` | Start server when IDE opens |
| Auto-run commands | `true` | Auto-execute safe commands |
| Require confirmation | `true` | Ask before executing |
| Context window | `5` | Conversation pairs to keep |
| Polling interval | `15000` | Health check interval (ms) |

---

## Publish to JetBrains Marketplace

### Step 1: Create a JetBrains Account

1. Go to [plugins.jetbrains.com](https://plugins.jetbrains.com/)
2. Click **Sign In** → create account or use existing JetBrains account
3. Go to your profile → **Upload Plugin** (this registers you as a plugin author)

### Step 2: Get a Marketplace Token

1. Go to [plugins.jetbrains.com/author/me/tokens](https://plugins.jetbrains.com/author/me/tokens)
2. Click **Generate Token**
3. Set scope: **Plugin Upload**
4. Copy the token (save it — you won't see it again)

### Step 3: Update plugin metadata

Edit `extensions/intellij/build.gradle.kts`:

```kotlin
intellijPlatform {
    pluginConfiguration {
        name = "Code Agents"
        version = "1.0.0"
        description = """
            AI-powered code agent platform with 13 specialist agents
            for CI/CD, code review, testing, security, and DevOps.
        """.trimIndent()

        changeNotes = """
            <ul>
                <li>Initial release</li>
                <li>13 specialist agents</li>
                <li>Chat panel with streaming responses</li>
                <li>Editor context menu actions</li>
            </ul>
        """.trimIndent()

        ideaVersion {
            sinceBuild = "241"    // 2024.1+
            untilBuild = "261.*"  // up to 2026.1.x
        }
    }
}
```

Edit `extensions/intellij/src/main/resources/META-INF/plugin.xml` — update vendor info:

```xml
<vendor email="your-email@company.com" url="https://your-website.com">
    Your Company Name
</vendor>
```

### Step 4: Build and publish

**Option A: Publish via Gradle (automated)**

Add to `gradle.properties`:
```properties
intellijPublishToken=your-marketplace-token-here
```

Add to `build.gradle.kts`:
```kotlin
intellijPlatform {
    publishing {
        token = providers.gradleProperty("intellijPublishToken")
    }
}
```

Then publish:
```bash
./gradlew publishPlugin
```

**Option B: Upload via web UI (manual)**

1. Build the plugin: `./gradlew buildPlugin`
2. Go to [plugins.jetbrains.com/author/me](https://plugins.jetbrains.com/author/me)
3. Click **Upload Plugin**
4. Select `build/distributions/code-agents-intellij-1.0.0.zip`
5. Fill in:
   - Plugin name: **Code Agents**
   - Category: **AI**, **Code tools**
   - License: MIT (or your choice)
   - Tags: `ai`, `agents`, `cicd`, `code-review`, `testing`, `devops`
6. Click **Upload**

### Step 5: Wait for approval

JetBrains reviews plugins manually. Typical approval time: **1-3 business days**.

You'll receive an email when approved. The plugin will then be available at:
```
https://plugins.jetbrains.com/plugin/XXXXX-code-agents
```

### Step 6: Users install via Marketplace

After approval, users can install directly from their IDE:

1. **Settings > Plugins > Marketplace**
2. Search **"Code Agents"**
3. Click **Install** → Restart IDE

### Updating the plugin

```bash
# Bump version in gradle.properties
# pluginVersion = 1.0.1

# Build and publish
./gradlew publishPlugin
```

---

## Editor Context Menu

Right-click in any editor to see:

```
Code Agents  >  Review Code        → code-reviewer
                Write Tests        → code-tester
                Explain Code       → code-reasoning
                Fix Bug            → code-writer
                Add to Chat        → current agent
                ─────────────
                Security Scan      → security
                Build & Deploy     → jenkins-cicd
```

---

## CLI Commands for Plugin Management

These commands help manage the plugin during development:

```bash
# Build
./gradlew buildPlugin              # Compile + package ZIP
./gradlew buildPlugin --info       # Verbose build output

# Run
./gradlew runIde                   # Launch sandboxed IDE
./gradlew runIde --debug-jvm       # Launch with remote debugger (port 5005)

# Test
./gradlew test                     # Run unit tests
./gradlew test --info              # Verbose test output

# Verify
./gradlew verifyPlugin             # Validate plugin descriptor
./gradlew verifyPluginStructure    # Check plugin ZIP structure

# Publish
./gradlew publishPlugin            # Upload to Marketplace

# Clean
./gradlew clean                    # Remove build artifacts
```

---

## Testing

```bash
# Run unit tests
./gradlew test

# Run with verbose output
./gradlew test --info

# Test files:
# src/test/kotlin/com/codeagents/plugin/PluginSettingsTest.kt
#   - Default settings values
#   - Settings mutation
#   - Path traversal validation
```

---

## Debug Logging

The plugin logs to IntelliJ's diagnostic log:

1. Go to **Help > Show Log in Finder** (macOS) / **Show Log in Explorer** (Windows)
2. Open `idea.log`
3. Search for `CodeAgents` or `JcefBridge`:
   ```
   INFO - c.c.plugin.ui.JcefBridge - Installing JCEF bridge for project: my-project
   DEBUG - c.c.plugin.ui.JcefBridge - Webview message: sendMessage
   INFO - c.c.plugin.services.ServerMonitor - Server connected
   ```

To enable DEBUG level logging:
1. Go to **Help > Diagnostic Tools > Debug Log Settings**
2. Add: `com.codeagents.plugin`
3. Click OK — debug logs now appear in `idea.log`

---

## Architecture

```
src/main/kotlin/com/codeagents/plugin/
├── services/
│   ├── PluginSettings.kt           # PersistentStateComponent (app-level)
│   └── ServerMonitor.kt            # Async health polling with Alarm
├── ui/
│   ├── ChatToolWindowFactory.kt    # ToolWindowFactory + JBCefBrowser
│   ├── JcefBridge.kt               # JS↔Kotlin bridge (Disposable)
│   └── StatusBarWidgetFactory.kt   # Async connection status widget
├── actions/
│   ├── BaseAgentAction.kt          # Abstract: EDT-safe editor context
│   ├── ReviewCodeAction.kt         # → code-reviewer
│   ├── WriteTestsAction.kt         # → code-tester
│   ├── ExplainCodeAction.kt        # → code-reasoning
│   ├── FixBugAction.kt             # → code-writer
│   ├── SecurityScanAction.kt       # → security
│   ├── BuildDeployAction.kt        # → jenkins-cicd
│   └── AddToChatAction.kt          # → current agent
└── settings/
    └── SettingsConfigurable.kt     # Settings > Tools > Code Agents

src/main/resources/
├── META-INF/
│   ├── plugin.xml                  # Plugin descriptor
│   └── pluginIcon.svg              # 13x13 tool window icon
└── webview/                        # Built from vscode/webview-ui/
    ├── index.html
    ├── assets/                     # JS + CSS from Vite build
    └── bridge.js                   # JCEF adapter (IDE detection)
```

---

## JCEF Bridge Architecture

```
Editor Action (Kotlin, EDT)
    → BaseAgentAction.actionPerformed()
    → JcefBridge.injectContext(agent, message, filePath)
    → browser.executeJavaScript("window._ideCallback({...})")
    → Webview receives message, updates UI
    → User types, webview calls window.IDE.postMessage()
    → JBCefJSQuery handler in Kotlin receives message
    → JcefBridge.handleWebviewMessage() dispatches action

Security:
    → URL-encoded JSON via postMessage (no JS injection)
    → Path traversal blocked (canonicalized, validated against project root)
    → Settings persisted via PersistentStateComponent (not localStorage)
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Chat panel shows "Webview files not found" | Build and copy webview: `make intellij-webview` |
| Tool window not appearing | Check Settings > Plugins, ensure "Code Agents" is enabled |
| "JCEF not supported" message | Use a JetBrains IDE with JCEF bundled (most desktop IDEs have it) |
| Server disconnected | Start the server: `code-agents start` in your project |
| Plugin won't build | Check Java 17+ (`java --version`) and run `gradle wrapper` |
| Right-click menu missing | Ensure you right-clicked inside a code editor, not a file tree |
| Logs not showing | Help > Diagnostic Tools > Debug Log Settings → add `com.codeagents.plugin` |

---

## Requirements

- IntelliJ Platform 2024.1+ (any JetBrains IDE)
- Kotlin 1.9+
- Gradle 8.13+
- Java 17+
- Node.js 18+ (for building webview)
