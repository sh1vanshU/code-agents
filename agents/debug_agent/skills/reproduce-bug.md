---
name: reproduce-bug
description: Reproduce a reported bug by running the failing test or command
trigger: "[SKILL:reproduce-bug]"
---

# Reproduce Bug

## Steps

1. **Identify the test/command** — Parse the bug report for:
   - Test file + function name (e.g., `tests/test_auth.py::test_login`)
   - Error command (e.g., `npm run build` failing)
   - Error message + traceback

2. **Run the failing test/command** — Execute in the repo directory:
   ```bash
   # Python
   python -m pytest <test_file>::<test_name> -x -v

   # JavaScript
   npx jest <test_file> --verbose

   # Go
   go test -v -run <TestName> ./<package>
   ```

3. **Capture the output** — Save:
   - Full error output (stdout + stderr)
   - Exit code
   - Timing information

4. **Confirm reproduction** — The bug is reproduced if:
   - The test fails with the expected error
   - The error message matches the report
   - The failure is consistent (not flaky)

5. **Report** — State clearly:
   - "Bug reproduced: [error type] at [file:line]"
   - OR "Cannot reproduce: test passes / error differs"
