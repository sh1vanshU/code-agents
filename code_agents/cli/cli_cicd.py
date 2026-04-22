"""CLI CI/CD, pipeline, release, deploy commands."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile

from .cli_helpers import (
    _colors, _server_url, _api_get, _api_post, _load_env,
    _user_cwd, _find_code_agents_home, prompt_yes_no,
)

logger = logging.getLogger("code_agents.cli.cli_cicd")


def cmd_test(args: list[str]):
    """Run tests on the target repository."""
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    cwd = _user_cwd()
    branch = args[0] if args else None
    body: dict = {"repo_path": cwd}
    if branch:
        body["branch"] = branch

    print(bold(f"  Running tests in {os.path.basename(cwd)}..."))
    print()

    data = _api_post("/testing/run", body)
    if not data:
        # Fallback: run directly
        import asyncio
        from code_agents.cicd.testing_client import TestingClient
        client = TestingClient(cwd)
        try:
            data = asyncio.run(client.run_tests(branch=branch))
        except Exception as e:
            print(red(f"  Error: {e}"))
            return

    passed = data.get("passed", False)
    if passed:
        print(green(bold("  ✓ Tests PASSED")))
    else:
        print(red(bold("  ✗ Tests FAILED")))

    print(f"    Total:    {data.get('total', '?')}")
    print(f"    Passed:   {green(str(data.get('passed_count', '?')))}")
    print(f"    Failed:   {red(str(data.get('failed_count', '?')))}")
    print(f"    Errors:   {data.get('error_count', '?')}")
    print(f"    Command:  {dim(data.get('test_command', '?'))}")

    if not passed and data.get("output"):
        print()
        print(bold("  Output (last 30 lines):"))
        lines = data["output"].strip().splitlines()
        for line in lines[-30:]:
            print(f"    {line}")
    print()


def cmd_coverage(args: list[str]):
    """Lightweight coverage report — runs in batches to avoid memory blowup.

    Usage:
        code-agents coverage              # summary for whole project
        code-agents coverage chat         # single module/pattern
        code-agents coverage --top 20     # top 20 lowest-coverage modules
    """
    bold, green, yellow, red, cyan, dim = _colors()

    home = _find_code_agents_home()
    tests_dir = home / "tests"
    src_dir = home / "code_agents"

    # Parse args
    pattern = None
    top_n = 10
    i = 0
    while i < len(args):
        if args[i] == "--top" and i + 1 < len(args):
            top_n = int(args[i + 1])
            i += 2
        else:
            pattern = args[i]
            i += 1

    # Discover test files matching pattern
    test_files = sorted(tests_dir.glob("test_*.py"))
    if pattern:
        test_files = [f for f in test_files if pattern in f.name]
        if not test_files:
            print(red(f"  No test files matching '{pattern}'"))
            return

    print(bold(f"  Running coverage across {len(test_files)} test file(s)..."))
    print(dim(f"  Mode: batch (memory-safe) | Source: code_agents/"))
    print()

    results: list[dict] = []
    failed_files: list[str] = []

    for idx, tf in enumerate(test_files, 1):
        label = tf.name.replace("test_", "").replace(".py", "")
        status = f"  [{idx}/{len(test_files)}] {label}..."
        print(f"{status}", end="", flush=True)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            proc = subprocess.run(
                [
                    sys.executable, "-m", "pytest", str(tf),
                    f"--cov={src_dir}", "--cov-report", f"json:{tmp_path}",
                    "--cov-report", "term:skip-covered",
                    "--tb=no", "-q", "--no-header",
                ],
                capture_output=True, text=True, timeout=120,
                cwd=str(home),
            )

            if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                with open(tmp_path) as f:
                    data = json.load(f)
                totals = data.get("totals", {})
                pct = totals.get("percent_covered", 0)
                results.append({
                    "file": tf.name,
                    "module": label,
                    "pct": round(pct, 1),
                    "stmts": totals.get("num_statements", 0),
                    "miss": totals.get("missing_lines", 0),
                })
                color = green if pct >= 80 else (yellow if pct >= 60 else red)
                print(f" {color(f'{pct:.1f}%')}")
            else:
                failed_files.append(tf.name)
                print(f" {red('FAIL')}")

        except subprocess.TimeoutExpired:
            failed_files.append(tf.name)
            print(f" {red('TIMEOUT')}")
        except Exception as e:
            failed_files.append(tf.name)
            print(f" {red(f'ERROR: {e}')}")
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # Summary
    if not results:
        print(red("\n  No coverage data collected."))
        return

    print()
    print(bold("  ─── Coverage Summary ───"))
    print()

    # Sort by coverage ascending (worst first)
    results.sort(key=lambda r: r["pct"])

    total_stmts = sum(r["stmts"] for r in results)
    total_miss = sum(r["miss"] for r in results)
    overall = round((1 - total_miss / total_stmts) * 100, 1) if total_stmts else 0

    # Show top N lowest
    show = results[:top_n]
    header = f"  {'Module':<35} {'Stmts':>6} {'Miss':>6} {'Cover':>7}"
    print(dim(header))
    print(dim("  " + "─" * 56))

    for r in show:
        color = green if r["pct"] >= 80 else (yellow if r["pct"] >= 60 else red)
        pct_str = f"{r['pct']:>6.1f}%"
        print(f"  {r['module']:<35} {r['stmts']:>6} {r['miss']:>6} {color(pct_str)}")

    if len(results) > top_n:
        print(dim(f"  ... and {len(results) - top_n} more (use --top {len(results)} to see all)"))

    print()
    overall_color = green if overall >= 80 else (yellow if overall >= 60 else red)
    print(bold(f"  Overall: {overall_color(f'{overall}%')}") + dim(f"  ({total_stmts} stmts, {total_miss} missing)"))

    if failed_files:
        print()
        print(yellow(f"  ⚠ {len(failed_files)} file(s) failed/timed out:"))
        for ff in failed_files[:5]:
            print(dim(f"    - {ff}"))
    print()


def cmd_pipeline(args: list[str]):
    """Manage CI/CD pipeline."""
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    sub = args[0] if args else "status"

    if sub == "start":
        branch = args[1] if len(args) > 1 else None
        if not branch:
            # Get current branch
            cur = _api_get("/git/current-branch")
            branch = cur.get("branch", "HEAD") if cur else "HEAD"

        print(bold(f"  Starting pipeline for branch: {cyan(branch)}"))
        data = _api_post("/pipeline/start", {"branch": branch})
        if data:
            print(green(f"  ✓ Pipeline started: run_id={data.get('run_id')}"))
            print(f"    Step: {data.get('current_step_name', '?')}")
            print(f"    Track: code-agents pipeline status {data.get('run_id')}")
        print()

    elif sub == "status":
        run_id = args[1] if len(args) > 1 else None
        if run_id:
            data = _api_get(f"/pipeline/{run_id}/status")
            if data:
                _print_pipeline_status(data)
            else:
                print(red(f"  Pipeline run {run_id} not found"))
        else:
            data = _api_get("/pipeline/runs")
            if data and data.get("runs"):
                for run in data["runs"]:
                    _print_pipeline_status(run)
                    print()
            else:
                print(dim("  No pipeline runs. Start one: code-agents pipeline start"))
        print()

    elif sub == "advance":
        run_id = args[1] if len(args) > 1 else None
        if not run_id:
            print(red("  Usage: code-agents pipeline advance <run_id>"))
            return
        data = _api_post(f"/pipeline/{run_id}/advance")
        if data:
            print(green(f"  ✓ Advanced to step {data.get('current_step')}: {data.get('current_step_name')}"))
        print()

    elif sub == "rollback":
        run_id = args[1] if len(args) > 1 else None
        if not run_id:
            print(red("  Usage: code-agents pipeline rollback <run_id>"))
            return
        data = _api_post(f"/pipeline/{run_id}/rollback")
        if data:
            print(yellow(f"  ⟲ Rollback triggered for pipeline {run_id}"))
            if data.get("rollback_info"):
                print(f"    {data['rollback_info'].get('instruction', '')}")
        print()

    else:
        print(f"  Unknown pipeline command: {sub}")
        print(f"  Usage: code-agents pipeline [start|status|advance|rollback] [args]")
        print()


def _print_pipeline_status(data: dict):
    """Pretty-print a pipeline run status."""
    bold, green, yellow, red, cyan, dim = _colors()

    status_icons = {
        "pending": "·", "in_progress": "▶", "success": "✓",
        "failed": "✗", "skipped": "○", "rolled_back": "⟲",
    }
    status_colors = {
        "pending": dim, "in_progress": cyan, "success": green,
        "failed": red, "skipped": dim, "rolled_back": yellow,
    }

    print(bold(f"  Pipeline: {data.get('run_id')}"))
    print(f"  Branch:   {cyan(data.get('branch', '?'))}")
    print(f"  Step:     {data.get('current_step')}/6 ({data.get('current_step_name', '?')})")
    if data.get("build_number"):
        print(f"  Build:    #{data['build_number']}")
    if data.get("error"):
        print(f"  Error:    {red(data['error'])}")
    print()

    steps = data.get("steps", {})
    for i in range(1, 7):
        step = steps.get(str(i), {})
        status = step.get("status", "pending")
        name = step.get("name", "?")
        icon = status_icons.get(status, "?")
        color_fn = status_colors.get(status, dim)
        print(f"    {color_fn(icon)} {i}. {name:<20} {color_fn(status)}")


def cmd_release(args: list[str] | None = None):
    """Automate release process end-to-end.

    Usage:
      code-agents release <version>               # full release
      code-agents release <version> --dry-run      # preview only
      code-agents release <version> --skip-deploy  # skip build/deploy/sanity
      code-agents release <version> --skip-jira    # skip Jira updates
      code-agents release <version> --skip-tests   # skip test step
    """
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    args = args or []
    if not args or args[0].startswith("--"):
        print()
        print(bold(cyan("  Release Automation")))
        print()
        print(f"  Usage: code-agents release <version> [flags]")
        print()
        print(f"    {cyan('code-agents release v8.1.0')}              {dim('# full release')}")
        print(f"    {cyan('code-agents release 8.1.0 --dry-run')}    {dim('# preview only')}")
        print(f"    {cyan('code-agents release 8.1.0 --skip-deploy')}{dim('# skip build/deploy')}")
        print(f"    {cyan('code-agents release 8.1.0 --skip-jira')}  {dim('# skip Jira updates')}")
        print(f"    {cyan('code-agents release 8.1.0 --skip-tests')} {dim('# skip tests')}")
        print()
        print(f"  Flags:")
        print(f"    {dim('--dry-run')}       Preview all steps without executing")
        print(f"    {dim('--skip-deploy')}   Skip build, deploy, and sanity steps")
        print(f"    {dim('--skip-jira')}     Skip Jira ticket transitions")
        print(f"    {dim('--skip-tests')}    Skip test execution")
        print()
        return

    version = args[0]
    flags = [a.lower() for a in args[1:]]
    dry_run = "--dry-run" in flags
    skip_deploy = "--skip-deploy" in flags
    skip_jira = "--skip-jira" in flags
    skip_tests = "--skip-tests" in flags

    cwd = _user_cwd()

    from code_agents.tools.release import ReleaseManager
    mgr = ReleaseManager(version=version, cwd=cwd, dry_run=dry_run)

    print()
    print(bold(cyan("  ╔══════════════════════════════════════════════╗")))
    print(bold(cyan("  ║       Code Agents — Release Automation       ║")))
    print(bold(cyan("  ╚══════════════════════════════════════════════╝")))
    print()
    print(f"  Version:  {bold(mgr.version)}")
    print(f"  Branch:   {cyan(mgr.branch_name)}")
    print(f"  Repo:     {dim(cwd)}")
    if dry_run:
        print(f"  Mode:     {yellow('DRY RUN (no changes will be made)')}")
    print()

    if not dry_run:
        if not prompt_yes_no("Proceed with release?", default=True):
            print(yellow("  Cancelled."))
            print()
            return

    # Build step list for progress display
    step_names = ["Create release branch"]
    if not skip_tests:
        step_names.append("Run tests")
    step_names.extend(["Generate changelog", "Bump version", "Commit changes", "Push branch"])
    if not skip_deploy:
        step_names.extend(["Build", "Deploy to staging", "Run sanity checks"])
    if not skip_jira:
        step_names.append("Update Jira tickets")

    total = len(step_names)

    # Run steps with progress
    steps_fns = [("Create release branch", mgr.create_branch)]
    if not skip_tests:
        steps_fns.append(("Run tests", mgr.run_tests))
    steps_fns.extend([
        ("Generate changelog", mgr.generate_changelog),
        ("Bump version", mgr.bump_version),
        ("Commit changes", mgr.commit_changes),
        ("Push branch", mgr.push_branch),
    ])
    if not skip_deploy:
        steps_fns.extend([
            ("Build", mgr.trigger_build),
            ("Deploy to staging", mgr.deploy_staging),
            ("Run sanity checks", mgr.run_sanity),
        ])
    if not skip_jira:
        steps_fns.append(("Update Jira tickets", mgr.update_jira))

    success = True
    for idx, (step_name, step_fn) in enumerate(steps_fns, 1):
        print(f"  [{idx}/{total}] {step_name}...", end=" ", flush=True)
        try:
            ok = step_fn()
            if ok:
                mgr.steps_completed.append(step_name)
                print(green("done"))
            else:
                print(red("FAILED"))
                success = False
                break
        except Exception as exc:
            mgr.errors.append(f"{step_name}: {exc}")
            print(red(f"ERROR: {exc}"))
            success = False
            break

    print()
    if success:
        print(bold(green(f"  ✓ Release {mgr.version} completed successfully!")))
        print()
        print(f"  Steps completed: {len(mgr.steps_completed)}/{total}")
        print(f"  Branch: {cyan(mgr.branch_name)}")
        print()
        print(f"  Next steps:")
        print(f"    1. Create a PR from {cyan(mgr.branch_name)} to main")
        print(f"    2. Get code review approval")
        print(f"    3. Merge and tag: {dim(f'git tag v{mgr.version}')}")
        print()
    else:
        print(bold(red(f"  ✗ Release {mgr.version} failed")))
        print()
        if mgr.errors:
            print(f"  Errors:")
            for err in mgr.errors:
                print(f"    {red('•')} {err}")
            print()
        if mgr.steps_completed:
            print(f"  Completed before failure:")
            for s in mgr.steps_completed:
                print(f"    {green('✓')} {s}")
            print()

        if not dry_run:
            if prompt_yes_no("Rollback release branch?", default=True):
                print(f"  Rolling back...", end=" ", flush=True)
                if mgr.rollback():
                    print(green("done"))
                else:
                    print(red("rollback failed"))
            print()


def cmd_coverage_boost(rest: list[str] | None = None):
    """Auto-boost test coverage — scan, analyze, generate tests.

    Usage:
      code-agents coverage-boost              # full pipeline
      code-agents coverage-boost --dry-run    # analyze only, don't run tests
      code-agents coverage-boost --target 90  # set coverage target
      code-agents coverage-boost --commit     # auto-commit generated tests
    """
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    cwd = _user_cwd()
    args = rest or []

    dry_run = "--dry-run" in args
    auto_commit = "--commit" in args
    target = 80.0
    if "--target" in args:
        idx = args.index("--target")
        if idx + 1 < len(args):
            try:
                target = float(args[idx + 1])
            except ValueError:
                pass

    from code_agents.tools.auto_coverage import AutoCoverageBoost, format_coverage_report

    print()
    print(bold("  Auto-Coverage Boost"))
    print(bold("  " + "=" * 50))

    boost = AutoCoverageBoost(cwd=cwd, target_pct=target)

    # Step 1
    print(dim("  Step 1/5: Scanning existing tests..."))
    scan = boost.scan_existing_tests()
    print(f"    {scan['files']} test files, {scan['methods']} test methods")

    # Step 2
    if not dry_run:
        print(dim("  Step 2/5: Running coverage baseline..."))
        baseline = boost.run_coverage_baseline()
        pct = baseline.get("coverage", 0)
        if pct >= target:
            print(green(f"    Coverage: {pct}% -- already meets target ({target}%)"))
            print()
            return
        print(f"    Coverage: {pct}% (target: {target}%)")
    else:
        print(dim("  Step 2/5: Skipped (dry-run)"))

    # Step 3
    print(dim("  Step 3/5: Identifying gaps..."))
    gaps = boost.identify_gaps()
    print(f"    {len(gaps)} uncovered files/methods found")

    # Step 4
    print(dim("  Step 4/5: Prioritizing by risk..."))
    prioritized = boost.prioritize_gaps()
    critical = sum(1 for g in prioritized if g.risk == "critical")
    high = sum(1 for g in prioritized if g.risk == "high")
    print(f"    {critical} critical, {high} high priority")

    # Step 5
    print(dim("  Step 5/5: Building test generation prompts..."))
    prompts = boost.build_test_prompts()
    print(f"    {len(prompts)} files ready for test generation")

    # Show report
    print()
    print(format_coverage_report(boost.report))

    # Build delegation prompt
    if prompts:
        delegation = boost.build_delegation_prompt(prompts)
        print()
        print(dim(f"  Delegation prompt ready ({len(delegation)} chars)"))
        print(dim(f"  Use in chat: paste this to code-tester agent, or run:"))
        print(dim(f"    code-agents chat code-tester"))
        print(dim(f"    Then paste the prompt above"))

    print()


def cmd_watch(rest: list[str] | None = None):
    """Watch mode — file watcher with auto-lint, auto-test, and auto-fix.

    Watches source files for changes, runs lint and tests on affected files,
    and auto-delegates failures to agents for fixing.

    Usage:
      code-agents watch                    # watch cwd, auto-detect everything
      code-agents watch src/               # watch specific directory
      code-agents watch --lint-only        # only lint, no tests
      code-agents watch --test-only        # only tests, no lint
      code-agents watch --no-fix           # report failures, don't auto-fix
      code-agents watch --interval 5       # poll every 5s (default: 3s)
    """
    import asyncio

    from code_agents.tools.watch_mode import WatchMode, format_watch_event

    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    cwd = _user_cwd()
    args = rest or []

    lint_only = "--lint-only" in args
    test_only = "--test-only" in args
    no_fix = "--no-fix" in args
    interval = 3.0
    if "--interval" in args:
        idx = args.index("--interval")
        if idx + 1 < len(args):
            try:
                interval = float(args[idx + 1])
            except ValueError:
                pass

    # Target path: first non-flag argument
    watch_path = ""
    skip_next = False
    for a in args:
        if skip_next:
            skip_next = False
            continue
        if a == "--interval":
            skip_next = True
            continue
        if not a.startswith("-"):
            watch_path = a
            break

    wm = WatchMode(
        repo_path=cwd,
        watch_path=watch_path,
        interval=interval,
        lint_only=lint_only,
        test_only=test_only,
        no_fix=no_fix,
    )

    if not wm.language:
        print(red("  Could not detect project language/framework."))
        print(dim("  Supported: Python, Java, JavaScript/TypeScript, Go"))
        print()
        return

    print()
    print(bold(cyan("  Watch Mode")))
    print(dim(f"  Stack: {wm.language} / lint={wm.lint_tool or 'none'} / test={wm.test_framework}"))
    print(dim(f"  Target: {watch_path or 'entire repo'}"))
    print(dim(f"  Interval: {interval}s | Lint: {'on' if not test_only else 'off'} | Test: {'on' if not lint_only else 'off'} | Auto-fix: {'on' if not no_fix else 'off'}"))
    print(dim("  Press Ctrl+C to stop"))
    print()

    def on_event(event_type: str, detail: str):
        print(format_watch_event(event_type, detail))
        sys.stdout.flush()

    try:
        asyncio.run(wm.run(on_event=on_event))
    except KeyboardInterrupt:
        wm.stop()
        print()
        print(dim("  Watch mode stopped."))
        print()


def cmd_gen_tests(rest: list[str] | None = None):
    """AI-powered test generation — fully automated, zero copy-paste.

    Scans source files with AST parsers, auto-delegates to code-tester agent,
    writes test files, and optionally runs them in a fix loop.

    Usage:
      code-agents gen-tests src/payments/       # directory
      code-agents gen-tests src/payments/api.py # single file
      code-agents gen-tests --all               # entire repo (gaps only)
      code-agents gen-tests --verify            # run + auto-fix loop (up to 3 retries)
      code-agents gen-tests --dry-run           # analyze only, show plan
      code-agents gen-tests --max 5             # limit to 5 files (default: 10)
    """
    import asyncio

    from code_agents.tools.test_generator import TestGenerator, format_gen_tests_report

    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    cwd = _user_cwd()
    args = rest or []

    dry_run = "--dry-run" in args
    verify = "--verify" in args
    max_files = 10
    if "--max" in args:
        idx = args.index("--max")
        if idx + 1 < len(args):
            try:
                max_files = int(args[idx + 1])
            except ValueError:
                pass

    # Target path: first non-flag argument
    target = ""
    for a in args:
        if not a.startswith("-") and a not in (str(max_files),):
            target = a
            break

    print()
    print(bold(cyan("  AI Test Generator")))
    print(dim(f"  Target: {target or 'entire repo'}"))
    if verify:
        print(dim("  Mode: generate + verify + auto-fix"))
    elif dry_run:
        print(dim("  Mode: dry-run (analyze only)"))
    else:
        print(dim("  Mode: generate"))
    print()

    gen = TestGenerator(
        repo_path=cwd,
        target_path=target,
        max_files=max_files,
        verify=verify,
        dry_run=dry_run,
    )

    if not gen.language:
        print(red("  Could not detect project language/framework."))
        print(dim("  Supported: Python, Java, JavaScript/TypeScript, Go"))
        print()
        return

    print(dim(f"  Stack: {gen.language} / {gen.test_framework}"))
    print()

    def on_progress(step: str, detail: str):
        icons = {
            "analyze": "1/4 Scanning",
            "gaps": "2/4 Gaps found",
            "style": "2/4 Learning patterns",
            "generate": "3/4 Generating",
            "done": "4/4 Done",
        }
        label = icons.get(step, step)
        if step == "done":
            print()
            print(green(f"  {label}: {detail}"))
        elif step == "generate":
            print(f"  {dim(label)}: {detail}")
        else:
            print(f"  {dim(label)}: {detail}")

    report = asyncio.run(gen.run(on_progress=on_progress))

    print()
    print(format_gen_tests_report(report))
    print()

    if report.files_generated and not dry_run:
        print(dim("  Test files written to disk."))
        if not verify:
            print(dim("  Run with --verify to auto-run and fix failing tests."))
        print()


def cmd_qa_suite(rest: list[str] | None = None):
    """Generate QA regression test suite for the repo.

    Usage:
      code-agents qa-suite                # analyze + generate
      code-agents qa-suite --analyze      # analyze only (no file generation)
      code-agents qa-suite --write        # write generated files to disk
      code-agents qa-suite --commit       # write + git commit on new branch
    """
    from code_agents.generators.qa_suite_generator import QASuiteGenerator, format_analysis

    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    cwd = _user_cwd()
    args = rest or []

    analyze_only = "--analyze" in args
    write_files = "--write" in args or "--commit" in args
    auto_commit = "--commit" in args

    print()
    print(bold(cyan("  QA Suite Generator")))
    print(dim(f"  Analyzing {cwd}..."))
    print()

    gen = QASuiteGenerator(cwd=cwd)
    analysis = gen.analyze()

    if not analysis.language:
        print(red("  Could not detect project language/framework."))
        print(dim("  Supported: Java (Maven/Gradle), Python (pyproject/requirements), JS (package.json), Go"))
        print()
        return

    # Show analysis
    print(format_analysis(analysis))
    print()

    if analysis.has_existing_tests and not args:
        print(yellow(f"  Found {analysis.existing_test_count} existing test files."))
        print(dim("  Use --write to generate additional tests alongside existing ones."))
        print()

    if analyze_only:
        print(dim("  Analyze-only mode. Use --write to generate test files."))
        print()
        return

    # Generate suite
    print(dim("  Generating test suite..."))
    generated = gen.generate_suite()

    if not generated:
        print(yellow("  No test files generated (no endpoints/services/repos discovered)."))
        print()
        return

    print(green(f"  Generated {len(generated)} test files"))
    for f in generated:
        print(f"    {f['path']} — {f['description']}")
    print()

    if write_files:
        written = 0
        for f in generated:
            fpath = os.path.join(cwd, f["path"])
            os.makedirs(os.path.dirname(fpath), exist_ok=True)
            if os.path.exists(fpath):
                print(yellow(f"    SKIP (exists): {f['path']}"))
                continue
            with open(fpath, "w") as fp:
                fp.write(f["content"])
            print(green(f"    WROTE: {f['path']}"))
            written += 1
        print()
        print(green(f"  {written} files written to disk"))

        if auto_commit and written > 0:
            import subprocess as _sp
            branch = "qa-suite/auto-generated"
            print(dim(f"  Creating branch: {branch}"))
            _sp.run(["git", "checkout", "-b", branch], cwd=cwd, capture_output=True)
            for f in generated:
                fpath = os.path.join(cwd, f["path"])
                if os.path.exists(fpath):
                    _sp.run(["git", "add", f["path"]], cwd=cwd, capture_output=True)
            _sp.run(
                ["git", "commit", "-m", f"test: add auto-generated QA regression suite ({written} files)"],
                cwd=cwd, capture_output=True,
            )
            print(green(f"  Committed on branch: {branch}"))
        print()
    else:
        # Show delegation prompt
        prompt = gen.build_agent_prompt()
        print(dim(f"  Delegation prompt ready ({len(prompt)} chars)"))
        print(dim(f"  Use in chat: /qa-suite to auto-generate, or run:"))
        print(dim(f"    code-agents qa-suite --write"))
        print()
