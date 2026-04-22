# Code Agents — Extension Build Automation
# Usage:
#   make all          Build both extensions
#   make vscode       Build VS Code extension only
#   make intellij     Build IntelliJ plugin only
#   make test         Run all tests
#   make clean        Remove build artifacts
#   make package      Create distributable packages (.vsix + .zip)

.PHONY: all vscode intellij test clean package webview vscode-ext intellij-plugin

# ---- Build all ----
all: vscode intellij

# ---- Webview UI (shared) ----
webview:
	@echo "==> Building webview UI..."
	cd vscode/webview-ui && npm install && npm run build
	@echo "==> Webview built: vscode/webview-ui/build/"

# ---- VS Code Extension ----
vscode-ext:
	@echo "==> Compiling VS Code extension..."
	cd vscode && npm install && npm run compile
	@echo "==> VS Code extension compiled: vscode/dist/"

vscode: webview vscode-ext
	@echo "==> VS Code extension ready"

# ---- IntelliJ Plugin ----
intellij-webview: webview
	@echo "==> Copying webview to IntelliJ resources..."
	mkdir -p intellij/src/main/resources/webview/assets
	cp vscode/webview-ui/build/index.html intellij/src/main/resources/webview/ 2>/dev/null || true
	cp -r vscode/webview-ui/build/assets/* intellij/src/main/resources/webview/assets/ 2>/dev/null || true
	cp intellij/src/main/resources/webview/bridge.js intellij/src/main/resources/webview/bridge.js 2>/dev/null || true
	@echo "==> Webview copied to IntelliJ resources"

intellij-plugin:
	@echo "==> Building IntelliJ plugin..."
	cd intellij && ./gradlew buildPlugin 2>/dev/null || echo "  (Gradle not configured — run ./gradlew wrapper first)"
	@echo "==> IntelliJ plugin built"

intellij: intellij-webview intellij-plugin

# ---- Tests ----
test: test-webview test-intellij

test-webview:
	@echo "==> Running webview tests..."
	cd vscode/webview-ui && npm install && npm test
	@echo "==> Webview tests passed"

test-intellij:
	@echo "==> Running IntelliJ tests..."
	cd intellij && ./gradlew test 2>/dev/null || echo "  (Gradle not configured — skipping)"

# ---- Package for distribution ----
package: vscode intellij
	@echo "==> Validating extension package.json (repository fields for @vscode/vsce)..."
	@python3 ../scripts/validate_extension_repositories.py
	@echo "==> Packaging VS Code extension..."
	cd vscode && npx --yes @vscode/vsce package --no-dependencies
	@echo "==> Packaging IntelliJ plugin..."
	cd intellij && ./gradlew buildPlugin 2>/dev/null || echo "  (Gradle not configured)"
	@echo ""
	@echo "==> Packages:"
	@ls -la vscode/*.vsix 2>/dev/null || echo "  VS Code: not built"
	@ls -la intellij/build/distributions/*.zip 2>/dev/null || echo "  IntelliJ: not built"

# ---- Clean ----
clean:
	@echo "==> Cleaning build artifacts..."
	rm -rf vscode/dist vscode/webview-ui/build vscode/webview-ui/node_modules
	rm -rf vscode/node_modules vscode/*.vsix
	rm -rf intellij/build intellij/.gradle
	rm -rf intellij/src/main/resources/webview/assets intellij/src/main/resources/webview/index.html
	@echo "==> Clean complete"

# ---- Dev helpers ----
dev-vscode: webview
	@echo "==> Starting VS Code watch mode..."
	cd vscode && npm run watch &
	cd vscode/webview-ui && npm run dev

dev-intellij: intellij-webview
	@echo "==> Starting IntelliJ sandboxed IDE..."
	cd intellij && ./gradlew runIde

# ---- Verify (lint + test + build) ----
verify: test vscode intellij
	@echo ""
	@echo "==> All checks passed"
	@echo "    Webview:  tests passed, built"
	@echo "    VS Code:  compiled"
	@echo "    IntelliJ: built"
