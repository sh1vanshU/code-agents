"""CLI reporting and team commands — standup, oncall, sprint, incident, morning, env-health, perf-baseline."""

from __future__ import annotations

import logging
import os
import sys

from .cli_helpers import (
    _colors, _server_url, _api_get, _api_post, _load_env,
    _user_cwd, _find_code_agents_home, prompt_yes_no,
)

logger = logging.getLogger("code_agents.cli.cli_reports")


def cmd_standup():
    """Generate AI standup from git activity, Jira tickets, and build status."""
    bold, green, yellow, red, cyan, dim = _colors()

    print()
    print(bold(cyan("  AI Standup Generator")))
    print()

    cwd = os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()
    repo_name = os.path.basename(cwd)

    # Yesterday's git activity
    print(bold("  \U0001f4cb What was done (git log since yesterday):"))
    import subprocess as _sp
    git_log = _sp.run(
        ["git", "log", "--oneline", "--since=yesterday", "--author=" + os.getenv("CODE_AGENTS_NICKNAME", "")],
        cwd=cwd, capture_output=True, text=True, timeout=10,
    )
    if git_log.stdout.strip():
        for line in git_log.stdout.strip().splitlines()[:10]:
            print(f"    {dim('\u2022')} {line}")
    else:
        print(f"    {dim('No commits since yesterday')}")
    print()

    # Today's plan (from Jira — if configured)
    print(bold("  \U0001f3af What's planned (Jira In Progress):"))
    jira_url = os.getenv("JIRA_URL", "")
    if jira_url:
        try:
            import httpx
            base = os.getenv("CODE_AGENTS_PUBLIC_BASE_URL", "http://127.0.0.1:8000")
            r = httpx.get(f"{base}/jira/search", params={"jql": "assignee=currentUser() AND status='In Progress'", "max_results": 5}, timeout=10)
            if r.status_code == 200:
                issues = r.json().get("issues", [])
                for issue in issues[:5]:
                    key = issue.get("key", "")
                    summary = issue.get("fields", {}).get("summary", "")
                    print(f"    {cyan(key)} {summary[:60]}")
                if not issues:
                    print(f"    {dim('No tickets in progress')}")
        except Exception:
            print(f"    {dim('Jira not reachable \u2014 configure with: code-agents init --jira')}")
    else:
        print(f"    {dim('Jira not configured \u2014 run: code-agents init --jira')}")
    print()

    # Build status
    print(bold("  \U0001f528 Build status:"))
    try:
        base = os.getenv("CODE_AGENTS_PUBLIC_BASE_URL", "http://127.0.0.1:8000")
        import httpx
        r = httpx.get(f"{base}/health", timeout=5)
        if r.status_code == 200:
            print(f"    {green('\u2713')} Server running")
        else:
            print(f"    {yellow('!')} Server unhealthy")
    except Exception:
        print(f"    {dim('Server not running')}")
    print()

    # Blockers
    print(bold("  \U0001f6a7 Blockers:"))
    git_status = _sp.run(["git", "status", "--porcelain"], cwd=cwd, capture_output=True, text=True, timeout=5)
    dirty_count = len([l for l in git_status.stdout.splitlines() if l.strip()])
    if dirty_count > 0:
        print(f"    {yellow('!')} {dirty_count} uncommitted changes")
    else:
        print(f"    {green('\u2713')} Clean working tree")
    print()

    # Format for Slack
    print(dim("  \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500"))
    print(dim("  Copy-paste for Slack:"))
    print()
    print(f"  *Standup \u2014 {repo_name}*")
    if git_log.stdout.strip():
        print(f"  \u2705 Done: {git_log.stdout.strip().splitlines()[0]}")
    print(f"  \U0001f3af Today: [from Jira or describe]")
    if dirty_count > 0:
        print(f"  \U0001f6a7 Blocker: {dirty_count} uncommitted changes")
    else:
        print(f"  \U0001f6a7 No blockers")
    print()

    # Copy to clipboard
    standup_text = f"Standup \u2014 {repo_name}\n"
    if git_log.stdout.strip():
        standup_text += f"\u2705 Done: {git_log.stdout.strip().splitlines()[0]}\n"
    standup_text += f"\U0001f3af Today: [describe]\n\U0001f6a7 No blockers\n"
    try:
        _sp.run(["pbcopy"], input=standup_text.encode(), capture_output=True, timeout=2)
        print(dim("  (copied to clipboard)"))
    except Exception:
        pass


