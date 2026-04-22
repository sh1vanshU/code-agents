---
name: code-examples
description: Find real code examples for any concept, library, or pattern in the codebase
tags: [code-understanding, search, examples]
---

# Code Example Finder

Answer "how is X used in this codebase?" by finding, grouping, and ranking real examples.

## Workflow

1. Search codebase for the query term
2. Extract surrounding code blocks for context
3. Classify each example (import, definition, function_call, context_manager, error_handling, etc.)
4. Score by relevance (definitions > references, shorter > longer, commented > uncommented)
5. Present ranked examples grouped by pattern type

## Usage

```
/examples Redis
/examples subprocess
/examples error handling
/examples HTTPException
```

## Output Includes
- Examples grouped by pattern (import, definition, function_call, etc.)
- Code snippets with file:line references
- Relevance scoring
- Test vs production code distinction
