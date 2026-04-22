"""CLI misc tools and utilities — onboard, watchdog, pre-push, changelog, version, update, curls, rules, migrate, repos, sessions, doctor."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from .cli_helpers import (
    _colors, _server_url, _api_get, _api_post, _load_env,
    _user_cwd, _find_code_agents_home, prompt_yes_no,
)

logger = logging.getLogger("code_agents.cli.cli_tools")


def cmd_rules(rest: list[str] | None = None):
    """Manage rules files (list, create, edit, delete)."""
    import subprocess as _sp
    rest = rest or []
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    cwd = _user_cwd()

    subcmd = rest[0] if rest else "list"

    if subcmd == "list":
        agent_name = None
        for i, arg in enumerate(rest):
            if arg == "--agent" and i + 1 < len(rest):
                agent_name = rest[i + 1]

        from code_agents.agent_system.rules_loader import list_rules
        rules = list_rules(agent_name=agent_name, repo_path=cwd)
        print()
        if not rules:
            print(dim("  No rules found."))
            print()
            print(f"  Create one:")
            print(f"    code-agents rules create                  {dim('# project rule, all agents')}")
            print(f"    code-agents rules create --agent code-writer  {dim('# project rule, specific agent')}")
            print(f"    code-agents rules create --global         {dim('# global rule, all agents')}")
        else:
            print(bold("  Active Rules:"))
            print()
            for r in rules:
                scope_label = green("global") if r["scope"] == "global" else cyan("project")
                target_label = "all agents" if r["target"] == "_global" else r["target"]
                print(f"    [{scope_label}] {bold(target_label)}")
                print(f"      {dim(r['preview'])}")
                print(f"      {dim(r['path'])}")
                print()
        print()

    elif subcmd == "create":
        is_global = "--global" in rest
        agent_name = None
        for i, arg in enumerate(rest):
            if arg == "--agent" and i + 1 < len(rest):
                agent_name = rest[i + 1]

        if is_global:
            from code_agents.agent_system.rules_loader import GLOBAL_RULES_DIR
            rules_dir = GLOBAL_RULES_DIR
        else:
            rules_dir = Path(cwd) / ".code-agents" / "rules"

        filename = f"{agent_name}.md" if agent_name else "_global.md"
        filepath = rules_dir / filename

        rules_dir.mkdir(parents=True, exist_ok=True)
        if not filepath.exists():
            target_desc = agent_name or "all agents"
            scope_desc = "global" if is_global else "project"
            filepath.write_text(
                f"# Rules for {target_desc} ({scope_desc})\n\n"
                f"<!-- Write your rules below. These will be injected into the agent's system prompt. -->\n\n"
            )
            print(green(f"  \u2713 Created: {filepath}"))
        else:
            print(dim(f"  File exists: {filepath}"))

        editor = os.environ.get("EDITOR", "vi")
        print(dim(f"  Opening in {editor}..."))
        _sp.run([editor, str(filepath)])

    elif subcmd == "edit":
        if len(rest) < 2:
            print(yellow("  Usage: code-agents rules edit <path>"))
            return
        filepath = rest[1]
        if not os.path.isfile(filepath):
            print(red(f"  File not found: {filepath}"))
            return
        editor = os.environ.get("EDITOR", "vi")
        _sp.run([editor, filepath])

    elif subcmd == "delete":
        if len(rest) < 2:
            print(yellow("  Usage: code-agents rules delete <path>"))
            return
        filepath = rest[1]
        if not os.path.isfile(filepath):
            print(red(f"  File not found: {filepath}"))
            return
        try:
            answer = input(f"  Delete {filepath}? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if answer in ("y", "yes"):
            os.remove(filepath)
            print(green(f"  \u2713 Deleted: {filepath}"))
        else:
            print(dim("  Cancelled."))

    else:
        print(yellow(f"  Unknown subcommand: {subcmd}"))
        print(f"  Usage: code-agents rules [list|create|edit|delete]")


def cmd_migrate():
    """Migrate legacy .env to centralized config."""
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    cwd = _user_cwd()

    legacy = os.path.join(cwd, ".env")
    if not os.path.isfile(legacy):
        print()
        print(dim("  No legacy .env file found \u2014 nothing to migrate."))
        print()
        return

    from code_agents.setup.setup import parse_env_file
    from code_agents.core.env_loader import GLOBAL_ENV_PATH, PER_REPO_FILENAME, split_vars

    env_vars = parse_env_file(Path(legacy))
    if not env_vars:
        print()
        print(dim("  Legacy .env is empty \u2014 nothing to migrate."))
        print()
        return

    global_vars, repo_vars = split_vars(env_vars)

    print()
    print(bold("  Migrating .env to centralized config"))
    print()
    print(f"    Source:        {legacy} ({len(env_vars)} variables)")
    print(f"    Global config: {GLOBAL_ENV_PATH} ({len(global_vars)} variables)")
    print(f"    Repo config:   {os.path.join(cwd, PER_REPO_FILENAME)} ({len(repo_vars)} variables)")
    print()

    if global_vars:
        print(f"  {bold('Global')} (API keys, server, integrations):")
        for k in sorted(global_vars):
            print(f"    {dim(k)}")
        print()
    if repo_vars:
        print(f"  {bold('Per-repo')} (Jenkins, ArgoCD, testing):")
        for k in sorted(repo_vars):
            print(f"    {dim(k)}")
        print()

    try:
        answer = input(f"  Proceed with migration? [Y/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if answer not in ("", "y", "yes"):
        print(dim("  Cancelled."))
        return

    from code_agents.setup.setup import _write_env_to_path

    if global_vars:
        # Merge with existing global config
        existing_global = parse_env_file(GLOBAL_ENV_PATH) if GLOBAL_ENV_PATH.is_file() else {}
        merged_global = dict(existing_global)
        for k, v in global_vars.items():
            merged_global[k] = v
        GLOBAL_ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
        _write_env_to_path(GLOBAL_ENV_PATH, merged_global, "global config")

    if repo_vars:
        repo_path = Path(os.path.join(cwd, PER_REPO_FILENAME))
        existing_repo = parse_env_file(repo_path) if repo_path.is_file() else {}
        merged_repo = dict(existing_repo)
        for k, v in repo_vars.items():
            merged_repo[k] = v
        _write_env_to_path(repo_path, merged_repo, "repo config")

    # Backup legacy .env
    import datetime
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = f"{legacy}.backup.{ts}"
    import shutil
    shutil.move(legacy, backup)
    print(green(f"  \u2713 Legacy .env moved to: {backup}"))
    print()
    print(green(bold("  Migration complete!")))
    print()


def cmd_repos(args: list[str] | None = None):
    """List and manage registered repos for multi-repo support.

    Usage:
      code-agents repos               # list registered repos
      code-agents repos add <path>     # register a repo
      code-agents repos remove <name>  # unregister a repo
    """
    bold, green, yellow, red, cyan, dim = _colors()
    from code_agents.domain.repo_manager import get_repo_manager

    args = args or []
    rm = get_repo_manager()

    # Register current cwd if no repos yet
    cwd = _user_cwd()
    if not rm.repos:
        try:
            rm.add_repo(cwd)
        except ValueError:
            pass

    sub = args[0] if args else "list"

    if sub == "add":
        if len(args) < 2:
            print(yellow("  Usage: code-agents repos add <path>"))
            return
        add_path = os.path.expanduser(args[1].strip())
        try:
            ctx = rm.add_repo(add_path)
            print()
            print(green(f"  + Registered: {bold(ctx.name)}"))
            print(f"    Path:   {dim(ctx.path)}")
            print(f"    Branch: {dim(ctx.git_branch or 'unknown')}")
            print()
        except ValueError as e:
            print(red(f"  {e}"))
        return

    if sub == "remove":
        if len(args) < 2:
            print(yellow("  Usage: code-agents repos remove <name>"))
            return
        remove_name = args[1].strip()
        try:
            removed = rm.remove_repo(remove_name)
            if removed:
                print(green(f"  - Removed: {remove_name}"))
            else:
                print(yellow(f"  Repo '{remove_name}' not found."))
        except ValueError as e:
            print(red(f"  {e}"))
        return

    # Default: list repos
    repos = rm.list_repos()
    print()
    if not repos:
        print(dim("  No repos registered."))
        print(dim("  Use 'code-agents repos add <path>' to register one."))
    else:
        print(bold("  Registered repos:"))
        for ctx in repos:
            is_active = ctx.path == rm.active_repo
            marker = f" {green('< active')}" if is_active else ""
            branch_info = f" [{dim(ctx.git_branch)}]" if ctx.git_branch else ""
            print(f"    {cyan(ctx.name):<28}{branch_info}{marker}")
            print(f"      {dim(ctx.path)}")
        print()
        print(f"  Total: {bold(str(len(repos)))} repos")
    print()


def cmd_sessions(args: list[str] | None = None):
    """List and manage saved chat sessions."""
    bold, green, yellow, red, cyan, dim = _colors()
    from datetime import datetime
    from code_agents.chat.chat_history import list_sessions, delete_session

    args = args or []
    cwd = _user_cwd()

    # Sub-commands: list (default), delete <N>, clear
    sub = args[0] if args else "list"

    if sub == "clear":
        from code_agents.chat.chat_history import HISTORY_DIR
        import shutil
        if HISTORY_DIR.exists():
            count = len(list(HISTORY_DIR.glob("*.json")))
            if count == 0:
                print(dim("  No sessions to clear."))
                return
            print(f"  This will delete {bold(str(count))} saved chat sessions.")
            try:
                answer = input("  Are you sure? [y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if answer in ("y", "yes"):
                shutil.rmtree(HISTORY_DIR)
                HISTORY_DIR.mkdir(parents=True, exist_ok=True)
                print(green(f"  \u2713 Cleared {count} sessions."))
            else:
                print(dim("  Cancelled."))
        else:
            print(dim("  No sessions to clear."))
        return

    if sub == "cleanup":
        from code_agents.chat.chat_history import cleanup_sessions
        # Parse optional flags
        days = 30  # default
        max_count = 100  # default
        for a in args[1:]:
            if a.startswith("--days="):
                days = int(a.split("=")[1])
            elif a.startswith("--max="):
                max_count = int(a.split("=")[1])
        result = cleanup_sessions(max_age_days=days, max_count=max_count)
        total = result["deleted_age"] + result["deleted_count"]
        if total > 0:
            print(green(f"  ✓ Cleaned up {total} sessions ({result['deleted_age']} expired, {result['deleted_count']} excess)"))
            print(dim(f"    {result['remaining']} sessions remaining"))
        else:
            print(dim(f"  No sessions to clean up ({result['remaining']} within limits)"))
        return

    if sub == "delete":
        if len(args) < 2:
            print(yellow("  Usage: code-agents sessions delete <session-id>"))
            return
        sid = args[1].strip()
        if delete_session(sid):
            print(green(f"  \u2713 Deleted session: {sid}"))
        else:
            print(red(f"  Session '{sid}' not found."))
            print(dim("  Use 'code-agents sessions' to see session IDs."))
        return

    # Default: list sessions
    show_all = "--all" in args
    repo_path = None if show_all else cwd
    # Find git root
    if not show_all:
        check_dir = cwd
        while True:
            if os.path.isdir(os.path.join(check_dir, ".git")):
                repo_path = check_dir
                break
            parent = os.path.dirname(check_dir)
            if parent == check_dir:
                repo_path = cwd
                break
            check_dir = parent

    sessions = list_sessions(limit=20, repo_path=repo_path)

    print()
    if not sessions:
        print(dim("  No saved chat sessions."))
        if not show_all:
            print(dim("  Use --all to show sessions from all repos."))
        print()
        return

    print(bold("  Saved chat sessions:"))
    print()
    for i, s in enumerate(sessions, 1):
        ts = datetime.fromtimestamp(s["updated_at"]).strftime("%b %d %H:%M")
        agent_label = cyan(s["agent"])
        msg_count = s["message_count"]
        title = s["title"]
        repo_name = os.path.basename(s.get("repo_path", ""))
        sid = s["id"]
        print(f"    {cyan(sid)}")
        print(f"      {title}")
        print(f"      {agent_label}  {dim(f'{msg_count} msgs')}  {dim(ts)}  {dim(repo_name)}")
    print()
    print(f"  {dim('Resume:  code-agents chat --resume <session-id>')}")
    print(f"  {dim('Delete:  code-agents sessions delete <session-id>')}")
    print(f"  {dim('Clear:   code-agents sessions clear')}")
    if not show_all:
        print(f"  {dim('All:     code-agents sessions --all')}")
    print()


def cmd_update():
    """Update code-agents to the latest version from git."""
    import subprocess as _sp
    bold, green, yellow, red, cyan, dim = _colors()

    home = _find_code_agents_home()
    print()
    print(bold(cyan("  Updating Code Agents...")))
    print(f"  Install dir: {dim(str(home))}")
    print()

    # Check if it's a git repo
    if not (home / ".git").is_dir():
        print(red("  \u2717 Not a git repository \u2014 cannot update."))
        print(dim(f"    Re-install: curl -fsSL https://github.com/code-agents-org/code-agents/raw/main/install.sh | bash"))
        return

    # Save current commit
    old_commit = _sp.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=str(home), capture_output=True, text=True,
    ).stdout.strip()

    # Check current branch
    current_branch = _sp.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=str(home), capture_output=True, text=True,
    ).stdout.strip() or "main"

    # Check remote URL and fix SSH -> HTTPS if SSH fails
    remote_url = _sp.run(
        ["git", "remote", "get-url", "origin"],
        cwd=str(home), capture_output=True, text=True,
    ).stdout.strip()
    print(f"  Remote: {dim(remote_url)}")
    print(f"  Branch: {dim(current_branch)}")
    print()

    # Pull latest via SSH (retry once on transient failure)
    print(dim("  Pulling latest changes..."))
    pull = _sp.run(
        ["git", "pull", "origin", current_branch],
        cwd=str(home), capture_output=True, text=True,
        stdin=_sp.DEVNULL,  # prevent auth prompts from blocking
        timeout=120,
    )

    # Retry once on transient SSH errors (connection reset, timeout)
    if pull.returncode != 0:
        err_text = (pull.stderr or pull.stdout or "").lower()
        transient_errors = ["connection reset", "kex_exchange", "connection timed out"]
        if any(e in err_text for e in transient_errors):
            print(yellow("  ! Transient SSH error — retrying..."))
            pull = _sp.run(
                ["git", "pull", "origin", current_branch],
                cwd=str(home), capture_output=True, text=True,
                stdin=_sp.DEVNULL, timeout=120,
            )

    if pull.returncode != 0:
        print(red(f"  \u2717 git pull failed:"))
        for line in (pull.stderr or pull.stdout).splitlines()[:5]:
            print(f"    {line}")
        print()
        print(dim("  Possible fixes:"))
        print(dim("    1. Check VPN connection"))
        print(dim("    2. Check SSH key: ssh -T git@bitbucket.org"))
        print(dim("    3. Re-install: curl -fsSL https://github.com/code-agents-org/code-agents/raw/main/install.sh | bash"))
        print()
        return

    new_commit = _sp.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=str(home), capture_output=True, text=True,
    ).stdout.strip()

    if old_commit == new_commit:
        print(green("  \u2713 Already up to date."))
        print()
        return

    # Show what changed
    changed = _sp.run(
        ["git", "diff", "--stat", f"{old_commit}..{new_commit}"],
        cwd=str(home), capture_output=True, text=True,
    ).stdout.strip()
    commits = _sp.run(
        ["git", "log", "--oneline", f"{old_commit}..{new_commit}"],
        cwd=str(home), capture_output=True, text=True,
    ).stdout.strip()

    if commits:
        print(bold("  New commits:"))
        for line in commits.splitlines():
            print(f"    {dim(line)}")
        print()

    if changed:
        lines = changed.splitlines()
        # Show each file with +/- stats
        print(bold("  Changed files:"))
        for line in lines[:-1]:  # skip summary line
            # Format: "path/to/file.py | 12 +++---"
            stripped = line.strip()
            if not stripped:
                continue
            # Color the +/- indicators
            colored = stripped
            colored = colored.replace("+", f"{green('+')}")
            colored = colored.replace("-", f"{red('-')}")
            print(f"    {colored}")
        # Show summary line (e.g., "8 files changed, 26 insertions(+), 32 deletions(-)")
        if lines:
            summary = lines[-1].strip()
            print(f"\n  {bold(summary)}")
        print()

    # Reinstall dependencies
    print(dim("  Installing dependencies..."))
    install = _sp.run(
        ["poetry", "install", "--quiet"],
        cwd=str(home), capture_output=True, text=True,
    )
    if install.returncode != 0:
        print(yellow(f"  ! poetry install had issues:"))
        for line in install.stderr.splitlines()[:5]:
            print(f"    {line}")
    else:
        print(green("  \u2713 Dependencies updated."))

    # Update TS terminal dependencies (if terminal exists)
    _ts_dir = home / "terminal"
    if (_ts_dir / "package.json").is_file():
        print(dim("  Updating TS terminal dependencies..."))
        npm_install = _sp.run(
            ["npm", "ci", "--quiet"],
            cwd=str(_ts_dir), capture_output=True, text=True,
        )
        if npm_install.returncode == 0:
            print(green("  ✓ TS terminal dependencies updated."))
        else:
            print(yellow("  ! npm ci had issues (chat will auto-install on first use)"))

    # Refresh shell tab-completions
    print(dim("  Refreshing shell completions..."))
    try:
        from code_agents.cli.cli_completions import _generate_zsh_completion, _generate_bash_completion
        import os as _os
        shell_rc = _os.path.expanduser("~/.zshrc") if _os.path.isfile(_os.path.expanduser("~/.zshrc")) else _os.path.expanduser("~/.bashrc")
        if _os.path.isfile(shell_rc):
            content = open(shell_rc).read()
            if "# code-agents completion" in content:
                # Remove old block
                import re as _re
                if ".zshrc" in shell_rc:
                    content = _re.sub(r'# code-agents completion.*?compdef _code_agents code-agents\n?', '', content, flags=_re.DOTALL)
                else:
                    content = _re.sub(r'# code-agents completion.*?complete -F _code_agents_completions code-agents\n?', '', content, flags=_re.DOTALL)
                open(shell_rc, 'w').write(content)
            # Append new
            comp = _generate_zsh_completion() if ".zshrc" in shell_rc else _generate_bash_completion()
            with open(shell_rc, 'a') as f:
                f.write(comp)
            print(green("  \u2713 Shell completions refreshed."))
    except Exception:
        print(dim("  Shell completions: run 'code-agents completions --install' to refresh"))

    print()
    print(green(bold(f"  \u2713 Updated: {old_commit} \u2192 {new_commit}")))
    print()
    _restart_cmd = "code-agents restart"
    print(dim(f"  Restart the server to apply: {bold(_restart_cmd)}"))
    try:
        import subprocess as _cp
        _cp.run(["pbcopy"], input=_restart_cmd.encode(), capture_output=True, timeout=2)
        print(dim("  (copied to clipboard \u2014 just paste and run)"))
    except Exception:
        pass
    print()


def cmd_version():
    """Show version info."""
    bold, green, _, _, cyan, dim = _colors()
    from code_agents.__version__ import __version__ as version

    print()
    print(f"  code-agents {bold(version)}")
    print(f"  Python {sys.version.split()[0]}")
    print(f"  Install: {dim(str(_find_code_agents_home()))}")
    print()


def cmd_version_bump(args: list[str] | None = None):
    """Bump version: major, minor, or patch."""
    bold, green, yellow, red, cyan, dim = _colors()
    from code_agents.__version__ import __version__ as current

    args = args or []
    if not args or args[0] not in ("major", "minor", "patch"):
        print()
        print(f"  Current version: {bold(current)}")
        print()
        print(f"  Usage: code-agents version-bump <major|minor|patch>")
        print()
        print(f"    {cyan('patch')}  {dim('0.2.0 \u2192 0.2.1  (bug fixes)')}")
        print(f"    {cyan('minor')}  {dim('0.2.0 \u2192 0.3.0  (new features)')}")
        print(f"    {cyan('major')}  {dim('0.2.0 \u2192 1.0.0  (breaking changes)')}")
        print()
        return

    bump_type = args[0]
    parts = current.split(".")
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])

    if bump_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump_type == "minor":
        minor += 1
        patch = 0
    elif bump_type == "patch":
        patch += 1

    new_version = f"{major}.{minor}.{patch}"

    # Update __version__.py
    version_file = Path(__file__).resolve().parent.parent / "__version__.py"
    version_file.write_text(f'"""Single source of truth for code-agents version."""\n\n__version__ = "{new_version}"\n')

    # Update pyproject.toml
    pyproject = Path(__file__).resolve().parent.parent.parent / "pyproject.toml"
    if pyproject.is_file():
        content = pyproject.read_text()
        content = content.replace(f'version = "{current}"', f'version = "{new_version}"')
        pyproject.write_text(content)

    print()
    print(f"  {green('\u2713')} Version bumped: {dim(current)} \u2192 {bold(green(new_version))}")
    print()
    print(f"  Updated:")
    print(f"    {dim(str(version_file))}")
    print(f"    {dim(str(pyproject))}")
    print()
    print(f"  Next steps:")
    print(f"    1. Update CHANGELOG.md with changes under [{new_version}]")
    print(f"    2. git add -A && git commit -m 'chore: bump version to {new_version}'")
    print(f"    3. git tag v{new_version}")
    print()


from .cli_curls import cmd_curls, _print_curl_sections, _curls_for_agent  # noqa: F401


def cmd_onboard(rest: list[str] | None = None):
    """Generate onboarding guide for new developers.

    Usage:
      code-agents onboard              # show in terminal
      code-agents onboard --save       # save as ONBOARDING.md
      code-agents onboard --full       # full markdown doc in terminal
    """
    from code_agents.tools.onboarding import OnboardingGenerator, generate_onboarding_doc, format_onboarding_terminal

    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    rest = rest or []
    cwd = _user_cwd()

    print()
    print(bold(cyan("  Onboarding Guide Generator")))
    print(dim(f"  Scanning {cwd}..."))
    print()

    generator = OnboardingGenerator(cwd=cwd)
    profile = generator.scan()

    if "--full" in rest:
        # Full markdown to stdout
        print(generate_onboarding_doc(profile))
    elif "--save" in rest:
        # Save to ONBOARDING.md
        doc = generate_onboarding_doc(profile)
        out_path = os.path.join(cwd, "ONBOARDING.md")
        with open(out_path, "w") as f:
            f.write(doc)
        print(green(f"  Saved to {out_path}"))
        print()
    else:
        # Terminal summary
        print(format_onboarding_terminal(profile))
        print()
        print(dim(f"  Tip: code-agents onboard --save   to save as ONBOARDING.md"))
        print(dim(f"       code-agents onboard --full   for full markdown output"))
        print()


def cmd_watchdog(rest: list[str] | None = None):
    """Post-deploy watchdog — monitor error rate, alert on spikes.

    Usage:
      code-agents watchdog                 # 15 minute watch
      code-agents watchdog --minutes 30    # custom duration
    """
    from code_agents.tools.watchdog import PostDeployWatchdog, format_watchdog_report

    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    rest = rest or []

    minutes = 15
    if "--minutes" in rest:
        idx = rest.index("--minutes")
        if idx + 1 < len(rest):
            try:
                minutes = int(rest[idx + 1])
            except ValueError:
                pass

    print()
    print(bold(cyan("  Post-Deploy Watchdog")))
    print(dim(f"  Monitoring for {minutes} minutes..."))
    print()

    wd = PostDeployWatchdog(duration_minutes=minutes)
    report = wd.run()
    print(format_watchdog_report(report))


def cmd_pre_push(rest: list[str] | None = None):
    """Pre-push checklist — tests, secrets, TODOs, lint.

    Usage:
      code-agents pre-push-check           # run checks
      code-agents pre-push install         # install git hook
    """
    from code_agents.tools.pre_push import PrePushChecklist, format_pre_push_report

    bold, green, yellow, red, cyan, dim = _colors()
    rest = rest or []

    cwd = os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()

    if rest and rest[0] == "install":
        result = PrePushChecklist.install_hook(cwd)
        print()
        print(green(f"  {result}"))
        print()
        return

    print()
    print(bold(cyan("  Pre-Push Checklist")))
    print(dim("  Running checks..."))
    print()

    checklist = PrePushChecklist(cwd=cwd)
    report = checklist.run_checks()
    print(format_pre_push_report(report))

    # Exit with non-zero if any check failed (for git hook)
    if not report.all_passed:
        sys.exit(1)


def cmd_changelog(rest: list[str] | None = None):
    """Generate changelog from conventional commits.

    Usage:
      code-agents changelog                  # preview changelog
      code-agents changelog --write          # prepend to CHANGELOG.md
      code-agents changelog --version 1.0.0  # set version
    """
    from code_agents.generators.changelog_gen import ChangelogGenerator, format_changelog_terminal

    bold, green, yellow, red, cyan, dim = _colors()
    rest = rest or []

    cwd = os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()
    write = "--write" in rest
    version = None
    if "--version" in rest:
        idx = rest.index("--version")
        if idx + 1 < len(rest):
            version = rest[idx + 1]

    print()
    print(bold(cyan("  Changelog Generator")))
    print()

    gen = ChangelogGenerator(cwd=cwd, version=version)
    data = gen.generate()

    print(format_changelog_terminal(data))

    if write:
        path = gen.prepend_to_changelog(data)
        print(green(f"  Changelog written to: {path}"))

    print()
