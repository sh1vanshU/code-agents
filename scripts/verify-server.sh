#!/usr/bin/env bash
# Quick check that Code Agents is this checkout and responding (no secrets).
set -euo pipefail
BASE="${CODE_AGENTS_URL:-http://localhost:8000}"
echo "Checking $BASE ..."
curl -sfS "$BASE/health" | python3 -m json.tool
echo ""
curl -sfS "$BASE/diagnostics" | python3 -m json.tool
echo ""
echo "OK: compare backend_py above to your code_agents/backend.py path; restart if wrong."
