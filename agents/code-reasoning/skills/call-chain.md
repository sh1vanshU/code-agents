---
name: call-chain
description: Trace full call tree — who calls a function and what it calls, as a visual tree
tags: [code-understanding, analysis, dependencies]
---

# Call Chain Analyzer

Show the complete call tree for any function — both upstream (callers) and downstream (callees).

## Workflow

1. Build call graph from all Python files in the codebase
2. Find target function in the graph
3. Build callers tree (upstream) to configurable depth
4. Build callees tree (downstream) to configurable depth
5. Detect entry points, leaf functions, and recursive calls

## Usage

```
/call-chain build_prompt
/call-chain build_prompt --depth 5
```

## Output Includes
- Target location (file:line)
- Callers tree with file:line links
- Callees tree with file:line links
- Flags: ENTRY POINT, LEAF, RECURSIVE
- Direct caller/callee counts
