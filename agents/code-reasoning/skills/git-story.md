---
name: git-story
description: Reconstruct the full story behind a line of code — blame, PR, Jira ticket, contributors
tags: [code-understanding, git, history]
---

# Git Story

Answer "why was this code written this way?" by tracing the full history.

## Workflow

1. Git blame the specific line
2. Get line modification history (git log -L)
3. Find associated PR (from merge commit or gh CLI)
4. Extract Jira ticket references from commit messages
5. Build a chronological story with all contributors

## Usage

```
/git-story code_agents/stream.py 42
/git-story code_agents/config.py 15
```

## Output Includes
- Current line content
- Original author and date
- Modification count and all contributors
- PR number and title (if found)
- Jira ticket (if referenced)
- Chronological timeline of all changes