def cmd_incident(args: list[str] | None = None):
    """Investigate a service incident — automated runbook.

    Usage:
      code-agents incident <service>              # full investigation
      code-agents incident <service> --rca        # generate RCA template
      code-agents incident <service> --save       # save report to file
      code-agents incident <service> --analyze    # AI-powered RCA prompt
    """
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    cwd = _user_cwd()
    args = args or sys.argv[2:]

    if not args or args[0].startswith("--"):
        print(red("  Usage: code-agents incident <service-name>"))
        print(dim("  Example: code-agents incident pg-acquiring-biz"))
        return

    service = args[0]
    gen_rca = "--rca" in args
    save = "--save" in args
    analyze = "--analyze" in args

    from code_agents.reporters.incident import (
        IncidentRunner, format_incident_report, generate_rca_template,
        build_rca_agent_prompt,
    )

    print()
    print(bold(f"  Investigating: {service}"))
    print(bold("  " + "=" * 50))

    runner = IncidentRunner(service=service, cwd=cwd)
    report = runner.run_all()

    # Display report
    print(format_incident_report(report))

    # RCA template
    if gen_rca:
        from datetime import datetime
        rca = generate_rca_template(report)
        rca_file = f"RCA-{service}-{datetime.now().strftime('%Y%m%d-%H%M')}.md"
        rca_path = os.path.join(cwd, rca_file)
        with open(rca_path, "w") as f:
            f.write(rca)
        print(green(f"\n  RCA template saved: {rca_file}"))

    # Save report
    if save:
        from datetime import datetime
        report_file = os.path.join(
            cwd, f"incident-{service}-{datetime.now().strftime('%Y%m%d-%H%M')}.md"
        )
        with open(report_file, "w") as f:
            f.write(format_incident_report(report))
        print(green(f"\n  Report saved: {report_file}"))

    # AI-powered RCA analysis prompt
    if analyze:
        rca_prompt = build_rca_agent_prompt(report)
        print()
        print(bold(cyan("  AI RCA Analysis Prompt")))
        print(dim("  Feed this to the agent via: code-agents chat"))
        print(dim("  " + "-" * 50))
        print(rca_prompt)
        print(dim("  " + "-" * 50))

    print()


def cmd_oncall_report(args: list[str] | None = None):
    """Generate on-call handoff report.

    Usage:
      code-agents oncall-report              # last 7 days
      code-agents oncall-report --days 14    # custom period
      code-agents oncall-report --save       # save to markdown file
      code-agents oncall-report --slack      # format for Slack/Confluence
    """
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    cwd = _user_cwd()
    args = args or sys.argv[2:]

    # Parse --days N
    days = 7
    if "--days" in args:
        idx = args.index("--days")
        if idx + 1 < len(args):
            try:
                days = int(args[idx + 1])
            except ValueError:
                print(red("  --days requires an integer"))
                return
    save = "--save" in args
    slack = "--slack" in args

    print()
    print(bold(cyan("  On-Call Handoff Report")))
    print(dim(f"  Collecting data for the last {days} days..."))
    print()

    from code_agents.reporters.oncall import OncallReporter, format_oncall_report, generate_oncall_markdown

    reporter = OncallReporter(cwd=cwd, days=days)
    report = reporter.generate()

    # Terminal display
    print(format_oncall_report(report))
    print()

    # Markdown output
    if save or slack:
        md = generate_oncall_markdown(report)
        if save:
            fname = f"oncall-report-{report.period_start}-to-{report.period_end}.md"
            fpath = os.path.join(cwd, fname)
            with open(fpath, "w") as f:
                f.write(md)
            print(green(f"  Saved: {fpath}"))
            print()
        if slack:
            print(bold("  Markdown (copy for Slack/Confluence):"))
            print(dim("  " + "-" * 50))
            print(md)
            print(dim("  " + "-" * 50))
            print()


