---
name: trace-flow
description: Trace a request or data flow end-to-end through the system
---

## Workflow

1. **Define the starting point.** Identify where the flow begins: an API endpoint, a CLI command, a message consumer, a cron job, or a user action.

2. **Read the entry point code.** Open the file that handles the initial trigger. Note the function signature, parameters, and first operation.

3. **Follow the call chain step by step.** For each function call:
   - Note the file and line number
   - What data is passed in
   - What transformation occurs
   - What is returned or emitted

4. **Track data transformations.** Document how the input data changes shape as it moves through layers:
   ```
   Step 1: Raw HTTP JSON body → Pydantic model (models.py:ChatRequest)
   Step 2: ChatRequest.messages → build_prompt() → formatted prompt string
   Step 3: Prompt → backend.run_agent() → streamed response chunks
   Step 4: Chunks → SSE format → HTTP streaming response
   ```

5. **Identify branching points.** Note where the flow splits based on conditions: if/else, match statements, feature flags, error handling paths.

6. **Map external interactions.** Flag every point where the code interacts with external systems: database queries, HTTP calls, file I/O, message queues, subprocess calls.

7. **Document the return path.** Trace how the response flows back to the caller, including error handling and cleanup.

8. **Present the complete trace** as a numbered sequence with file:line references. Include the happy path first, then note error paths as branches.
