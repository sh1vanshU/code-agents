---
name: explain-code
description: Explain any function, class, or module in plain English with edge cases, dependencies, and side effects
tags: [code-understanding, explanation, analysis]
---

# Explain Code

Analyze and explain code constructs in plain English.

## Workflow

1. Parse the target (file:function, file:class, or file)
2. Use AST analysis to extract structure, dependencies, calls
3. Detect edge cases (null handling, empty collections, timeouts)
4. Detect side effects (I/O, HTTP calls, shell commands, logging)
5. Build comprehensive explanation with signature, summary, and details

## Usage

```
/explain-code code_agents/stream.py:build_prompt
/explain-code code_agents/config.py:AgentConfig
/explain-code code_agents/backend.py
```

## Output Includes
- Function signature with types
- One-line summary
- Detailed explanation
- Cyclomatic complexity score
- Edge cases to consider
- Side effects detected
- Dependencies (what it calls)
- Callers (who calls it)
