"""CLI handlers for productivity features."""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_productivity")


def _user_cwd() -> str:
    return os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()


def cmd_pr_describe(rest: list[str] | None = None):
    """Generate PR description from branch diff.

    Usage:
      code-agents pr-describe                  # default (base=main, format=md)
      code-agents pr-describe --base develop   # custom base branch
      code-agents pr-describe --format json    # JSON output
      code-agents pr-describe --no-reviewers   # skip reviewer suggestions
    """
    from .cli_helpers import _colors, _load_env
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    rest = rest or []
    base = "main"
    fmt = "md"
    include_reviewers = True
    include_risk = True

    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--base" and i + 1 < len(rest):
            base = rest[i + 1]; i += 2; continue
        elif a == "--format" and i + 1 < len(rest):
            fmt = rest[i + 1]; i += 2; continue
        elif a == "--no-reviewers":
            include_reviewers = False
        elif a == "--no-risk":
            include_risk = False
        i += 1

    cwd = _user_cwd()
    from code_agents.git_ops.pr_describe import PRDescriptionGenerator, format_pr_description

    print(f"\n  {bold('PR Description Generator')}")
    print(f"  {dim(f'Base: {base} | Format: {fmt}')}\n")

    gen = PRDescriptionGenerator(
        cwd=cwd, base=base,
        include_reviewers=include_reviewers, include_risk=include_risk,
    )
    desc = gen.generate()
    print(format_pr_description(desc, fmt))


def cmd_postmortem(rest: list[str] | None = None):
    """Generate incident postmortem from time range.

    Usage:
      code-agents postmortem --from "2026-04-08 14:00" --to "2026-04-08 16:00"
      code-agents postmortem --from "2h ago" --service api-gateway
      code-agents postmortem --format json
    """
    from .cli_helpers import _colors, _load_env
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    rest = rest or []
    time_from = ""
    time_to = ""
    service = ""
    fmt = "md"

    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--from" and i + 1 < len(rest):
            time_from = rest[i + 1]; i += 2; continue
        elif a == "--to" and i + 1 < len(rest):
            time_to = rest[i + 1]; i += 2; continue
        elif a == "--service" and i + 1 < len(rest):
            service = rest[i + 1]; i += 2; continue
        elif a == "--format" and i + 1 < len(rest):
            fmt = rest[i + 1]; i += 2; continue
        i += 1

    cwd = _user_cwd()
    from code_agents.domain.postmortem import PostmortemWriter, format_postmortem

    print(f"\n  {bold('Incident Postmortem Writer')}")
    print(f"  {dim(f'From: {time_from or 'auto'} | To: {time_to or 'now'} | Service: {service or 'all'}')}\n")

    writer = PostmortemWriter(cwd=cwd, time_from=time_from, time_to=time_to, service=service)
    report = writer.generate()
    print(format_postmortem(report, fmt))


def cmd_dep_upgrade(rest: list[str] | None = None):
    """Scan and upgrade outdated dependencies.

    Usage:
      code-agents dep-upgrade                  # scan only (dry run)
      code-agents dep-upgrade --package requests  # upgrade one package
      code-agents dep-upgrade --all --execute  # upgrade all, for real
    """
    from .cli_helpers import _colors, _load_env
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    rest = rest or []
    package = ""
    all_pkgs = False
    dry_run = True

    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--package" and i + 1 < len(rest):
            package = rest[i + 1]; i += 2; continue
        elif a == "--all":
            all_pkgs = True
        elif a == "--execute":
            dry_run = False
        i += 1

    cwd = _user_cwd()
    from code_agents.domain.dep_upgrade import DependencyUpgradePilot, format_upgrade_report

    print(f"\n  {bold('Dependency Upgrade Pilot')}")
    print(f"  {dim(f'Mode: {'scan only' if dry_run else 'execute'} | Package: {package or 'all'}')}\n")

    pilot = DependencyUpgradePilot(cwd=cwd, dry_run=dry_run)

    if not package and not all_pkgs and dry_run:
        candidates = pilot.scan()
        from code_agents.domain.dep_upgrade import UpgradeReport
        report = UpgradeReport(repo_path=cwd, package_manager=pilot.package_manager, candidates=candidates)
        print(format_upgrade_report(report))
    else:
        report = pilot.upgrade(package=package, all_packages=all_pkgs)
        print(format_upgrade_report(report))