def cmd_sprint_report(rest: list[str] | None = None):
    """Generate sprint summary report.

    Usage:
      code-agents sprint-report              # current sprint (14 days)
      code-agents sprint-report --days 21    # custom period
      code-agents sprint-report --save       # save to file
      code-agents sprint-report --slack      # markdown for Slack
    """
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    cwd = _user_cwd()
    args = rest or []

    # Parse --days N
    days = 14
    if "--days" in args:
        idx = args.index("--days")
        if idx + 1 < len(args):
            try:
                days = int(args[idx + 1])
            except ValueError:
                print(red("  --days requires an integer"))
                return
    save = "--save" in args
    slack = "--slack" in args

    print()
    print(bold(cyan("  Sprint Report")))
    print(dim(f"  Collecting data for the last {days} days..."))
    print()

    from code_agents.reporters.sprint_reporter import SprintReporter, format_sprint_report, generate_sprint_markdown

    reporter = SprintReporter(cwd=cwd, sprint_days=days)
    report = reporter.generate()

    # Terminal display
    print(format_sprint_report(report))
    print()

    # Markdown output
    if save or slack:
        md = generate_sprint_markdown(report)
        if save:
            from datetime import datetime as _dt
            date_str = _dt.now().strftime("%Y-%m-%d")
            fname = f"sprint-report-{date_str}.md"
            fpath = os.path.join(cwd, fname)
            with open(fpath, "w") as f:
                f.write(md)
            print(green(f"  Saved: {fpath}"))
            print()
        if slack:
            print(bold("  Markdown (copy for Slack/Confluence):"))
            print(dim("  " + "-" * 50))
            print(md)
            print(dim("  " + "-" * 50))
            print()


def cmd_sprint_velocity(rest: list[str] | None = None):
    """Track sprint velocity across sprints from Jira.

    Usage:
      code-agents sprint-velocity              # last 5 sprints
      code-agents sprint-velocity --sprints 10 # custom number
      code-agents sprint-velocity --json       # JSON output
    """
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    cwd = _user_cwd()
    args = rest or []

    # Parse --sprints N
    num_sprints = 5
    if "--sprints" in args:
        idx = args.index("--sprints")
        if idx + 1 < len(args):
            try:
                num_sprints = int(args[idx + 1])
            except ValueError:
                print(red("  --sprints requires an integer"))
                return
    json_output = "--json" in args

    print()
    print(bold(cyan("  Sprint Velocity Tracker")))
    print(dim(f"  Collecting data for the last {num_sprints} sprints..."))
    print()

    from code_agents.reporters.sprint_velocity import SprintVelocityTracker, format_report

    tracker = SprintVelocityTracker(cwd=cwd)
    report = tracker.calculate_velocity(sprints=num_sprints)

    if json_output:
        import json as _json
        data = {
            "project_key": report.project_key,
            "repo_name": report.repo_name,
            "source": report.source,
            "avg_velocity": report.avg_velocity,
            "trend": report.trend,
            "total_bugs_created": report.total_bugs_created,
            "total_bugs_resolved": report.total_bugs_resolved,
            "sprints": [
                {
                    "name": s.name,
                    "start_date": s.start_date,
                    "end_date": s.end_date,
                    "completed_points": s.completed_points,
                    "committed_points": s.committed_points,
                    "state": s.state,
                    "carry_overs": len(s.carry_overs),
                }
                for s in report.sprints
            ],
            "carry_overs": report.total_carry_overs,
        }
        print(_json.dumps(data, indent=2))
    else:
        print(format_report(report))

    print()


