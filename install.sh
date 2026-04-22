#!/usr/bin/env bash
# ============================================================================
# Code Agents — One-Command Installer
# ============================================================================
# Installs code-agents centrally at ~/.code-agents
# Then use 'code-agents init' in any repo to configure and run.
#
# Usage (org Bitbucket — clone directly):
#   git clone git@github.com:code-agents-org/code-agents.git ~/.code-agents && bash ~/.code-agents/install.sh
#
# Or if you have the script locally:
#   bash install.sh
#
# Best-effort: individual steps may fail (network, optional tools); we keep going
# and print warnings so later steps (wrapper, completions, hints) still run.
# ============================================================================

set +eu -o pipefail

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
if [ -t 1 ]; then
    BOLD='\033[1m'
    GREEN='\033[32m'
    YELLOW='\033[33m'
    RED='\033[31m'
    CYAN='\033[36m'
    DIM='\033[2m'
    RESET='\033[0m'
else
    BOLD='' GREEN='' YELLOW='' RED='' CYAN='' DIM='' RESET=''
fi

info()    { echo -e "${GREEN}  ✓${RESET} $*"; }
warn()    { echo -e "${YELLOW}  !${RESET} $*"; }
error()   { echo -e "${RED}  ✗${RESET} $*"; }
step()    { echo -e "\n${BOLD}${CYAN}[$1]${RESET} ${BOLD}$2${RESET}"; }
dim()     { echo -e "${DIM}    $*${RESET}"; }
ask()     { echo -en "  $1 "; }
divider() { echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"; }

CODE_AGENTS_DIR="$HOME/.code-agents"
REPO_URL_SSH="git@github.com:code-agents-org/code-agents.git"
REPO_URL_HTTPS="https://github.com/code-agents-org/code-agents.git"

# Use SSH if key exists, otherwise HTTPS
if ssh -T git@bitbucket.org 2>&1 | grep -q "authenticated"; then
    REPO_URL="$REPO_URL_SSH"
    info "Using SSH authentication"
else
    REPO_URL="$REPO_URL_HTTPS"
    info "Using HTTPS authentication (you may be prompted for credentials)"
fi

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
echo ""
echo -e "${BOLD}${CYAN}  ╔══════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${CYAN}  ║     Code Agents — One-Command Installer      ║${RESET}"
echo -e "${BOLD}${CYAN}  ╚══════════════════════════════════════════════╝${RESET}"
echo ""

# ============================================================================
# STEP 1: Check Python
# ============================================================================
step "1/7" "Checking Python..."

PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    error "Python 3.10+ is required but not found."
    echo "  Install: https://www.python.org/downloads/"
    echo "  macOS:   brew install python@3.12"
    echo "  Ubuntu:  sudo apt install python3.12"
    warn "Continuing — install Python, then re-run this script or use poetry from a 3.10+ interpreter."
fi

if [ -n "$PYTHON_CMD" ]; then
    info "$("$PYTHON_CMD" --version 2>&1)"
fi

# ============================================================================
# STEP 2: Check/Install Poetry
# ============================================================================
step "2/7" "Checking Poetry..."

if command -v poetry &>/dev/null; then
    info "$(poetry --version 2>&1)"
else
    warn "Poetry not found. Installing..."
    # Try pipx first (works on macOS, Linux, WSL)
    if command -v pipx &>/dev/null; then
        dim "Installing via pipx..."
        pipx install poetry 2>&1 | tail -3
        pipx ensurepath 2>&1 | tail -1
        export PATH="$HOME/.local/bin:$PATH"
    elif command -v brew &>/dev/null; then
        # macOS / Homebrew Linux: install pipx via brew, then poetry
        dim "Installing pipx via brew, then poetry..."
        brew install pipx 2>&1 | tail -3
        pipx ensurepath 2>&1 | tail -1
        pipx install poetry 2>&1 | tail -3
        export PATH="$HOME/.local/bin:$PATH"
    elif command -v pip3 &>/dev/null || command -v pip &>/dev/null; then
        # Linux without brew: install pipx via pip, then poetry
        _pip_cmd="pip3"; command -v pip3 &>/dev/null || _pip_cmd="pip"
        dim "Installing pipx via $_pip_cmd, then poetry..."
        "$_pip_cmd" install --user pipx 2>&1 | tail -3
        "$PYTHON_CMD" -m pipx ensurepath 2>&1 | tail -1
        export PATH="$HOME/.local/bin:$PATH"
        pipx install poetry 2>&1 | tail -3
    else
        # Last resort: official installer script
        dim "Installing via official installer..."
        curl -sSL https://install.python-poetry.org | "$PYTHON_CMD" - 2>&1 | tail -3
        export PATH="$HOME/.local/bin:$PATH"
    fi
    if command -v poetry &>/dev/null; then
        info "Poetry installed: $(poetry --version)"
    else
        error "Poetry installation failed."
        echo "  Install manually:"
        echo "    macOS:  brew install pipx && pipx install poetry"
        echo "    Linux:  pip3 install --user pipx && pipx install poetry"
        echo "    Docs:   https://python-poetry.org/docs/"
        warn "Continuing without Poetry — install it, then: cd ~/.code-agents && poetry install"
    fi
fi

# ============================================================================
# STEP 3: Clone / Update code-agents
# ============================================================================
step "3/7" "Installing Code Agents to ~/.code-agents..."

if [ -f "$CODE_AGENTS_DIR/pyproject.toml" ]; then
    info "Already installed at: $CODE_AGENTS_DIR"
    cd "$CODE_AGENTS_DIR"

    # Check current version before pull
    OLD_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

    dim "Pulling latest from Bitbucket..."
    PULL_OUTPUT=$(git pull 2>&1)
    PULL_STATUS=$?

    if [ $PULL_STATUS -ne 0 ]; then
        warn "Could not pull latest (offline or merge conflict?)"
        dim "    $PULL_OUTPUT"
    elif echo "$PULL_OUTPUT" | grep -q "Already up to date"; then
        info "Already up to date (${OLD_COMMIT})"
    else
        NEW_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
        info "Updated: ${OLD_COMMIT} → ${NEW_COMMIT}"
        echo ""
        dim "  Files updated:"

        # Show which files changed
        CHANGED=$(git diff --name-only "${OLD_COMMIT}..${NEW_COMMIT}" 2>/dev/null)
        if [ -n "$CHANGED" ]; then
            CHANGED_COUNT=$(echo "$CHANGED" | wc -l | tr -d ' ')
            echo "$CHANGED" | while read -r file; do
                dim "    • $file"
            done
            echo ""
            info "${CHANGED_COUNT} file(s) updated"
        fi

        # Show commit messages
        COMMITS=$(git log --oneline "${OLD_COMMIT}..${NEW_COMMIT}" 2>/dev/null)
        if [ -n "$COMMITS" ]; then
            echo ""
            dim "  Changes:"
            echo "$COMMITS" | while read -r line; do
                dim "    $line"
            done
        fi
    fi
else
    dim "Cloning from Bitbucket..."
    if git clone "$REPO_URL" "$CODE_AGENTS_DIR" 2>&1 | tail -2; then
        info "Installed to: $CODE_AGENTS_DIR"
        if cd "$CODE_AGENTS_DIR"; then
            FILE_COUNT=$(git ls-files | wc -l | tr -d ' ')
            COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
            info "Cloned ${FILE_COUNT} files (commit: ${COMMIT})"
        else
            warn "Could not cd to $CODE_AGENTS_DIR after clone"
        fi
    else
        warn "git clone failed — check VPN/network and Bitbucket access (SSH key or HTTPS credentials)."
        warn "You can clone manually, then re-run: git clone <url> $CODE_AGENTS_DIR && bash $CODE_AGENTS_DIR/install.sh"
    fi
fi

# ============================================================================
# STEP 4: Install dependencies
# ============================================================================
step "4/7" "Installing dependencies..."

cd "$CODE_AGENTS_DIR" 2>/dev/null || warn "Cannot cd to $CODE_AGENTS_DIR — some steps may fail until the repo exists."
dim "poetry install (includes claude-agent-sdk)..."
if ! poetry install --quiet 2>&1 | tail -5; then
    dim "Lock file may be stale — regenerating..."
    poetry lock 2>&1 | tail -3 || true
    if poetry install --quiet 2>&1 | tail -5; then
        info "Core dependencies installed (after re-lock)"
    else
        warn "poetry install failed — you may need to run: cd ~/.code-agents && poetry install"
        dim "Continuing with remaining steps..."
    fi
else
    info "Core dependencies installed (includes claude-agent-sdk)"
fi

# cursor-agent-sdk (optional — for Cursor backend, requires git clone)
if poetry run python -c "import cursor_agent_sdk" 2>/dev/null; then
    info "cursor-agent-sdk ready"
else
    dim "Installing cursor-agent-sdk (Cursor backend)..."
    poetry install --with cursor --quiet 2>&1 | tail -3 &
    _pip_pid=$!
    _waited=0
    while kill -0 "$_pip_pid" 2>/dev/null; do
        sleep 2; _waited=$((_waited + 2))
        if [ "$_waited" -ge 60 ]; then
            kill "$_pip_pid" 2>/dev/null; wait "$_pip_pid" 2>/dev/null
            warn "cursor-agent-sdk install timed out (optional — Cursor backend won't be available)"
            dim "Retry later: cd ~/.code-agents && poetry install --with cursor"
            break
        fi
    done
    if [ "$_waited" -lt 60 ] && wait "$_pip_pid"; then
        info "cursor-agent-sdk ready"
    elif [ "$_waited" -lt 60 ]; then
        warn "cursor-agent-sdk install failed (optional — Cursor backend won't be available)"
        dim "Retry later: cd ~/.code-agents && poetry install --with cursor"
    fi
fi

# Claude CLI (optional — for claude-cli backend)
if command -v claude &>/dev/null; then
    info "Claude CLI ready ($(claude --version 2>/dev/null || echo 'installed'))"
else
    dim "Installing Claude CLI (claude-cli backend)..."
    if command -v npm &>/dev/null; then
        if npm install -g @anthropic-ai/claude-code 2>&1 | tail -3; then
            info "Claude CLI installed"
            dim "Run 'claude' to login and authenticate"
        else
            warn "Claude CLI install failed (optional — claude-cli backend won't be available)"
            dim "Install manually: npm install -g @anthropic-ai/claude-code"
        fi
    elif command -v brew &>/dev/null; then
        # macOS without npm: install node via brew first
        dim "Installing Node.js via brew..."
        brew install node 2>&1 | tail -3
        if command -v npm &>/dev/null; then
            npm install -g @anthropic-ai/claude-code 2>&1 | tail -3
            if command -v claude &>/dev/null; then
                info "Claude CLI installed"
                dim "Run 'claude' to login and authenticate"
            else
                warn "Claude CLI install failed (optional — claude-cli backend won't be available)"
                dim "Install manually: npm install -g @anthropic-ai/claude-code"
            fi
        else
            warn "npm still not found after node install"
            dim "Install manually: npm install -g @anthropic-ai/claude-code"
        fi
    else
        warn "Node.js/npm not found — skipping Claude CLI install"
        dim "macOS: brew install node && npm install -g @anthropic-ai/claude-code"
    fi
fi

# ============================================================================
# IDE Extensions — build + auto-install into VS Code, IntelliJ, Chrome
# ============================================================================

# --- Node.js / npm (needed for VS Code extension) ---
if ! command -v npm &>/dev/null; then
    dim "npm not found — attempting to install Node.js..."
    if command -v brew &>/dev/null; then
        brew install node 2>&1 | tail -3
        if command -v npm &>/dev/null; then
            info "Node.js installed via Homebrew"
        else
            warn "Node.js install failed"
            dim "Install manually: https://nodejs.org/"
        fi
    elif [ "$(uname)" = "Linux" ] && command -v apt-get &>/dev/null; then
        sudo apt-get install -y nodejs npm 2>&1 | tail -3
        if command -v npm &>/dev/null; then
            info "Node.js installed via apt"
        else
            warn "Node.js install failed"
        fi
    else
        dim "Install Node.js from: https://nodejs.org/"
    fi
fi

# --- VS Code Extension: build (shared with CLI: code_agents.tools.vscode_extension) ---
_ext_dir="$CODE_AGENTS_DIR/extensions/vscode"
_vscode_built=false
if command -v npm &>/dev/null && command -v poetry &>/dev/null; then
    if [ -f "$_ext_dir/package.json" ]; then
        dim "Building VS Code extension..."
        (
            cd "$CODE_AGENTS_DIR" || { warn "Could not cd to $CODE_AGENTS_DIR"; exit 1; }
            export CODE_AGENTS_DIR
            poetry run python -m code_agents.tools.vscode_extension build
        ) && { info "VS Code extension built"; _vscode_built=true; } \
          || warn "VS Code extension build failed (run 'code-agents plugin build vscode' later)"
    fi
else
    if ! command -v npm &>/dev/null; then
        dim "Skipping VS Code extension build (npm not found)"
    else
        dim "Skipping VS Code extension build (poetry not found — run from repo: poetry install)"
    fi
fi

# --- VS Code Extension: package (.vsix) + auto-install (same as: plugin package vscode → plugin install vscode) ---
if [ "$_vscode_built" = true ]; then
    if command -v code &>/dev/null && code --list-extensions 2>/dev/null | grep -q "code-agents" 2>/dev/null; then
        info "VS Code extension already installed"
    else
        _vsix=$(ls -t "$_ext_dir"/*.vsix 2>/dev/null | head -1)
        if [ -z "$_vsix" ]; then
            dim "Packaging VS Code extension (.vsix) with @vscode/vsce..."
            if (
                cd "$CODE_AGENTS_DIR" || { warn "Could not cd to $CODE_AGENTS_DIR"; exit 1; }
                export CODE_AGENTS_DIR
                poetry run python -m code_agents.tools.vscode_extension package
            ); then
                _vsix=$(ls -t "$_ext_dir"/*.vsix 2>/dev/null | head -1)
                if [ -n "$_vsix" ]; then
                    info "VS Code extension packaged: $(basename "$_vsix")"
                fi
            else
                warn "VS Code .vsix packaging failed — run later: code-agents plugin package vscode"
            fi
        fi

        if command -v code &>/dev/null; then
            if [ -n "${_vsix:-}" ]; then
                if code --install-extension "$_vsix" 2>/dev/null; then
                    info "VS Code extension installed from .vsix"
                else
                    dim "Auto-install failed — install manually: code --install-extension $_vsix"
                fi
            else
                dim "No .vsix available — run: code-agents plugin build vscode && code-agents plugin package vscode"
            fi
        else
            dim "VS Code CLI ('code') not in PATH — extension built but not installed via CLI"
            dim "  VS Code → Cmd+Shift+P → 'Shell Command: Install code in PATH'"
            if [ -n "${_vsix:-}" ]; then
                dim "  Or install from disk: $_vsix"
            else
                dim "  Then run: code-agents plugin install vscode"
            fi
        fi
    fi
fi

# --- Copy webview to IntelliJ resources (for shared UI) ---
_webview_build="$CODE_AGENTS_DIR/extensions/vscode/webview-ui/build"
_ij_dir="$CODE_AGENTS_DIR/extensions/intellij"
if [ -d "$_webview_build" ] && [ -d "$_ij_dir/src/main/resources/webview" ]; then
    cp "$_webview_build/index.html" "$_ij_dir/src/main/resources/webview/" 2>/dev/null
    mkdir -p "$_ij_dir/src/main/resources/webview/assets"
    cp -r "$_webview_build/assets/"* "$_ij_dir/src/main/resources/webview/assets/" 2>/dev/null
    dim "Webview copied to IntelliJ resources"
fi

# --- Java (needed for IntelliJ plugin) ---
if ! command -v java &>/dev/null; then
    dim "Java not found — attempting to install..."
    if command -v brew &>/dev/null; then
        brew install openjdk@21 2>&1 | tail -3
        # Symlink for macOS
        if [ -d "/opt/homebrew/opt/openjdk@21" ]; then
            sudo ln -sfn /opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk /Library/Java/JavaVirtualMachines/openjdk-21.jdk 2>/dev/null
        fi
        if command -v java &>/dev/null; then
            info "Java 21 installed via Homebrew"
        else
            warn "Java install failed — IntelliJ plugin won't build"
            dim "Install manually: https://adoptium.net/"
        fi
    elif [ "$(uname)" = "Linux" ] && command -v apt-get &>/dev/null; then
        sudo apt-get install -y openjdk-21-jdk 2>&1 | tail -3
        command -v java &>/dev/null && info "Java 21 installed via apt"
    else
        dim "Install Java 21: https://adoptium.net/ or brew install openjdk@21"
    fi
fi

# --- Gradle (needed for IntelliJ plugin build) ---
if ! command -v gradle &>/dev/null && [ ! -f "$_ij_dir/gradlew" ]; then
    if command -v java &>/dev/null; then
        dim "Gradle not found — attempting to install..."
        if command -v brew &>/dev/null; then
            brew install gradle 2>&1 | tail -3
            command -v gradle &>/dev/null && info "Gradle installed via Homebrew"
        elif [ "$(uname)" = "Linux" ] && command -v apt-get &>/dev/null; then
            sudo apt-get install -y gradle 2>&1 | tail -3
            command -v gradle &>/dev/null && info "Gradle installed via apt"
        else
            dim "Install Gradle: brew install gradle"
        fi
    fi
fi

# --- IntelliJ Plugin: generate wrapper + build ---
_ij_built=false
if command -v java &>/dev/null && [ -f "$_ij_dir/build.gradle.kts" ]; then

    # SSL fix for corporate networks: import corporate CA into local Java truststore
    _local_cacerts="$_ij_dir/gradle/cacerts"
    if [ ! -f "$_local_cacerts" ]; then
        _corp_ca=""
        # Auto-detect corporate CA bundle
        for _ca_candidate in "$HOME/corporate-ca.pem" "$HOME/.corporate-ca.pem" "/etc/ssl/certs/corporate-ca.pem"; do
            if [ -f "$_ca_candidate" ]; then
                _corp_ca="$_ca_candidate"
                break
            fi
        done

        if [ -n "$_corp_ca" ] && command -v keytool &>/dev/null; then
            dim "Importing corporate CA certificates for Gradle SSL..."
            _java_home="$(/usr/libexec/java_home 2>/dev/null || echo "$JAVA_HOME")"
            _java_cacerts="$_java_home/lib/security/cacerts"
            if [ -f "$_java_cacerts" ]; then
                mkdir -p "$_ij_dir/gradle"
                cp "$_java_cacerts" "$_local_cacerts"
                # Import all certs from the bundle
                awk 'BEGIN{n=0} /BEGIN CERTIFICATE/{n++; fn="/tmp/_ca_cert_"n".pem"} {print > fn}' "$_corp_ca"
                _imported=0
                for _cert in /tmp/_ca_cert_*.pem; do
                    if [ -f "$_cert" ]; then
                        _imported=$((_imported + 1))
                        keytool -importcert -trustcacerts -alias "corp-ca-$_imported" \
                            -file "$_cert" -keystore "$_local_cacerts" \
                            -storepass changeit -noprompt 2>/dev/null
                    fi
                done
                rm -f /tmp/_ca_cert_*.pem
                info "Imported $_imported corporate CA certificates"
            fi
        fi
    fi

    # Ensure gradlew exists (pre-bundled or generate)
    _ssl_opts="${_ssl_opts:-}"
    if [ ! -f "$_ij_dir/gradlew" ]; then
        dim "Setting up Gradle wrapper..."
        if command -v gradle &>/dev/null; then
            (cd "$_ij_dir" && gradle wrapper --gradle-version=8.13 $_ssl_opts 2>/dev/null)
        fi

        # If gradle wrapper generation failed (SSL/proxy), create manually
        if [ ! -f "$_ij_dir/gradlew" ]; then
            dim "Downloading Gradle wrapper directly..."
            mkdir -p "$_ij_dir/gradle/wrapper"
            # Download wrapper jar
            curl -sL "https://raw.githubusercontent.com/gradle/gradle/v8.13.0/gradle/wrapper/gradle-wrapper.jar" \
                -o "$_ij_dir/gradle/wrapper/gradle-wrapper.jar" 2>/dev/null
            # Create wrapper properties
            cat > "$_ij_dir/gradle/wrapper/gradle-wrapper.properties" << 'GWPROPS'
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-8.13-bin.zip
networkTimeout=10000
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
GWPROPS
            # Create gradlew script
            cat > "$_ij_dir/gradlew" << 'GRADLEW'
#!/bin/sh
# Gradle wrapper — auto-detects macOS Keychain for corporate SSL trust
APP_HOME=$( cd "${0%"${0##*/}"}." > /dev/null && pwd -P ) || exit
SSL_OPTS=""
case "$(uname)" in
    Darwin*) SSL_OPTS="-Djavax.net.ssl.trustStoreType=KeychainStore" ;;