def cmd_review_buddy(rest: list[str] | None = None):
    """Pre-push code review against conventions.

    Usage:
      code-agents review-buddy              # review staged changes
      code-agents review-buddy --all        # review all changes
      code-agents review-buddy --fix        # auto-fix where possible
    """
    from .cli_helpers import _colors, _load_env
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    rest = rest or []
    staged_only = True
    auto_fix = False

    for a in rest:
        if a == "--all":
            staged_only = False
        elif a == "--fix":
            auto_fix = True

    cwd = _user_cwd()
    from code_agents.reviews.review_buddy import ReviewBuddy, format_review

    print(f"\n  {bold('Code Review Buddy')}")
    print(f"  {dim(f'Scope: {'staged' if staged_only else 'all changes'} | Auto-fix: {auto_fix}')}\n")

    buddy = ReviewBuddy(cwd=cwd, staged_only=staged_only, auto_fix=auto_fix)
    report = buddy.check()
    print(format_review(report))


def cmd_db_migrate(rest: list[str] | None = None):
    """Generate DB migration from description.

    Usage:
      code-agents db-migrate "add expires_at to sessions"
      code-agents db-migrate "create table payments" --type alembic
      code-agents db-migrate "drop column temp_flag from users" --preview
    """
    from .cli_helpers import _colors, _load_env
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    rest = rest or []
    description = ""
    migration_type = "auto"
    preview = True

    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--type" and i + 1 < len(rest):
            migration_type = rest[i + 1]; i += 2; continue
        elif a == "--execute":
            preview = False
        elif a == "--preview":
            preview = True
        elif not a.startswith("--"):
            description = a
        i += 1

    if not description:
        print(f"  {red('Usage: code-agents db-migrate \"description\"')}")
        return

    cwd = _user_cwd()
    from code_agents.knowledge.migration_gen import MigrationGenerator, format_migration

    print(f"\n  {bold('Migration Generator')}")
    print(f"  {dim(f'Type: {migration_type} | Preview: {preview}')}\n")

    gen = MigrationGenerator(cwd=cwd, migration_type=migration_type)
    output = gen.generate(description, preview=preview)
    print(format_migration(output))


def cmd_oncall_summary(rest: list[str] | None = None):
    """Summarize on-call alerts and generate standup.

    Usage:
      code-agents oncall-summary                 # last 12 hours
      code-agents oncall-summary --hours 24      # last 24 hours
      code-agents oncall-summary --log /path/to/log
    """
    from .cli_helpers import _colors, _load_env
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    rest = rest or []
    hours = 12
    channel = "oncall"
    log_path = ""

    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--hours" and i + 1 < len(rest):
            hours = int(rest[i + 1]); i += 2; continue
        elif a == "--channel" and i + 1 < len(rest):
            channel = rest[i + 1]; i += 2; continue
        elif a == "--log" and i + 1 < len(rest):
            log_path = rest[i + 1]; i += 2; continue
        i += 1

    cwd = _user_cwd()
    from code_agents.domain.oncall_summary import OncallSummarizer, format_oncall_summary

    print(f"\n  {bold('On-Call Summary')}")
    print(f"  {dim(f'Period: last {hours}h | Channel: {channel}')}\n")

    summarizer = OncallSummarizer(cwd=cwd, hours=hours, channel=channel, log_path=log_path)
    report = summarizer.generate()
    print(format_oncall_summary(report))


