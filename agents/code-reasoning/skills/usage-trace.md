---
name: usage-trace
description: Find all usages of any symbol across the codebase — imports, calls, tests, configs
tags: [code-understanding, search, tracing]
---

# Usage Trace

Find every place a symbol is used across the entire codebase.

## Workflow

1. Search codebase for the symbol name
2. Classify each usage (import, call, definition, assignment, test, config, reference)
3. Group by type and file
4. Report totals and detailed locations

## Usage

```
/usage-trace build_prompt
/usage-trace CODE_AGENTS_BACKEND
/usage-trace AgentConfig
```

## Output Includes
- Total usage count
- Breakdown by type (imports, calls, tests, configs, references)
- File-by-file listing
- Definition locations