esac
JAVACMD=${JAVA_HOME:+$JAVA_HOME/bin/}java
exec "$JAVACMD" \
    $SSL_OPTS \
    -Dorg.gradle.appname="${0##*/}" \
    -classpath "$APP_HOME/gradle/wrapper/gradle-wrapper.jar" \
    org.gradle.wrapper.GradleWrapperMain \
    "$@"
GRADLEW
            chmod +x "$_ij_dir/gradlew"
            if [ -f "$_ij_dir/gradle/wrapper/gradle-wrapper.jar" ]; then
                info "Gradle wrapper created manually"
            else
                warn "Failed to download Gradle wrapper"
            fi
        fi
    fi

    _gradle_cmd=""
    if [ -f "$_ij_dir/gradlew" ]; then
        chmod +x "$_ij_dir/gradlew"
        _gradle_cmd="$_ij_dir/gradlew"
    fi

    if [ -n "$_gradle_cmd" ]; then
        dim "Building IntelliJ plugin (this may take a few minutes on first run)..."
        (cd "$_ij_dir" && "$_gradle_cmd" buildPlugin $_ssl_opts 2>/dev/null) \
            && { info "IntelliJ plugin built"; _ij_built=true; } \
            || warn "IntelliJ plugin build failed (run 'code-agents plugin build intellij' later)"
    else
        dim "Skipping IntelliJ build (no Gradle wrapper available)"
    fi
