#!/usr/bin/env bash
# Start Code Agents + Open WebUI so you can chat in the browser (no Docker).
# Run once, then use http://localhost:8080 for chat. Press Enter here to stop both.

set -e
cd "$(dirname "$0")/.."

# Load .env if present
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

if [ -z "${CURSOR_API_KEY:-}" ]; then
  echo "Warning: CURSOR_API_KEY not set. Set it in .env or the environment."
fi

# Logging: default to DEBUG when started via this script; override in .env or env
export LOG_LEVEL="${LOG_LEVEL:-DEBUG}"

# Public URL for echoes (Open WebUI, Atlassian OAuth); override when using a tunnel
: "${PORT:=8000}"
CODE_AGENTS_BASE="${CODE_AGENTS_PUBLIC_BASE_URL:-http://127.0.0.1:$PORT}"
# So /oauth/atlassian success page links to chat (override in .env if WebUI uses another host/port).
export OPEN_WEBUI_PUBLIC_URL="${OPEN_WEBUI_PUBLIC_URL:-http://localhost:8080}"
# After login, 302 to Open WebUI when not set in .env. To force the HTML “Signed in” page instead, add:
#   ATLASSIAN_OAUTH_SUCCESS_REDIRECT=
# to .env (empty value — do not omit the line if you use this script’s default and want to disable it).
if ! [[ -v ATLASSIAN_OAUTH_SUCCESS_REDIRECT ]]; then
  export ATLASSIAN_OAUTH_SUCCESS_REDIRECT="$OPEN_WEBUI_PUBLIC_URL"
fi

# Start Code Agents in background
echo "Starting Code Agents on $CODE_AGENTS_BASE ..."
poetry run code-agents &
CODE_AGENTS_PID=$!

# Give Code Agents a moment to bind
sleep 2

# Start Open WebUI (see README: pipx install open-webui --python python3.12, or pip install open-webui in a 3.11/3.12 venv)
if ! command -v open-webui &>/dev/null; then
  echo "Open WebUI not found. Install per README (Open WebUI Integration), e.g.: pipx install open-webui --python python3.12"
  kill $CODE_AGENTS_PID 2>/dev/null || true
  exit 1
fi

echo "Starting Open WebUI on http://localhost:8080 ..."
open-webui serve &
OPEN_WEBUI_PID=$!

cleanup() {
  echo "Stopping Code Agents and Open WebUI..."
  kill $CODE_AGENTS_PID 2>/dev/null || true
  kill $OPEN_WEBUI_PID 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM

echo ""
echo "  Code Agents:  $CODE_AGENTS_BASE"
echo "  Open WebUI:   http://localhost:8080  <- use this for chat"
echo "  OPEN_WEBUI_PUBLIC_URL=$OPEN_WEBUI_PUBLIC_URL"
echo "  ATLASSIAN_OAUTH_SUCCESS_REDIRECT=$ATLASSIAN_OAUTH_SUCCESS_REDIRECT  (302 after Atlassian login if set)"
echo ""
echo "  LOG_LEVEL=$LOG_LEVEL"
echo ""
echo "  In Open WebUI: Settings > Connections > OpenAI"
echo "  URL: $CODE_AGENTS_BASE/v1   API Key: (any value)"
echo "  (Use that URL to see all agents including agent-router; per-agent URLs only expose one agent.)"
if [ -n "${ATLASSIAN_OAUTH_CLIENT_ID:-}" ]; then
  echo "  Atlassian OAuth (if configured): $CODE_AGENTS_BASE/oauth/atlassian/"
fi
echo ""
echo "Press Enter to stop both servers."
read -r
cleanup