def cmd_env_health(rest: list[str] | None = None):
    """Check environment health — ArgoCD, Jenkins, Jira, Kibana status.

    Usage:
      code-agents env-health
    """
    from code_agents.reporters.env_health import EnvironmentHealthChecker, format_env_health

    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    print()
    print(bold(cyan("  Environment Health Check")))
    print()

    checker = EnvironmentHealthChecker()
    report = checker.run_all()
    print(format_env_health(report))
    print()


def cmd_morning(rest: list[str] | None = None):
    """Morning autopilot — git pull, build, Jira, tests, alerts.

    Usage:
      code-agents morning
    """
    from code_agents.reporters.morning import MorningAutopilot, format_morning_report

    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    cwd = os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()

    print()
    print(bold(cyan("  Morning Autopilot")))
    print(dim("  Running morning checks..."))
    print()

    pilot = MorningAutopilot(cwd=cwd)
    report = pilot.run_all()
    print(format_morning_report(report))


def cmd_perf_baseline(rest: list[str] | None = None):
    """Record or compare performance baseline.

    Usage:
      code-agents perf-baseline                # profile + save as baseline
      code-agents perf-baseline --compare      # profile + compare with saved baseline
      code-agents perf-baseline --show         # show saved baseline
      code-agents perf-baseline --clear        # clear saved baseline
      code-agents perf-baseline --iterations 50  # custom iteration count
    """
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    args = rest or []

    print()
    print(bold(cyan("  Performance Baseline")))
    print()

    # --show: display saved baseline
    if "--show" in args:
        from code_agents.observability.performance import BASELINE_PATH
        if not BASELINE_PATH.exists():
            print(yellow("  No baseline saved yet."))
            print(dim("  Run: code-agents perf-baseline"))
            print()
            return
        import json as _json
        with open(BASELINE_PATH) as f:
            data = _json.load(f)
        updated = data.get("updated", "unknown")
        print(dim(f"  Last updated: {updated}"))
        print()
        for entry in data.get("baselines", []):
            print(f"  {entry.get('method', 'GET')} {entry['url']}")
            print(f"    p50: {entry.get('p50', 0):.1f}ms  p95: {entry.get('p95', 0):.1f}ms  "
                  f"p99: {entry.get('p99', 0):.1f}ms  avg: {entry.get('avg', 0):.1f}ms")
            print(f"    Recorded: {entry.get('recorded_at', 'unknown')}")
            print()
        return

    # --clear: delete baseline
    if "--clear" in args:
        from code_agents.observability.performance import BASELINE_PATH
        if BASELINE_PATH.exists():
            BASELINE_PATH.unlink()
            print(green("  Baseline cleared."))
        else:
            print(yellow("  No baseline to clear."))
        print()
        return

    # Parse --iterations
    iterations = 20
    if "--iterations" in args:
        idx = args.index("--iterations")
        if idx + 1 < len(args):
            try:
                iterations = int(args[idx + 1])
            except ValueError:
                pass

    compare_only = "--compare" in args

    from code_agents.observability.performance import PerformanceProfiler, format_profile_report

    profiler = PerformanceProfiler()
    cwd = _user_cwd()
    endpoints = profiler.discover_endpoints(cwd)

    if not endpoints:
        print(yellow("  No endpoints discovered."))
        print()
        return

    print(dim(f"  Profiling {len(endpoints)} endpoint(s), {iterations} iterations each..."))
    print()

    report = profiler.profile_multiple(endpoints, iterations=iterations)
    print(format_profile_report(report))
    print()

    if not compare_only:
        count = profiler.save_as_baseline(report.results)
        print(green(f"  Baseline saved ({count} endpoint(s))."))
        print(dim(f"  Run 'code-agents perf-baseline --compare' to compare next time."))
    else:
        regressions = [c for c in report.baseline_comparison if c.get("regression")]
        if regressions:
            print(red(f"  {len(regressions)} regression(s) detected!"))
        elif report.baseline_comparison:
            print(green("  All endpoints within baseline thresholds."))
        else:
            print(yellow("  No baseline to compare against. Run without --compare first."))

    print()