else
    dim "Skipping IntelliJ plugin build (Java not found)"
fi

# --- IntelliJ Plugin: install hint ---
if [ "$_ij_built" = true ]; then
    _ij_zip=$(find "$_ij_dir/build/distributions" -name "*.zip" 2>/dev/null | head -1)
    if [ -n "$_ij_zip" ]; then
        dim "IntelliJ plugin: $_ij_zip"
        dim "  Install: IDE → Settings → Plugins → Install from disk → select the .zip"
    fi
fi

# --- Chrome Extension: hint ---
if [ -f "$CODE_AGENTS_DIR/extensions/chrome/manifest.json" ]; then
    dim "Chrome extension ready (no build needed)"
    dim "  Install: chrome://extensions → Load unpacked → select extensions/chrome/"
fi

# Add to PATH
POETRY_BIN="$(cd "$CODE_AGENTS_DIR" && poetry env info -p 2>/dev/null)/bin"
SHELL_RC=""
if [ -f "$HOME/.zshrc" ]; then
    SHELL_RC="$HOME/.zshrc"
elif [ -f "$HOME/.bashrc" ]; then
    SHELL_RC="$HOME/.bashrc"
fi

# Create a wrapper script in ~/.local/bin
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/code-agents" << 'WRAPPER'
#!/usr/bin/env bash
# Code Agents CLI wrapper — runs 'code-agents' from ~/.code-agents
# Captures the user's working directory so agents work on THEIR repo
export CODE_AGENTS_USER_CWD="$(pwd)"
export PYTHONDONTWRITEBYTECODE=1
cd "$HOME/.code-agents" && poetry run code-agents "$@"
WRAPPER
chmod +x "$HOME/.local/bin/code-agents"

