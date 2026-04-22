"""CLI git and code operations — diff, branches, commit, review, pr-preview, auto-review."""

from __future__ import annotations

import logging
import os
import sys

from .cli_helpers import (
    _colors, _server_url, _api_get, _api_post, _load_env,
    _user_cwd, _find_code_agents_home, prompt_yes_no,
)

logger = logging.getLogger("code_agents.cli.cli_git")


def cmd_diff(args: list[str]):
    """Show git diff between branches."""
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    base = args[0] if len(args) > 0 else "main"
    head = args[1] if len(args) > 1 else "HEAD"

    cwd = _user_cwd()
    data = _api_get(f"/git/diff?base={base}&head={head}&repo_path={cwd}")
    if not data:
        # Fallback: run git directly
        print(dim(f"  Server not running — using git directly"))
        import asyncio
        from code_agents.cicd.git_client import GitClient
        client = GitClient(cwd)
        try:
            data = asyncio.run(client.diff(base, head))
        except Exception as e:
            print(red(f"  Error: {e}"))
            return

    print()
    print(bold(f"  Diff: {cyan(base)} → {cyan(head)}"))
    print(f"  Files changed: {data.get('files_changed', 0)}")
    print(f"  Insertions:    {green('+' + str(data.get('insertions', 0)))}")
    print(f"  Deletions:     {red('-' + str(data.get('deletions', 0)))}")
    print()

    for f in data.get("changed_files", []):
        ins = f.get("insertions", 0)
        dels = f.get("deletions", 0)
        print(f"    {green('+' + str(ins)):<8} {red('-' + str(dels)):<8} {f['file']}")
    print()


def cmd_branches():
    """List git branches."""
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    cwd = _user_cwd()

    data = _api_get(f"/git/branches?repo_path={cwd}")
    if not data:
        import asyncio
        from code_agents.cicd.git_client import GitClient
        client = GitClient(cwd)
        try:
            branches = asyncio.run(client.list_branches())
            data = {"branches": branches}
        except Exception as e:
            print(red(f"  Error: {e}"))
            return

    # Get current branch
    current = None
    cur_data = _api_get(f"/git/current-branch?repo_path={cwd}")
    if cur_data:
        current = cur_data.get("branch")
    else:
        import asyncio
        from code_agents.cicd.git_client import GitClient
        client = GitClient(cwd)
        try:
            current = asyncio.run(client.current_branch())
        except Exception:
            pass

    print()
    print(bold("  Branches:"))
    for b in data.get("branches", []):
        name = b.get("name", "?")
        marker = f" {green('← current')}" if name == current else ""
        print(f"    {cyan(name)}{marker}")
    print()


def cmd_commit():
    """Smart commit — generate conventional commit message from staged diff.

    Usage:
      code-agents commit              # generate and confirm
      code-agents commit --auto       # commit without confirmation
      code-agents commit --dry-run    # show message only
    """
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    cwd = _user_cwd()
    args = sys.argv[2:]

    auto = "--auto" in args
    dry_run = "--dry-run" in args

    from code_agents.tools.smart_commit import SmartCommit

    sc = SmartCommit(cwd=cwd)
    result = sc.generate_message()

    if "error" in result:
        print(red(f"\n  {result['error']}"))
        return

    print()
    print(bold("  Smart Commit"))
    print(bold("  " + "=" * 50))
    print()
    print(f"  Type:   {cyan(result['type'])}")
    if result.get("scope"):
        print(f"  Scope:  {result['scope']}")
    print(f"  Files:  {len(result['files'])}")
    if result.get("ticket"):
        print(f"  Ticket: {green(result['ticket'])}")
    print()
    print(bold("  Message:"))
    for line in result["full_message"].split("\n"):
        print(f"  {line}")
    print()

    if dry_run:
        print(dim("  (dry run — no commit made)"))
        return

    if auto:
        if sc.commit(result["full_message"]):
            print(green("  Committed!"))
        else:
            print(red("  Commit failed"))
        return

    # Interactive: ask to confirm, edit, or cancel
    print(f"  {bold('[Y]')} Commit  {bold('[E]')} Edit message  {bold('[N]')} Cancel")
    try:
        choice = input("  Choice [Y]: ").strip().lower() or "y"
    except (KeyboardInterrupt, EOFError):
        print("\n  Cancelled.")
        return

    if choice == "y":
        if sc.commit(result["full_message"]):
            print(green("  Committed!"))
        else:
            print(red("  Commit failed"))
    elif choice == "e":
        # Let user edit
        print(dim("  Enter new message (empty line to finish):"))
        lines = []
        while True:
            try:
                line = input("  ")
                if line == "":
                    break
                lines.append(line)
            except (KeyboardInterrupt, EOFError):
                break
        if lines:
            custom_msg = "\n".join(lines)
            if sc.commit(custom_msg):
                print(green("  Committed with custom message!"))
            else:
                print(red("  Commit failed"))
        else:
            print(dim("  Cancelled — no message entered."))
    else:
        print(dim("  Cancelled."))


