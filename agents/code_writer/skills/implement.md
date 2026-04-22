---
name: implement
description: Implement a feature from requirements — create files, write code, add tests
---

## Workflow

1. **Read the requirements.** Understand what the feature should do, its inputs, outputs, and edge cases. Ask clarifying questions if the requirements are ambiguous.

2. **Read the existing codebase.** Before writing anything:
   - Understand the project structure and conventions
   - Identify where the new code should live (which directory, module)
   - Find similar existing features to use as a pattern
   - Check for existing utilities or helpers you can reuse

3. **Plan the implementation.** Explain to the user what you will create:
   - New files and their purpose
   - Modified files and what changes
   - Data models or schemas needed
   - API endpoints (if applicable)

4. **Implement the core logic first.** Write the main function or class:
   - Follow existing code style exactly (indentation, naming, imports)
   - Handle errors at system boundaries
   - Keep functions focused — one responsibility per function
   - Add type hints if the project uses them

5. **Wire it into the existing system.** Connect the new code:
   - Add imports where needed
   - Register routes, handlers, or commands
   - Update configuration if needed
   - Add to __init__.py exports if applicable

6. **Write tests for the new code.** Create test file(s) that cover:
   - Happy path
   - Edge cases (empty input, null, boundary values)
   - Error paths
   - Use the project's existing test patterns and framework

7. **Run the tests** to verify everything passes:
   ```bash
   poetry run pytest tests/ -v
   ```

8. **Review your own changes.** Check for:
   - No unnecessary files or changes
   - No debug print statements left behind
   - Consistent style with the rest of the codebase
   - No hardcoded values that should be configurable