# Ensure ~/.local/bin is in PATH
if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
    if [ -n "$SHELL_RC" ]; then
        echo '' >> "$SHELL_RC"
        echo '# Code Agents CLI' >> "$SHELL_RC"
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_RC"
        info "Added ~/.local/bin to PATH in $(basename "$SHELL_RC")"
    fi
    export PATH="$HOME/.local/bin:$PATH"
fi

# Install/update shell tab-completion (always regenerate to pick up new flags)
dim "Installing shell tab-completion..."
if [ -f "$HOME/.zshrc" ]; then
    # Remove old completion block if present, then regenerate
    if grep -q "# code-agents completion" "$HOME/.zshrc" 2>/dev/null; then
        # Remove old block: from "# code-agents completion" to "compdef _code_agents code-agents"
        sed -i.bak '/# code-agents completion/,/compdef _code_agents code-agents/d' "$HOME/.zshrc" 2>/dev/null || true
        dim "Removed old completions, regenerating..."
    fi
    if "$HOME/.local/bin/code-agents" completions --zsh >> "$HOME/.zshrc" 2>/dev/null; then
        info "Tab-completion installed/updated in ~/.zshrc (14 init flags, 14 agents)"
    else
        warn "Could not append zsh completions (fix code-agents / Poetry, then: code-agents completions --zsh >> ~/.zshrc)"
    fi
