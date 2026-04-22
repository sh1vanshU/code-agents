---
name: compare
description: Compare two approaches, analyze trade-offs and complexity
---

## Workflow

1. **Understand what is being compared.** Identify the two (or more) approaches: different algorithms, architectures, libraries, patterns, or implementation strategies.

2. **Define evaluation criteria.** Establish the dimensions for comparison:
   - Performance (time complexity, space complexity, latency)
   - Readability and maintainability
   - Testability
   - Error handling robustness
   - Scalability under load
   - Compatibility with existing codebase patterns

3. **Analyze Approach A.** Read the relevant code or design. Document:
   - How it works (brief mechanism)
   - Strengths (what it does well)
   - Weaknesses (where it falls short)
   - Complexity: O(n) time/space analysis where applicable

4. **Analyze Approach B.** Same analysis as above for the alternative approach.

5. **Build a comparison table:**
   ```
   | Criterion       | Approach A          | Approach B          |
   |-----------------|---------------------|---------------------|
   | Time complexity | O(n log n)          | O(n^2)              |
   | Readability     | High — idiomatic    | Medium — clever      |
   | Testability     | Easy — pure funcs   | Hard — side effects  |
   | Maintenance     | Low effort          | High effort          |
   ```

6. **Identify the deciding factor.** What criterion matters most for this specific context? A startup prototype values speed-to-ship; a payment system values correctness and auditability.

7. **Give a clear recommendation** with reasoning. State which approach to use and why, acknowledging the trade-off explicitly.

8. **Note migration cost** if recommending a switch from the current approach: what would need to change, how many files, and what risks exist during the transition.
