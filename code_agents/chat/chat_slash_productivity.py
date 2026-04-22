"""Slash command handlers for productivity features."""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("code_agents.chat.chat_slash_productivity")


def _handle_productivity(command: str, arg: str, state: dict, url: str) -> Optional[str]:
    """Handle productivity slash commands."""
    try:
        from ..cli.cli_helpers import _colors
        bold, green, yellow, red, cyan, dim = _colors()
    except ImportError:
        bold = green = yellow = red = cyan = dim = lambda x: str(x)

    repo = state.get("repo_path", os.getcwd())

    if command == "/pr-describe":
        from code_agents.git_ops.pr_describe import PRDescriptionGenerator, format_pr_description

        parts = arg.strip().split() if arg.strip() else []
        base = "main"
        fmt = "md"
        for i, p in enumerate(parts):
            if p == "--base" and i + 1 < len(parts):
                base = parts[i + 1]
            elif p == "--format" and i + 1 < len(parts):
                fmt = parts[i + 1]

        gen = PRDescriptionGenerator(cwd=repo, base=base)
        desc = gen.generate()
        print(format_pr_description(desc, fmt))

    elif command == "/postmortem":
        from code_agents.domain.postmortem import PostmortemWriter, format_postmortem

        parts = arg.strip().split() if arg.strip() else []
        time_from = time_to = service = ""
        for i, p in enumerate(parts):
            if p == "--from" and i + 1 < len(parts):
                time_from = parts[i + 1]
            elif p == "--to" and i + 1 < len(parts):
                time_to = parts[i + 1]
            elif p == "--service" and i + 1 < len(parts):
                service = parts[i + 1]

        writer = PostmortemWriter(cwd=repo, time_from=time_from, time_to=time_to, service=service)
        report = writer.generate()
        print(format_postmortem(report))

    elif command in ("/postmortem-gen", "/pm-gen"):
        from code_agents.domain.postmortem_gen import PostmortemGenerator

        parts = arg.strip().split() if arg.strip() else []
        incident_id = time_range = title = ""
        fmt = "markdown"
        idx = 0
        while idx < len(parts):
            p = parts[idx]
            if p == "--incident" and idx + 1 < len(parts):
                incident_id = parts[idx + 1]; idx += 2; continue
            elif p == "--time-range" and idx + 1 < len(parts):
                time_range = parts[idx + 1]; idx += 2; continue
            elif p == "--title" and idx + 1 < len(parts):
                title = parts[idx + 1]; idx += 2; continue
            elif p == "--format" and idx + 1 < len(parts):
                fmt = parts[idx + 1]; idx += 2; continue
            idx += 1

        gen = PostmortemGenerator(cwd=repo)
        pm = gen.generate(incident_id=incident_id, time_range=time_range, title=title)
        if fmt == "terminal":
            print(gen.format_terminal(pm))
        else:
            print(gen.format_markdown(pm))

    elif command == "/dep-upgrade":
        from code_agents.domain.dep_upgrade import DependencyUpgradePilot, format_upgrade_report

        pilot = DependencyUpgradePilot(cwd=repo, dry_run=True)
        candidates = pilot.scan()
        from code_agents.domain.dep_upgrade import UpgradeReport
        report = UpgradeReport(repo_path=repo, package_manager=pilot.package_manager, candidates=candidates)
        print(format_upgrade_report(report))

    elif command == "/review-buddy":
        from code_agents.reviews.review_buddy import ReviewBuddy, format_review

        staged_only = "--all" not in arg
        auto_fix = "--fix" in arg
        buddy = ReviewBuddy(cwd=repo, staged_only=staged_only, auto_fix=auto_fix)
        report = buddy.check()
        print(format_review(report))

    elif command in ("/db-migrate", "/migration"):
        from code_agents.knowledge.migration_gen import MigrationGenerator, format_migration

        desc = arg.strip()
        if not desc or desc.startswith("--"):
            print(f"  {red('Usage: /db-migrate \"add column_name to table_name\"')}")
            return None

        migration_type = "auto"
        if "--type" in desc:
            parts = desc.split("--type")
            desc = parts[0].strip()
            if len(parts) > 1:
                migration_type = parts[1].strip().split()[0]

        gen = MigrationGenerator(cwd=repo, migration_type=migration_type)
        output = gen.generate(desc, preview=True)
        print(format_migration(output))

    elif command == "/oncall-summary":
        from code_agents.domain.oncall_summary import OncallSummarizer, format_oncall_summary

        hours = 12
        if arg.strip().isdigit():
            hours = int(arg.strip())

        summarizer = OncallSummarizer(cwd=repo, hours=hours)
        report = summarizer.generate()
        print(format_oncall_summary(report))

    elif command == "/test-impact":
        from code_agents.testing.test_impact import ImpactAnalyzer, format_test_impact

        run = "--run" in arg
        base = "main"
        parts = arg.strip().split() if arg.strip() else []
        for i, p in enumerate(parts):
            if p == "--base" and i + 1 < len(parts):
                base = parts[i + 1]

        analyzer = ImpactAnalyzer(cwd=repo, base=base)
        if run:
            report = analyzer.analyze_and_run()
        else:
            report = analyzer.analyze()
        print(format_test_impact(report))

    elif command == "/runbook":
        from code_agents.knowledge.runbook import RunbookExecutor, format_runbook_list, format_execution

        name = arg.strip()
        executor = RunbookExecutor(cwd=repo, dry_run=True)

        if not name or name == "--list":
            runbooks = executor.list_runbooks()
            print(format_runbook_list(runbooks))
        else:
            spec = executor.load(name)
            if not spec:
                print(f"  {red(f'Runbook not found: {name}')}")
                return None
            execution = executor.execute(spec)
            print(format_execution(execution))

    elif command == "/sprint-dashboard":
        from code_agents.domain.sprint_dashboard import SprintDashboard, format_sprint_dashboard

        days = 14
        if arg.strip().isdigit():
            days = int(arg.strip())

        dashboard = SprintDashboard(cwd=repo, period_days=days)
        report = dashboard.generate()
        print(format_sprint_dashboard(report))

    elif command == "/explain":
        from code_agents.knowledge.codebase_qa import CodebaseQA, format_qa_answer

        question = arg.strip()
        if not question:
            print(f"  {red('Usage: /explain \"your question about the codebase\"')}")
            return None

        qa = CodebaseQA(cwd=repo)
        answer = qa.ask(question)
        print(format_qa_answer(answer))

    return None