elif [ -f "$HOME/.bashrc" ]; then
    if grep -q "# code-agents completion" "$HOME/.bashrc" 2>/dev/null; then
        sed -i.bak '/# code-agents completion/,/complete -F _code_agents_completions code-agents/d' "$HOME/.bashrc" 2>/dev/null || true
        dim "Removed old completions, regenerating..."
    fi
    if "$HOME/.local/bin/code-agents" completions --bash >> "$HOME/.bashrc" 2>/dev/null; then
        info "Tab-completion installed/updated in ~/.bashrc (14 init flags, 14 agents)"
    else
        warn "Could not append bash completions (fix code-agents / Poetry, then: code-agents completions --bash >> ~/.bashrc)"
    fi
fi

# ============================================================================
# STEP 5: Local LLM (Ollama) — optional, best-effort
# ============================================================================
step "5/7" "Local LLM (Ollama) — optional..."

DEFAULT_OLLAMA_MODEL="${CODE_AGENTS_DEFAULT_OLLAMA_MODEL:-qwen2.5-coder:7b}"

_append_local_llm_config() {
    _cfg="$HOME/.code-agents/config.env"
    if [ ! -f "$_cfg" ]; then
        touch "$_cfg" 2>/dev/null || true
    fi
    if [ ! -f "$_cfg" ]; then
        warn "Could not create ~/.code-agents/config.env — set CODE_AGENTS_LOCAL_LLM_* manually (see setup.md)"
        return 0
    fi
    if grep -q "CODE_AGENTS_LOCAL_LLM_URL" "$_cfg" 2>/dev/null; then
        dim "config.env already defines CODE_AGENTS_LOCAL_LLM_URL — skipping template append"
        return 0
    fi
    {
        echo ""
        echo "# --- Local LLM (appended by install.sh) ---"
        echo "CODE_AGENTS_BACKEND=local"
        echo "CODE_AGENTS_LOCAL_LLM_URL=http://127.0.0.1:11434/v1"
        echo "CODE_AGENTS_LOCAL_LLM_API_KEY=local"
        echo "CODE_AGENTS_MODEL=${DEFAULT_OLLAMA_MODEL}"
    } >> "$_cfg" 2>/dev/null && info "Appended local LLM defaults to ~/.code-agents/config.env" \
        || warn "Could not append local LLM block to config.env"
}

