# Code Agents — Makefile
# Usage: make <target>

.PHONY: help install dev test lint start stop restart chat status doctor update clean

# Default
help: ## Show this help
	@echo ""
	@echo "  Code Agents — Make targets"
	@echo "  ─────────────────────────────────────────"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ── Install ──────────────────────────────────────────────────────────────────

install: ## Install all dependencies (core + cursor + dev)
	poetry install --with cursor --with dev
	@echo "✓ All dependencies installed"

dev: ## Install dev dependencies only
	poetry install --with dev
	@echo "✓ Dev dependencies installed"

setup: ## Run the full interactive setup wizard
	poetry run code-agents setup

init: ## Initialize code-agents in current repo
	poetry run code-agents init

security-scan: ## Scan dependencies for known vulnerabilities
	@echo "Scanning Python dependencies..."
	poetry run pip-audit 2>/dev/null || poetry run pip install pip-audit && poetry run pip-audit
	@echo ""
	@echo "Scanning Node.js dependencies..."
	cd extensions/vscode && npm audit --omit=dev 2>/dev/null || echo "(npm not installed)"
	@echo "✓ Security scan complete"

audit: ## Run initiater quality audit (14 rules)
	poetry run python initiater/run_audit.py

# ── Server ───────────────────────────────────────────────────────────────────

start: ## Start the server (background)
	poetry run code-agents start

start-fg: ## Start the server (foreground, for debugging)
	poetry run code-agents start --fg

stop: ## Stop the running server
	poetry run code-agents shutdown

restart: ## Restart the server
	poetry run code-agents restart

status: ## Check server health and config
	poetry run code-agents status

doctor: ## Diagnose common issues
	poetry run code-agents doctor

# ── Chat ─────────────────────────────────────────────────────────────────────

chat: ## Open interactive chat (pick agent from menu)
	poetry run code-agents chat

chat-reasoning: ## Chat with code-reasoning agent
	poetry run code-agents chat code-reasoning

chat-writer: ## Chat with code-writer agent
	poetry run code-agents chat code-writer

chat-reviewer: ## Chat with code-reviewer agent
	poetry run code-agents chat code-reviewer

chat-tester: ## Chat with code-tester agent
	poetry run code-agents chat code-tester

chat-jenkins: ## Chat with jenkins-build agent
	poetry run code-agents chat jenkins-build

chat-qa: ## Chat with qa-regression agent
	poetry run code-agents chat qa-regression

# ── Testing ──────────────────────────────────────────────────────────────────

test: ## Run all tests
	poetry run pytest

test-v: ## Run all tests (verbose)
	poetry run pytest -v

test-chat: ## Run chat tests only
	poetry run pytest tests/test_chat.py -v

test-cli: ## Run CLI tests only
	poetry run pytest tests/test_cli.py -v

test-jenkins: ## Run Jenkins tests only
	poetry run pytest tests/test_jenkins_client.py -v

test-env: ## Run env loader tests only
	poetry run pytest tests/test_env_loader.py -v

test-rules: ## Run rules loader tests only
	poetry run pytest tests/test_rules_loader.py -v

test-cov: ## Run tests with coverage report
	poetry run pytest --cov=code_agents --cov-report=term-missing

# ── Code Quality ─────────────────────────────────────────────────────────────

audit: ## Run project quality audit
	poetry run python initiater/run_audit.py

audit-docs: ## Audit documentation sync
	poetry run python initiater/run_audit.py --rules documentation,workflow

# ── Utilities ────────────────────────────────────────────────────────────────

agents: ## List all available agents
	poetry run code-agents agents

rules: ## List active rules
	poetry run code-agents rules

logs: ## Tail server logs
	poetry run code-agents logs

config: ## Show current configuration (secrets masked)
	poetry run code-agents config

update: ## Update code-agents to latest version
	poetry run code-agents update

completions: ## Install shell tab-completion
	poetry run code-agents completions --install

sessions: ## List saved chat sessions
	poetry run code-agents sessions

# ── Jenkins ──────────────────────────────────────────────────────────────────

jenkins-test: ## Test Jenkins connectivity
	poetry run python scripts/test_jenkins.py

jenkins-jobs: ## List Jenkins jobs (requires running server)
	@curl -s "http://127.0.0.1:8000/jenkins/jobs?folder=pg2/pg2-dev-build-jobs" | python3 -m json.tool

# ── Docker ───────────────────────────────────────────────────────────────────

docker-build: ## Build Docker image
	docker build -t code-agents .

docker-run: ## Run in Docker
	docker run -p 8000:8000 -e CURSOR_API_KEY=$${CURSOR_API_KEY} code-agents

# ── Cleanup ──────────────────────────────────────────────────────────────────

clean: ## Remove build artifacts, caches, and temp files
	rm -rf __pycache__ .pytest_cache .mypy_cache
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "✓ Cleaned"

clean-logs: ## Remove all log files
	rm -rf logs/*.log logs/*.log.*
	@echo "✓ Logs cleaned"

clean-sessions: ## Clear all saved chat sessions
	poetry run code-agents sessions clear