def cmd_test_impact(rest: list[str] | None = None):
    """Analyze which tests are impacted by changes.

    Usage:
      code-agents test-impact                # analyze only
      code-agents test-impact --run          # analyze + run impacted tests
      code-agents test-impact --base develop # compare against develop
    """
    from .cli_helpers import _colors, _load_env
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    rest = rest or []
    base = "main"
    run = False

    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--base" and i + 1 < len(rest):
            base = rest[i + 1]; i += 2; continue
        elif a == "--run":
            run = True
        i += 1

    cwd = _user_cwd()
    from code_agents.testing.test_impact import ImpactAnalyzer, format_test_impact

    print(f"\n  {bold('Test Impact Analyzer')}")
    print(f"  {dim(f'Base: {base} | Run: {run}')}\n")

    analyzer = ImpactAnalyzer(cwd=cwd, base=base)
    if run:
        report = analyzer.analyze_and_run()
    else:
        report = analyzer.analyze()
    print(format_test_impact(report))


def cmd_runbook(rest: list[str] | None = None):
    """Execute runbooks with safety gates.

    Usage:
      code-agents runbook --list             # list available runbooks
      code-agents runbook deploy-api         # execute a runbook (dry-run)
      code-agents runbook deploy-api --execute  # execute for real
    """
    from .cli_helpers import _colors, _load_env
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    rest = rest or []
    name = ""
    list_mode = False
    dry_run = True

    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--list":
            list_mode = True
        elif a == "--execute":
            dry_run = False
        elif not a.startswith("--"):
            name = a
        i += 1

    cwd = _user_cwd()
    from code_agents.knowledge.runbook import RunbookExecutor, format_runbook_list, format_execution

    executor = RunbookExecutor(cwd=cwd, dry_run=dry_run)

    if list_mode or not name:
        print(f"\n  {bold('Available Runbooks')}\n")
        runbooks = executor.list_runbooks()
        print(format_runbook_list(runbooks))
    else:
        print(f"\n  {bold('Runbook Executor')}")
        print(f"  {dim(f'Runbook: {name} | Mode: {'dry-run' if dry_run else 'LIVE'}')}\n")
        spec = executor.load(name)
        if not spec:
            print(f"  {red(f'Runbook not found: {name}')}")
            return
        execution = executor.execute(spec)
        print(format_execution(execution))


def cmd_sprint_dashboard(rest: list[str] | None = None):
    """Sprint velocity dashboard with cycle time.

    Usage:
      code-agents sprint-dashboard              # last 14 days
      code-agents sprint-dashboard --days 7     # last 7 days
      code-agents sprint-dashboard --format json
    """
    from .cli_helpers import _colors, _load_env
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    rest = rest or []
    days = 14
    fmt = "md"

    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--days" and i + 1 < len(rest):
            days = int(rest[i + 1]); i += 2; continue
        elif a == "--format" and i + 1 < len(rest):
            fmt = rest[i + 1]; i += 2; continue
        i += 1

    cwd = _user_cwd()
    from code_agents.domain.sprint_dashboard import SprintDashboard, format_sprint_dashboard

    print(f"\n  {bold('Sprint Dashboard')}")
    print(f"  {dim(f'Period: last {days} days')}\n")

    dashboard = SprintDashboard(cwd=cwd, period_days=days)
    report = dashboard.generate()

    if fmt == "json":
        import json
        from dataclasses import asdict
        print(json.dumps(asdict(report), indent=2))
    else:
        print(format_sprint_dashboard(report))


def cmd_explain(rest: list[str] | None = None):
    """Ask questions about the codebase.

    Usage:
      code-agents explain "how does authentication work"
      code-agents explain "where is the database config"
      code-agents explain "what files handle routing"
    """
    from .cli_helpers import _colors, _load_env
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    rest = rest or []
    question = " ".join(rest) if rest else ""

    if not question:
        print(f"  {red('Usage: code-agents explain \"your question here\"')}")
        return

    cwd = _user_cwd()
    from code_agents.knowledge.codebase_qa import CodebaseQA, format_qa_answer

    print(f"\n  {bold('Codebase Q&A')}\n")

    qa = CodebaseQA(cwd=cwd)
    answer = qa.ask(question)
    print(format_qa_answer(answer))