def cmd_review(args: list[str]):
    """Review code changes between branches."""
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    base = args[0] if len(args) > 0 else "main"
    head = args[1] if len(args) > 1 else "HEAD"

    print(bold(f"  Reviewing changes: {base} → {head}"))
    print()

    # Get diff first
    diff_data = _api_get(f"/git/diff?base={base}&head={head}")
    if diff_data:
        print(f"  Files changed: {diff_data.get('files_changed', 0)}")
        print(f"  +{diff_data.get('insertions', 0)} / -{diff_data.get('deletions', 0)}")
        print()

    # Send to code-reviewer agent with repo context
    cwd = _user_cwd()
    repo_name = os.path.basename(cwd)
    diff_text = diff_data.get("diff", "") if diff_data else ""
    prompt = (
        f"You are reviewing code in the project: {repo_name} (at {cwd}).\n"
        f"Review this code diff between {base} and {head}. "
        f"Identify bugs, security issues, and improvements:\n\n{diff_text[:10000]}"
    )

    body = {
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "cwd": cwd,
    }
    print(dim("  Sending to code-reviewer agent..."))
    result = _api_post("/v1/agents/code-reviewer/chat/completions", body)
    if result:
        choices = result.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")
            print()
            print(content)
    else:
        print(yellow("  Could not reach code-reviewer. Is the server running?"))
    print()


def cmd_pr_preview(rest: list[str] | None = None):
    """Preview what a PR would look like before creating it.

    Usage:
      code-agents pr-preview              # diff against main
      code-agents pr-preview develop      # diff against develop
    """
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    cwd = _user_cwd()
    args = rest or []

    base = args[0] if args else "main"

    from code_agents.tools.pr_preview import PRPreview

    preview = PRPreview(cwd=cwd, base=base)

    # Check we have commits
    commits = preview.get_commits()
    if not commits:
        print()
        print(yellow(f"  No commits found ahead of {base}."))
        print(dim(f"  Make sure you're on a feature branch with commits not in {base}."))
        print()
        return

    output = preview.format_preview()
    print()
    print(output)


def cmd_auto_review(rest: list[str] | None = None):
    """Automated code review — diff analysis + AI review.

    Usage:
      code-agents auto-review              # review current branch vs main
      code-agents auto-review develop      # custom base branch
      code-agents auto-review main feature # base and head
    """
    from code_agents.reviews.review_autopilot import ReviewAutopilot, format_review

    bold, green, yellow, red, cyan, dim = _colors()
    rest = rest or []

    cwd = os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()

    base = rest[0] if len(rest) >= 1 else "main"
    head = rest[1] if len(rest) >= 2 else "HEAD"

    print()
    print(bold(cyan("  Code Review Autopilot")))
    print(dim(f"  Reviewing {base}...{head}"))
    print()

    ra = ReviewAutopilot(cwd=cwd, base=base, head=head)
    report = ra.run()
    print(format_review(report))
    print()
