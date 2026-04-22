---
name: stack-decode
description: Stack trace decoder — paste trace, get mapped code, root cause, and fix suggestion
tags: [debug, stack-trace, error, root-cause]
---

# Stack Trace Decoder

## Workflow

1. **Parse the trace** — Extract exception type, message, file paths, line numbers, and frame chain.
2. **Map to source** — Resolve each frame to the actual source file; read the surrounding code context.
3. **Identify root cause** — Walk the frame chain bottom-up to find the originating fault (not just the symptom).
4. **Check common patterns** — Match against known error categories: null/undefined access, type mismatch, import failure, OOM, timeout, permission denied.
5. **Suggest fix** — Provide a concrete code change or config adjustment that addresses the root cause.
6. **Summarize** — Return: root cause (1 sentence), affected code path, suggested fix, and confidence level.

## Notes

- For minified/obfuscated traces, ask for source maps or ProGuard mappings.
- For multi-language traces (e.g. Python calling C extensions), decode each layer separately.
- Flag if the trace indicates an infrastructure issue vs. application bug.
