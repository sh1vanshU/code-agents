---
name: trace-error
description: Trace an error through the codebase to find root cause
trigger: "[SKILL:trace-error]"
---

# Trace Error

## Steps

1. **Parse the error** — Extract structured data:
   - Error type (e.g., `AttributeError`, `TypeError`, `NullPointerException`)
   - Error message
   - File path + line number
   - Full stack trace / call chain

2. **Read the error location** — Read the file at the error line with 20 lines of context above and below.

3. **Trace the call chain** — For each frame in the stack trace:
   - Read the calling function
   - Understand what data flows to the error point
   - Check function signatures and types

4. **Check related code** — Use knowledge graph or grep to find:
   - Other callers of the broken function
   - Recent changes to the file (`git log -5 <file>`)
   - Similar patterns elsewhere that might have the same bug

5. **Identify root cause** — Determine:
   - What assumption is violated?
   - What input triggers the failure?
   - Is it a data issue, logic issue, or API change?

6. **Document findings**:
   ```
   ROOT CAUSE: [description]
   ERROR: [type] at [file:line]
   TRIGGER: [what input/condition causes it]
   FIX STRATEGY: [how to fix it]
   ```
