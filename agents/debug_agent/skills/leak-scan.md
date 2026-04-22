---
name: leak-scan
description: Memory leak pattern scanner — unclosed resources, growing caches, reference cycles
tags: [debug, memory, leak, resources]
---

# Memory Leak Scanner

## Workflow

1. **Scan code** — Search for resource allocation patterns: file handles, DB connections, HTTP clients, sockets.
2. **Check cleanup** — Verify each allocation has a corresponding close/release in a finally block or context manager.
3. **Inspect caches** — Find in-memory caches, dicts, or lists that grow without bounds or eviction policy.
4. **Detect reference cycles** — Look for circular references that prevent garbage collection.
5. **Review event listeners** — Check for listeners or callbacks registered but never removed.
6. **Report** — List each finding with: file, line, pattern type, severity, and suggested fix.

## Notes

- Language-specific: context managers (Python), try-with-resources (Java), defer (Go), RAII (C++/Rust).
- For runtime analysis, suggest heap profiling tools appropriate to the language.