if [ "${SKIP_OLLAMA:-}" = "1" ]; then
    dim "SKIP_OLLAMA=1 — skipping Ollama install (defaults still appended if config is new)"
    _append_local_llm_config
else
    if command -v ollama &>/dev/null; then
        info "Ollama found: $(ollama --version 2>/dev/null || echo ok)"
        dim "Pulling default model: $DEFAULT_OLLAMA_MODEL (best-effort)..."
        ollama pull "$DEFAULT_OLLAMA_MODEL" 2>&1 | tail -5 || warn "ollama pull failed — run later: ollama pull $DEFAULT_OLLAMA_MODEL"
    else
        dim "Installing Ollama (https://ollama.com)..."
        if curl -fsSL https://ollama.com/install.sh | sh 2>&1 | tail -8; then
            info "Ollama install script finished"
        else
            warn "Ollama install failed — install manually from https://ollama.com/download"
        fi
        if command -v ollama &>/dev/null; then
            dim "Pulling default model: $DEFAULT_OLLAMA_MODEL..."
            ollama pull "$DEFAULT_OLLAMA_MODEL" 2>&1 | tail -5 || warn "ollama pull failed — run later: ollama pull $DEFAULT_OLLAMA_MODEL"
        fi
    fi
    _append_local_llm_config
