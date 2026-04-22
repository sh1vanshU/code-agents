---
name: git-history
description: Git history analysis — blame, bisect, churn, contributor stats, timelines
---

## Before You Start

- Confirm the scope: specific file, directory, branch, or entire repo.
- Ensure the repo is fetched so history is complete.
- For bisect, identify a known good commit and a known bad commit (or symptoms to test).

## Workflow

### Blame — Who Last Changed Each Line

1. **Run git blame on the target file.**
   ```bash
   curl -sS "${CODE_AGENTS_PUBLIC_BASE_URL}/git/log?branch=main&limit=1"
   ```
   Then use bash to run blame directly:
   ```bash
   cd ${TARGET_REPO_PATH} && git blame --line-porcelain FILE_PATH | head -200
   ```

2. **Summarize blame results:** group lines by author, show which sections each person owns.

### Bisect — Find the Bug-Introducing Commit

3. **Start bisect** with known good and bad commits.
   ```bash
   cd ${TARGET_REPO_PATH} && git bisect start BAD_COMMIT GOOD_COMMIT
   ```

4. **At each bisect step**, run the test or check that reproduces the bug.
   ```bash
   cd ${TARGET_REPO_PATH} && git bisect good   # or: git bisect bad
   ```

5. **Report the first bad commit** when bisect completes. Show the commit message, author, date, and changed files.

6. **Reset bisect** when done.
   ```bash
   cd ${TARGET_REPO_PATH} && git bisect reset
   ```

### Commit Frequency Analysis

7. **Most active files** — files with the most commits (refactoring candidates).
   ```bash
   cd ${TARGET_REPO_PATH} && git log --pretty=format: --name-only | sort | uniq -c | sort -rn | head -20
   ```

8. **Most active authors** — commits per person.
   ```bash
   cd ${TARGET_REPO_PATH} && git shortlog -sn --all | head -20
   ```

### File Churn Detection

9. **Files changed most often** in the last N commits or time period.
   ```bash
   cd ${TARGET_REPO_PATH} && git log --since="3 months ago" --pretty=format: --name-only | sort | uniq -c | sort -rn | head -20
   ```

10. **High churn + high complexity** = refactoring candidates. Flag files that appear in both "most changed" and "largest" lists.

### Contributor Stats

11. **Lines added/removed per author.**
    ```bash
    cd ${TARGET_REPO_PATH} && git log --all --numstat --pretty="%aN" | awk 'NF==1{author=$0} NF==3{added[author]+=$1; removed[author]+=$2} END{for(a in added) print added[a], removed[a], a}' | sort -rn | head -20
    ```

### Timeline

12. **When were key files last modified?**
    ```bash
    cd ${TARGET_REPO_PATH} && for f in FILE1 FILE2 FILE3; do echo "$f: $(git log -1 --format='%ai %s' -- $f)"; done
    ```

13. **Present a summary report** with the requested analysis sections, formatted as a table.

## Definition of Done

- Requested analysis completed (blame, bisect, churn, stats, or timeline).
- Results presented in a clear, tabular format.
- Actionable insights highlighted (refactoring candidates, key contributors, bug-introducing commit).
- Bisect reset if it was started.
