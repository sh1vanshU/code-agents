---
name: explore-smart-search
description: Knowledge Graph-powered codebase search — find symbols, files, and blast radius instantly
---

## Smart Search Workflow (Knowledge Graph Powered)

Use the knowledge graph API for instant project structure queries instead of manual grep/find.

### 1. Search for symbols (functions, classes, imports)
```bash
curl -sS "${BASE_URL}/knowledge-graph/query?keywords=auth,login"
```
Returns matching symbols with file paths, line numbers, signatures, and docstrings.

### 2. Check blast radius for a file change
```bash
curl -sS "${BASE_URL}/knowledge-graph/blast-radius?file=code_agents/backend.py"
```
Returns all files that depend on or are affected by changes to the given file.

### 3. Get all symbols in a specific file
```bash
curl -sS "${BASE_URL}/knowledge-graph/file/code_agents/backend.py"
```
Returns functions, classes, methods, imports in that file with line numbers.

### 4. Check graph statistics
```bash
curl -sS "${BASE_URL}/knowledge-graph/stats"
```
Returns total files, symbols, edges, and last build time.

### 5. Then drill into specific files
After identifying relevant files from the knowledge graph, read them for deep analysis:
```bash
cat -n path/to/relevant/file.py | head -100
```

## When to Use

- "Find all files related to authentication" → Step 1 (query keywords)
- "What would be affected if I change backend.py?" → Step 2 (blast radius)
- "Show me all functions in the config module" → Step 3 (file symbols)
- "Where is the payment handler defined?" → Step 1 (query keywords)

## Fallback

If the knowledge graph is not built or returns empty results, fall back to traditional search:
```bash
grep -rn "def authenticate" --include="*.py" .
find . -name "*.py" -path "*/auth/*"
```