fi

# ============================================================================
# STEP 6: TypeScript Terminal (optional — requires Node.js >= 18)
# ============================================================================
if command -v node &>/dev/null; then
    _node_major=$(node -v | sed 's/v//' | cut -d. -f1)
    if [ "$_node_major" -ge 18 ] 2>/dev/null; then
        step "6/7" "Building TypeScript terminal..."
        if [ -d "$CODE_AGENTS_DIR/terminal" ] && [ -f "$CODE_AGENTS_DIR/terminal/package.json" ]; then
            cd "$CODE_AGENTS_DIR/terminal"
            if npm ci --quiet 2>&1 | tail -3; then
                if npm run build 2>&1 | tail -3; then
                    info "TypeScript terminal built"
                    dim "Launch with: code-agents chat"
                else
                    warn "TypeScript terminal build failed (will auto-build on first 'code-agents chat')"
                fi
            else
                warn "npm ci failed (will auto-install on first 'code-agents chat')"
            fi
            cd "$CODE_AGENTS_DIR"
        else
            dim "TypeScript terminal not found — skipping"
        fi
    else
        dim "Node.js $_node_major found but < 18 — skipping TypeScript terminal"
    fi
else
    dim "Node.js not found — skipping TypeScript terminal (optional)"
fi

# ============================================================================
# STEP 7: Done!
# ============================================================================
step "7/7" "Installation complete!"
echo ""
divider
echo ""
echo -e "  ${BOLD}${GREEN}Code Agents is installed!${RESET}"
echo ""
echo -e "  ${BOLD}How to use:${RESET}"
echo ""
echo -e "    ${CYAN}# Go to any git repo and initialize:${RESET}"
echo -e "    ${BOLD}cd /path/to/your-project${RESET}"
echo -e "    ${BOLD}code-agents init${RESET}"
echo ""
echo -e "    ${DIM}This will:${RESET}"
echo -e "    ${DIM}  1. Configure backend (default: local LLM / Cursor / Claude) → ~/.code-agents/config.env${RESET}"
echo -e "    ${DIM}  2. Ask for Jenkins/ArgoCD config (optional) → saved to .env.code-agents${RESET}"
echo -e "    ${DIM}  3. Start the server pointing at your repo${RESET}"
echo ""
echo -e "    ${CYAN}# After init, just start the server:${RESET}"
echo -e "    ${BOLD}cd /path/to/your-project${RESET}"
echo -e "    ${BOLD}code-agents start${RESET}"
echo ""
echo -e "    ${CYAN}# Other commands:${RESET}"
echo -e "    ${BOLD}code-agents help${RESET}     ${DIM}— show all commands${RESET}"
echo -e "    ${BOLD}code-agents init${RESET}     ${DIM}— configure in current repo${RESET}"
echo -e "    ${BOLD}code-agents start${RESET}    ${DIM}— start server${RESET}"
echo -e "    ${BOLD}code-agents setup${RESET}    ${DIM}— full setup wizard${RESET}"
echo -e "    ${BOLD}code-agents plugin${RESET}   ${DIM}— manage IDE extensions (VS Code, IntelliJ)${RESET}"
echo -e "    ${BOLD}code-agents doctor${RESET}   ${DIM}— diagnose env, integrations, IDE extensions${RESET}"
echo -e "    ${BOLD}code-agents readme${RESET}   ${DIM}— view README in terminal${RESET}"
echo ""
echo -e "  ${BOLD}IDE Extensions:${RESET}"
if [ "$_vscode_built" = true ]; then
    echo -e "    ${GREEN}✓${RESET} VS Code extension built"
else
    echo -e "    ${DIM}· VS Code extension: run 'code-agents plugin build vscode'${RESET}"
fi
if [ "$_ij_built" = true ]; then
    echo -e "    ${GREEN}✓${RESET} IntelliJ plugin built"
else
    echo -e "    ${DIM}· IntelliJ plugin: run 'code-agents plugin build intellij'${RESET}"
fi
echo -e "    ${DIM}· Chrome extension: load extensions/chrome/ in chrome://extensions${RESET}"
echo ""
divider
echo ""
echo -e "  ${DIM}Restart your terminal (or run: source ${SHELL_RC:-~/.zshrc}) then:${RESET}"
echo ""
echo -e "    ${BOLD}cd your-project && code-agents init${RESET}"
echo ""
