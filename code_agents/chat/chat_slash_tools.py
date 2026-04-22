"""Interactive tool slash commands: /pair, /kb, /coverage-boost, /qa-suite, /mutate, /testdata, /profile, /compile, /verify, /style."""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("code_agents.chat.chat_slash_tools")

from .chat_ui import bold, green, yellow, red, cyan, dim


def _handle_tools(command: str, arg: str, state: dict, url: str) -> Optional[str]:
    """Handle interactive tool slash commands."""

    if command == "/pair":
        from code_agents.domain.pair_mode import PairMode

        if arg in ("off", "stop"):
            if state.get("_pair_mode"):
                state["_pair_mode"].stop()
                state["_pair_mode"] = None
                print(f"  {green('Pair programming mode OFF')}")
            else:
                print(dim("  Pair mode is not active"))
            print()
        elif arg == "status":
            pm = state.get("_pair_mode")
            if pm and pm.active:
                print(f"  Pair mode: {green('ACTIVE')}")
                print(f"  Watching: {len(pm._file_hashes)} files")
                print(f"  Patterns: {', '.join(pm.watch_patterns)}")
            else:
                print(f"  Pair mode: {dim('inactive')}")
            print()
        else:
            # Start pair mode
            repo = state.get("repo_path", ".")
            patterns = arg.split(",") if arg else None
            pm = PairMode(cwd=repo, watch_patterns=patterns)
            pm.start()
            state["_pair_mode"] = pm
            print(f"  {green('Pair programming mode ON')}")
            print(f"  Watching {len(pm._file_hashes)} files in {repo}")
            print(dim("  I'll review your changes as you code."))
            print(dim("  /pair off to stop | /pair status to check"))
            print()

    elif command == "/coverage-boost":
        from code_agents.tools.auto_coverage import AutoCoverageBoost, format_coverage_report
        target = 80.0
        if arg:
            try:
                target = float(arg)
            except ValueError:
                pass

        repo = state.get("repo_path", os.getcwd())
        boost = AutoCoverageBoost(cwd=repo, target_pct=target)

        print(dim("  Running auto-coverage pipeline..."))
        report = boost.run_pipeline(dry_run=False)
        print(format_coverage_report(report))

        if report.prioritized_gaps:
            prompts = boost.build_test_prompts()
            if prompts:
                delegation = boost.build_delegation_prompt(prompts)
                print()
                print(dim(f"  Delegating to code-tester ({len(prompts)} files)..."))
                # Feed as next user message (agent will generate tests)
                state["_exec_feedback"] = {
                    "command": "/coverage-boost",
                    "output": delegation,
                }
                return "exec_feedback"
        print()

    elif command == "/mutate":
        if not arg:
            print(yellow("  Usage: /mutate <file>"))
            print(dim("  Run mutation testing to verify test quality for a source file."))
            print()
            return None
        from code_agents.testing.mutation_tester import MutationTester, format_mutation_report
        repo = state.get("repo_path", os.getcwd())
        print(dim(f"  Generating mutations for {arg.strip()}..."))
        tester = MutationTester(repo_path=repo)
        report = tester.test_file(arg.strip())
        print()
        print(format_mutation_report(report))
        print()

    elif command == "/testdata":
        from code_agents.generators.test_data_generator import TestDataGenerator, format_test_data
        repo = state.get("repo_path", os.getcwd())
        gen = TestDataGenerator(repo_path=repo)

        if not arg:
            domains = gen.detect_domain()
            print(dim(f"  Auto-detected domains: {', '.join(domains)}"))
            records = gen.generate(domains=domains, count=5)
            print(format_test_data(records, language="json"))
            print()
        else:
            parts = arg.strip().split()
            domain = parts[0]
            count = 5
            lang = "json"
            if len(parts) > 1:
                try:
                    count = int(parts[1])
                except ValueError:
                    lang = parts[1]
            if len(parts) > 2:
                lang = parts[2]
            available = list(TestDataGenerator.__init__.__code__.co_varnames)  # noqa
            records = gen.generate(domains=[domain], count=count)
            if not records:
                print(yellow(f"  Unknown domain: {domain}"))
                print(dim(f"  Available: payment, user, merchant, api, date"))
            else:
                print(format_test_data(records, language=lang))
            print()

    elif command == "/profile":
        from code_agents.observability.performance import PerformanceProfiler, ProfileReport, format_profile_report
        profiler = PerformanceProfiler()

        if not arg:
            print("  Usage: /profile <url>")
            print("         /profile <url> --iterations 50")
            print("         /profile --discover  (auto-discover from repo)")
            print()
        elif arg.strip() == "--discover":
            endpoints = profiler.discover_endpoints(state.get("repo_path", "."))
            if not endpoints:
                print(yellow("  No endpoints discovered."))
            else:
                print(dim(f"  Profiling {len(endpoints)} endpoint(s)..."))
                report = profiler.profile_multiple(endpoints)
                print(format_profile_report(report))
            print()
        else:
            parts = arg.split()
            url = parts[0]
            iters = 20
            if "--iterations" in parts:
                idx = parts.index("--iterations")
                if idx + 1 < len(parts):
                    try:
                        iters = int(parts[idx + 1])
                    except ValueError:
                        pass
            result = profiler.profile_endpoint(url, iterations=iters)
            report = ProfileReport(
                results=[result],
                total_requests=iters,
                total_errors=result.errors,
            )
            print(format_profile_report(report))
            print()

    elif command == "/compile":
        # Manual compile check — run compile for detected project language
        cwd = state.get("repo_path", os.getcwd())
        from code_agents.analysis.compile_check import CompileChecker
        checker = CompileChecker(cwd=cwd)
        if not checker.language:
            print(yellow("  No supported build system found in this project."))
            print(dim("  Supported: Maven (pom.xml), Gradle (build.gradle), Go (go.mod), TypeScript (tsconfig.json)"))
            print()
        else:
            print(f"  {dim(f'Detected: {checker.language}')}")
            print(f"  {dim('Compiling...')}")
            result = checker.run_compile()
            if result.success:
                warn_str = f" with {len(result.warnings)} warning(s)" if result.warnings else ""
                print(f"  {green(f'✓ Compilation successful ({result.elapsed:.1f}s){warn_str}')}")
                for w in result.warnings[:5]:
                    print(f"    {yellow(w)}")
            else:
                print(f"  {red(f'✗ Compilation failed ({result.elapsed:.1f}s)')}")
                for err in result.errors[:10]:
                    print(f"    {err}")
                if len(result.errors) > 10:
                    print(dim(f"    ... and {len(result.errors) - 10} more errors"))
            print()

    elif command == "/verify":
        from code_agents.core.response_verifier import get_verifier
        verifier = get_verifier()
        if arg.lower() == "off":
            verifier.toggle(False)
            print(green("  ✓ Auto-verify OFF. Code-writer responses will not be reviewed."))
        elif arg.lower() in ("on", ""):
            verifier.toggle(True)
            print()
            print(green("  ✓ Auto-verify ON"))
            print(dim("  Code-writer responses with code blocks will be auto-reviewed by code-reviewer."))
            print(dim("  Type /verify off to disable."))
        elif arg.lower() == "status":
            status = "ON" if verifier.enabled else "OFF"
            print(f"  Auto-verify: {bold(status)}")
        else:
            print(yellow(f"  Usage: /verify [on|off|status]"))
        print()

    elif command == "/style":
        from code_agents.reviews.style_matcher import StyleMatcher
        repo = state.get("repo_path", os.getcwd())
        print()
        print(dim(f"  Scanning {repo}..."))
        matcher = StyleMatcher(repo)
        profile = matcher.analyze()
        if profile.language == "unknown":
            print(yellow("  No source files detected."))
        else:
            print(bold("  Detected Code Style"))
            print(matcher.format_display(profile))
            print()
            prompt = matcher.generate_style_prompt(profile)
            print(dim(f"  Prompt: {prompt}"))
        print()

    elif command == "/commands":
        # If query provided, use smart agent routing; else fall through to browser
        if arg and arg.strip():
            _handle_commands_smart(arg, state)
        else:
            _handle_commands_browser(arg, state)

    elif command == "/watch":
        from code_agents.tools.watch_mode import WatchMode, format_watch_event

        repo = state.get("repo_path", os.getcwd())

        if arg in ("off", "stop"):
            wm = state.get("_watch_mode")
            if wm and wm.active:
                wm.stop()
                state["_watch_mode"] = None
                print(f"  {green('Watch mode OFF')}")
            else:
                print(dim("  Watch mode is not active"))
            print()
            return None

        if arg == "status":
            wm = state.get("_watch_mode")
            if wm and wm.active:
                from code_agents.tools.watch_mode import format_watch_stats
                print(f"  Watch mode: {green('ACTIVE')}")
                print(format_watch_stats(wm.stats))
            else:
                print(f"  Watch mode: {dim('inactive')}")
            print()
            return None

        # Check if already running
        existing = state.get("_watch_mode")
        if existing and existing.active:
            print(yellow("  Watch mode already running. /watch stop first."))
            print()
            return None

        # Parse flags from arg
        parts = arg.split() if arg else []
        watch_path = ""
        lint_only = "--lint-only" in parts
        test_only = "--test-only" in parts
        no_fix = "--no-fix" in parts
        interval = 3.0
        for p in parts:
            if not p.startswith("-"):
                watch_path = p

        wm = WatchMode(
            repo_path=repo,
            watch_path=watch_path,
            lint_only=lint_only,
            test_only=test_only,
            no_fix=no_fix,
            interval=interval,
        )

        if not wm.language:
            print(red("  Could not detect project language/framework."))
            print()
            return None

        state["_watch_mode"] = wm

        def on_event(event_type, detail):
            import sys
            sys.stdout.write(format_watch_event(event_type, detail) + "\n")
            sys.stdout.flush()

        # Run in background thread — doesn't block the chat
        wm.run_in_background(on_event=on_event)

        print(f"  {green('Watch mode ON')} {dim('(background)')}")
        print(dim(f"  Stack: {wm.language} / lint={wm.lint_tool or 'none'} / test={wm.test_framework}"))
        print(dim(f"  Watching: {watch_path or 'entire repo'}"))
        print(dim(f"  /watch status — check stats | /watch stop — stop watching"))
        print(dim(f"  Keep chatting — watch runs in the background!"))
        print()

    elif command == "/slack":
        _handle_slack_command(arg, state)

    elif command == "/gen-tests":
        import asyncio
        from code_agents.tools.test_generator import TestGenerator, format_gen_tests_report

        repo = state.get("repo_path", os.getcwd())
        target = arg.strip() if arg else ""
        verify = "--verify" in target
        dry_run = "--dry-run" in target
        # Strip flags from target path
        target = " ".join(p for p in target.split() if not p.startswith("--"))

        gen = TestGenerator(
            repo_path=repo,
            target_path=target,
            verify=verify,
            dry_run=dry_run,
        )

        if not gen.language:
            print(red("  Could not detect project language/framework."))
            print()
            return None

        print(dim(f"  AI Test Generator — {gen.language} / {gen.test_framework}"))
        print(dim(f"  Target: {target or 'entire repo'}"))
        if dry_run:
            print(dim("  Mode: dry-run"))
        print()

        def on_progress(step, detail):
            print(f"  {dim(step)}: {detail}")

        report = asyncio.run(gen.run(on_progress=on_progress))
        print()
        print(format_gen_tests_report(report))
        print()

    elif command in ("/skill", "/marketplace"):
        from code_agents.cli.cli_skill import _skill_list, _skill_search, _skill_install, _skill_remove, _skill_info
        if not arg:
            _skill_list()
        elif arg.startswith("list"):
            _skill_list()
        elif arg.startswith("search "):
            _skill_search(arg.split(None, 1)[1])
        elif arg.startswith("install "):
            parts = arg.split()
            source = parts[1] if len(parts) > 1 else ""
            agent = parts[3] if len(parts) > 3 and parts[2] == "--agent" else "_shared"
            if source:
                _skill_install(source, agent)
            else:
                print(yellow("  Usage: /skill install <url-or-name>"))
        elif arg.startswith("remove "):
            _skill_remove(arg.split(None, 1)[1])
        elif arg.startswith("info "):
            _skill_info(arg.split(None, 1)[1])
        else:
            print(yellow(f"  Unknown: /skill {arg}"))
            print(dim("  Try: list, search, install, remove, info"))
        print()

    elif command == "/mindmap":
        from code_agents.ui.mindmap import RepoMindmap, format_terminal, format_mermaid, format_html

        repo = state.get("repo_path", os.getcwd())
        fmt = "text"
        depth = 3
        focus = None
        output_path = None

        if arg:
            parts = arg.split()
            i = 0
            while i < len(parts):
                if parts[i] == "--format" and i + 1 < len(parts):
                    fmt = parts[i + 1].lower()
                    i += 1
                elif parts[i] == "--depth" and i + 1 < len(parts):
                    try:
                        depth = int(parts[i + 1])
                    except ValueError:
                        pass
                    i += 1
                elif parts[i] == "--focus" and i + 1 < len(parts):
                    focus = parts[i + 1]
                    i += 1
                elif parts[i] == "--output" and i + 1 < len(parts):
                    output_path = parts[i + 1]
                    i += 1
                i += 1

        print(dim(f"  Scanning {repo}..."))
        try:
            mindmap = RepoMindmap(repo_path=repo, depth=depth, focus=focus)
            result = mindmap.build()
        except ValueError as exc:
            print(red(f"  Error: {exc}"))
            print()
            return None

        if fmt == "mermaid":
            output = format_mermaid(result)
        elif fmt == "html":
            output = format_html(result)
        else:
            output = format_terminal(result, depth=depth)

        if output_path:
            from pathlib import Path as _Path
            out = _Path(output_path).resolve()
            out.write_text(output, encoding="utf-8")
            print(green(f"  Written to {out}"))
        else:
            print(output)
        print()

    elif command in ("/txn-flow", "/transaction-flow"):
        from code_agents.domain.txn_flow import TxnFlowTracer

        repo = state.get("repo_path", os.getcwd())
        parts = arg.strip().split() if arg else []

        order_id = ""
        env = "dev"
        from_code = "--from-code" in parts
        fmt = "terminal"

        i = 0
        while i < len(parts):
            if parts[i] == "--order-id" and i + 1 < len(parts):
                order_id = parts[i + 1]
                i += 1
            elif parts[i] == "--env" and i + 1 < len(parts):
                env = parts[i + 1]
                i += 1
            elif parts[i] == "--format" and i + 1 < len(parts):
                fmt = parts[i + 1].lower()
                i += 1
            i += 1

        if not from_code and not order_id:
            print()
            print(bold("  /txn-flow commands"))
            print(f"  {cyan('/txn-flow --from-code')}                    {dim('Scan code for state machines')}")
            print(f"  {cyan('/txn-flow --order-id ORD123 --env dev')}    {dim('Trace from ES logs')}")
            print(f"  {cyan('/txn-flow --from-code --format state')}     {dim('Mermaid state diagram')}")
            print(f"  {cyan('/txn-flow --from-code --format sequence')}  {dim('Mermaid sequence diagram')}")
            print()
            return None

        tracer = TxnFlowTracer(cwd=repo)

        if from_code:
            print(dim(f"  Scanning {repo} for state machines..."))
            flow = tracer.trace_from_code()
        else:
            print(dim(f"  Querying {env} logs for order {order_id}..."))
            flow = tracer.trace_from_logs(order_id, env=env)

        if not flow.steps:
            print(yellow("  No transaction steps found."))
            print()
            return None

        if fmt == "terminal":
            print(tracer.generate_terminal(flow))
        elif fmt in ("mermaid", "sequence"):
            print(tracer.generate_sequence_diagram(flow))
        elif fmt == "state":
            print(tracer.generate_state_diagram(flow))
        else:
            print(tracer.generate_terminal(flow))
        print()

    elif command in ("/migrate-tracing", "/otel-migrate"):
        from code_agents.observability.tracing_migration import (
            TracingMigrator,
            format_migration_plan,
            format_migration_result,
        )

        repo = state.get("repo_path", os.getcwd())
        parts = arg.strip().split() if arg else []

        try:
            migrator = TracingMigrator(repo)
        except FileNotFoundError as e:
            print(red(f"  {e}"))
            print()
            return None

        if "rollback" in parts:
            ok = migrator.rollback()
            if ok:
                print(green("  Rollback complete — files restored."))
            else:
                print(yellow("  No backup found."))
            print()
            return None

        print(dim(f"  Scanning {repo} for tracing patterns..."))
        plan = migrator.scan()
        print(format_migration_plan(plan))

        if not plan.patterns_found:
            print(dim("  No legacy tracing patterns found."))
            print()
            return None

        if "dry-run" in parts or "--dry-run" in parts:
            result = migrator.apply(plan, dry_run=True)
            print(dim("  (dry-run — no files changed)"))
            print(format_migration_result(result))
            return None

        if "apply" in parts or "--apply" in parts:
            result = migrator.apply(plan)
            print(format_migration_result(result))
            return None

        print(dim("  Use: /migrate-tracing apply | /migrate-tracing dry-run | /migrate-tracing rollback"))
        print()

    elif command in ("/idempotency", "/idempotency-audit"):
        from code_agents.domain.idempotency_audit import IdempotencyAuditor, format_idempotency_report

        repo = state.get("repo_path", os.getcwd())
        parts = arg.strip().split() if arg else []

        severity_filter = "all"
        output_format = "text"
        i = 0
        while i < len(parts):
            if parts[i] == "--severity" and i + 1 < len(parts):
                severity_filter = parts[i + 1].lower()
                i += 1
            elif parts[i] == "--format" and i + 1 < len(parts):
                output_format = parts[i + 1].lower()
                i += 1
            i += 1

        print(dim(f"  Scanning {repo} for payment endpoint idempotency issues..."))
        auditor = IdempotencyAuditor(cwd=repo)
        findings = auditor.audit()

        if severity_filter != "all":
            findings = [f for f in findings if f.severity == severity_filter]

        if output_format == "json":
            import json as _json
            data = [
                {"file": f.file, "line": f.line, "endpoint": f.endpoint,
                 "issue": f.issue, "severity": f.severity, "suggestion": f.suggestion}
                for f in findings
            ]
            print(_json.dumps(data, indent=2))
        else:
            print(format_idempotency_report(findings))

        crit = sum(1 for f in findings if f.severity == "critical")
        if crit:
            print(f"  {red(f'{crit} critical issue(s) found.')}")
        print()

    elif command in ("/dep-impact", "/impact"):
        from code_agents.domain.dep_impact import DependencyImpactScanner, format_impact_report

        repo = state.get("repo_path", os.getcwd())
        parts = arg.strip().split() if arg else []

        if not parts:
            print(yellow("  Usage: /dep-impact <package>==<version> [--check|--apply]"))
            print(dim("  Example: /dep-impact requests==3.0.0"))
            print()
            return None

        spec = parts[0]
        check_mode = "--check" in parts
        apply_mode = "--apply" in parts

        if "==" in spec:
            package, target_version = spec.split("==", 1)
        else:
            package = spec
            target_version = "latest"

        print(dim(f"  Scanning impact of {package} -> {target_version}..."))

        scanner = DependencyImpactScanner(
            cwd=repo,
            package=package,
            target_version=target_version,
            dry_run=not apply_mode,
        )
        report = scanner.scan()
        print(format_impact_report(report))

        if apply_mode and report.patches:
            patched = scanner.apply_patches()
            print(f"  {green(f'Applied {patched} patch(es).')}")
            print()
        elif check_mode and report.risk_level in ("high", "critical"):
            print(f"  {red(f'Risk: {report.risk_level.upper()} — upgrade may break your project.')}")
            print()

    elif command == "/review":
        from code_agents.reviews.code_review import (
            InlineCodeReview,
            format_annotated_diff,
            apply_fixes,
            to_json,
        )
        import json as _json

        parts = arg.split() if arg else []
        base = "main"
        fix = "--fix" in parts
        output_json = "--json" in parts
        category = "all"
        files_filter = None

        for idx, p in enumerate(parts):
            if p == "--base" and idx + 1 < len(parts):
                base = parts[idx + 1]
            elif p == "--category" and idx + 1 < len(parts):
                category = parts[idx + 1]
            elif p == "--files" and idx + 1 < len(parts):
                files_filter = [f.strip() for f in parts[idx + 1].split(",")]

        repo = state.get("repo_path", os.getcwd())

        print()
        print(bold(cyan("  AI Code Review — Inline Diff")))
        print(dim(f"  Reviewing {base}...HEAD"))
        if category != "all":
            print(dim(f"  Category filter: {category}"))
        print()

        reviewer = InlineCodeReview(cwd=repo, base=base, files=files_filter, category_filter=category)
        result = reviewer.run()

        if output_json:
            print(_json.dumps(to_json(result), indent=2))
        else:
            print(format_annotated_diff(result))

        if fix and result.findings:
            count = apply_fixes(result, repo)
            if count:
                print(green(f"  Applied {count} fix(es)"))
            else:
                print(dim("  No auto-fixable issues found"))
            print()

    elif command in ("/pci-scan", "/pci"):
        from code_agents.security.pci_scanner import PCIComplianceScanner, format_pci_report, pci_report_to_json
        import json as _json

        repo = state.get("repo_path", os.getcwd())
        parts = arg.split() if arg else []
        fmt = "text"
        severity_filter = "all"
        output_json = "--json" in parts

        for idx, p in enumerate(parts):
            if p == "--format" and idx + 1 < len(parts):
                fmt = parts[idx + 1].lower()
            elif p == "--severity" and idx + 1 < len(parts):
                severity_filter = parts[idx + 1].lower()

        if "--json" in parts:
            fmt = "json"

        print()
        print(bold(cyan("  PCI-DSS Compliance Scan")))
        print(dim(f"  Scanning {repo}..."))
        print()

        scanner = PCIComplianceScanner(cwd=repo)
        report = scanner.scan()

        # Filter by severity
        if severity_filter != "all":
            severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            threshold = severity_order.get(severity_filter, 3)
            report.findings = [
                f for f in report.findings
                if severity_order.get(f.severity, 3) <= threshold
            ]

        if fmt == "json":
            print(_json.dumps(pci_report_to_json(report), indent=2))
        else:
            print(format_pci_report(report))
        print()

    elif command in ("/owasp-scan", "/owasp"):
        from code_agents.security.owasp_scanner import OWASPScanner, format_owasp_report, owasp_report_to_json
        import json as _json

        repo = state.get("repo_path", os.getcwd())
        parts = arg.split() if arg else []
        fmt = "text"
        severity_filter = "all"

        for idx, p in enumerate(parts):
            if p == "--format" and idx + 1 < len(parts):
                fmt = parts[idx + 1].lower()
            elif p == "--severity" and idx + 1 < len(parts):
                severity_filter = parts[idx + 1].lower()

        if "--json" in parts:
            fmt = "json"

        print()
        print(bold(cyan("  OWASP Top 10 Security Scan")))
        print(dim(f"  Scanning {repo}..."))
        print()

        scanner = OWASPScanner(cwd=repo)
        report = scanner.scan()

        # Filter by severity
        if severity_filter != "all":
            severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            threshold = severity_order.get(severity_filter, 3)
            report.findings = [
                f for f in report.findings
                if severity_order.get(f.severity, 3) <= threshold
            ]

        if fmt == "json":
            print(_json.dumps(owasp_report_to_json(report), indent=2))
        else:
            print(format_owasp_report(report))
        print()

    elif command in ("/validate-states", "/state-machine"):
        from code_agents.domain.state_machine_validator import (
            StateMachineValidator,
            format_validation_report,
        )
        import json as _json

        repo = state.get("repo_path", os.getcwd())
        parts = arg.strip().split() if arg else []

        output_format = "text"
        for idx, p in enumerate(parts):
            if p == "--format" and idx + 1 < len(parts):
                output_format = parts[idx + 1].lower()

        print()
        print(bold(cyan("  Transaction State Machine Validator")))
        print(dim(f"  Scanning {repo}..."))
        print()

        validator = StateMachineValidator(cwd=repo)
        machines = validator.extract()

        if not machines:
            print(yellow("  No state machines found in the codebase."))
            print()
            return None

        all_findings = []
        for sm in machines:
            findings = validator.validate(sm)
            all_findings.extend(findings)

        if output_format == "json":
            data = {
                "machines": [
                    {
                        "name": sm.name,
                        "states": [s.name for s in sm.states],
                        "initial_state": sm.initial_state,
                        "terminal_states": sm.terminal_states,
                        "transitions": [
                            {"from": t.from_state, "to": t.to_state, "trigger": t.trigger}
                            for t in sm.transitions
                        ],
                    }
                    for sm in machines
                ],
                "findings": [
                    {"severity": f.severity, "message": f.message, "states_involved": f.states_involved}
                    for f in all_findings
                ],
            }
            print(_json.dumps(data, indent=2))
        elif output_format == "mermaid":
            for sm in machines:
                print(f"  {bold(sm.name)}")
                print()
                print(validator.generate_diagram(sm))
                print()
        else:
            print(format_validation_report(machines, all_findings))

        crit = sum(1 for f in all_findings if f.severity == "critical")
        if crit:
            print(f"  {red(f'{crit} critical issue(s) found.')}")
        print()

    elif command in ("/api-docs", "/apidocs"):
        from code_agents.api.api_docs import APIDocGenerator, format_api_summary

        repo = state.get("repo_path", os.getcwd())
        parts = arg.strip().split() if arg else []

        fmt = "terminal"
        output_path = ""
        i = 0
        while i < len(parts):
            if parts[i] == "--format" and i + 1 < len(parts):
                fmt = parts[i + 1].lower()
                i += 1
            elif parts[i] == "--output" and i + 1 < len(parts):
                output_path = parts[i + 1]
                i += 1
            i += 1

        print()
        print(bold(cyan("  Automated API Documentation Generator")))
        print(dim(f"  Scanning {repo}..."))
        print()

        gen = APIDocGenerator(cwd=repo)
        result = gen.scan()

        if not result.routes:
            print(yellow("  No API routes discovered."))
            print(dim("  Supports: FastAPI, Flask, Spring Boot, Express"))
            print()
            return None

        if fmt == "openapi":
            import json as _json
            text = _json.dumps(gen.generate_openapi(result), indent=2)
        elif fmt == "markdown":
            text = gen.generate_markdown(result)
        elif fmt == "html":
            text = gen.generate_html(result)
        else:
            text = format_api_summary(result)

        if output_path:
            from pathlib import Path as _Path
            out = _Path(output_path).resolve()
            out.write_text(text, encoding="utf-8")
            print(green(f"  Written to {out}"))
        else:
            print(text)
        print()

    elif command in ("/translate", "/code-translate"):
        from code_agents.knowledge.code_translator import CodeTranslator, format_translation

        repo = state.get("repo_path", os.getcwd())
        parts = arg.strip().split() if arg else []

        if not parts:
            print(yellow("  Usage: /translate <file> --to <lang> [--output <path>]"))
            print(dim("  Example: /translate src/utils.py --to javascript"))
            print(dim("  Supported: python, javascript, typescript, java, go"))
            print()
            return None

        source_file = parts[0]
        target_lang = ""
        output_path = ""
        i = 1
        while i < len(parts):
            if parts[i] == "--to" and i + 1 < len(parts):
                target_lang = parts[i + 1]
                i += 1
            elif parts[i] == "--output" and i + 1 < len(parts):
                output_path = parts[i + 1]
                i += 1
            i += 1

        if not target_lang:
            print(red("  Missing --to <lang>."))
            print()
            return None

        translator = CodeTranslator(cwd=repo)
        result = translator.translate_file(source_file, target_lang)

        if output_path:
            from pathlib import Path as _Path
            out = _Path(output_path).resolve()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(result.code, encoding="utf-8")
            print(green(f"  Written to {out}"))
        else:
            print(format_translation(result))

        if result.warnings:
            for w in result.warnings:
                print(f"  {yellow(w)}")
        print()

    elif command in ("/settlement", "/settle"):
        parts = arg.split() if arg else []
        if not parts:
            print(yellow("  Usage: /settlement --file data.csv [--format visa|mastercard|upi|auto] [--compare bank.csv] [--output adj.csv]"))
            print()
            return None

        file_path = None
        compare_file = None
        fmt = "auto"
        output_path = None
        i = 0
        while i < len(parts):
            if parts[i] == "--file" and i + 1 < len(parts):
                file_path = parts[i + 1]; i += 1
            elif parts[i] == "--format" and i + 1 < len(parts):
                fmt = parts[i + 1].lower(); i += 1
            elif parts[i] == "--compare" and i + 1 < len(parts):
                compare_file = parts[i + 1]; i += 1
            elif parts[i] == "--output" and i + 1 < len(parts):
                output_path = parts[i + 1]; i += 1
            i += 1

        if not file_path:
            print(red("  Missing --file flag"))
            print()
            return None

        from code_agents.domain.settlement_parser import (
            SettlementParser, SettlementValidator, format_settlement_report,
        )

        parser = SettlementParser()
        validator = SettlementValidator()

        try:
            records = parser.parse(file_path, format=fmt)
        except (FileNotFoundError, ValueError) as exc:
            print(red(f"  Error: {exc}"))
            print()
            return None

        report = validator.validate(records)
        print(format_settlement_report(report))

        if compare_file:
            try:
                bank_records = parser.parse(compare_file, format=fmt)
            except (FileNotFoundError, ValueError) as exc:
                print(red(f"  Error loading comparison file: {exc}"))
                print()
                return None

            discrepancies = validator.compare(records, bank_records)
            if discrepancies:
                print(yellow(f"\n  {len(discrepancies)} discrepancies found"))
                for d in discrepancies[:20]:
                    print(f"    [{d.discrepancy_type.upper():10s}] {d.txn_id}: {d.field}")
                if output_path:
                    adj_csv = validator.generate_adjustments(discrepancies)
                    with open(output_path, "w", encoding="utf-8") as f:
                        f.write(adj_csv)
                    print(green(f"  Adjustments written to: {output_path}"))
            else:
                print(green("  No discrepancies — files match!"))
        print()

    elif command in ("/batch", "/batch-ops"):
        from code_agents.devops.batch_ops import BatchOperator, format_batch_result

        repo = state.get("repo_path", os.getcwd())
        parts = arg.strip().split() if arg else []

        instruction = ""
        files: list[str] = []
        pattern = ""
        dry_run = "--dry-run" in parts
        parallel = 4

        i = 0
        while i < len(parts):
            if parts[i] == "--instruction" and i + 1 < len(parts):
                instruction = parts[i + 1]
                i += 1
            elif parts[i] == "--files":
                i += 1
                while i < len(parts) and not parts[i].startswith("--"):
                    files.append(parts[i])
                    i += 1
                continue
            elif parts[i] == "--pattern" and i + 1 < len(parts):
                pattern = parts[i + 1]
                i += 1
            elif parts[i] == "--parallel" and i + 1 < len(parts):
                try:
                    parallel = int(parts[i + 1])
                except ValueError:
                    pass
                i += 1
            i += 1

        if not instruction:
            print(yellow('  Usage: /batch --instruction "add docstrings" [--files a.py b.py] [--pattern "*.py"] [--dry-run] [--parallel N]'))
            print()
            return None

        print(dim(f"  Processing files in {repo}..."))
        try:
            op = BatchOperator(cwd=repo)
            result = op.run(
                instruction=instruction,
                files=files or None,
                pattern=pattern,
                max_parallel=parallel,
                dry_run=dry_run,
            )
            print(format_batch_result(result))
        except ValueError as exc:
            print(red(f"  Error: {exc}"))
        print()

    elif command in ("/index", "/rag-index"):
        from code_agents.knowledge.rag_context import VectorStore
        repo = state.get("repo_path", os.getcwd())
        vs = VectorStore(repo)
        if arg == "--stats":
            stats = vs.stats()
            for k, v in stats.items():
                print(f"  {bold(k)}: {v}")
        else:
            force = "--force" in (arg or "")
            print(dim("  Building RAG index..."))
            count = vs.build(force=force)
            print(f"  {green('✓')} Indexed {count} chunks")
        print()

    elif command in ("/tech-debt", "/debt-scan", "/debt"):
        from code_agents.reviews.tech_debt import TechDebtTracker, format_debt_report
        import json as _json

        repo = state.get("repo_path", os.getcwd())
        parts = arg.strip().split() if arg else []
        json_output = "--json" in parts
        save_snapshot = "--save" in parts

        print()
        print(bold(cyan("  Tech Debt Tracker")))
        print(dim(f"  Scanning {repo}..."))
        print()

        tracker = TechDebtTracker(cwd=repo)
        report = tracker.scan()

        if json_output:
            import dataclasses
            print(_json.dumps(dataclasses.asdict(report), indent=2))
        else:
            print(format_debt_report(report))

        if save_snapshot:
            tracker.save_snapshot(report)
            print(green("  Snapshot saved for trend tracking."))
        print()

    elif command in ("/deadcode", "/dead-code"):
        from code_agents.analysis.deadcode import scan_dead_code
        repo = state.get("repo_path", os.getcwd())
        print(dim("  Scanning for dead code..."))
        report = scan_dead_code(repo)
        print(report)
        print()

    elif command in ("/dead-code-eliminate", "/eliminate-dead", "/dce"):
        from code_agents.reviews.dead_code_eliminator import DeadCodeEliminator, format_dead_code_report
        repo = state.get("repo_path", os.getcwd())
        apply_mode = arg and "--apply" in arg
        dry_run = arg and "--dry-run" in arg
        print(dim("  Running cross-file dead code elimination scan..."))
        eliminator = DeadCodeEliminator(cwd=repo)
        report = eliminator.scan()
        print(format_dead_code_report(report))
        if dry_run and report.safe_to_remove:
            print(yellow("\n  [dry-run] Would remove:"))
            for f in report.safe_to_remove:
                print(f"    - {f.file}:{f.line} ({f.kind}: {f.name})")
        elif apply_mode and report.safe_to_remove:
            count = eliminator.apply(report.safe_to_remove)
            print(green(f"\n  Removed {count} dead code items. Backups: *.deadcode.bak"))
        print()

    elif command == "/complexity":
        from code_agents.analysis.complexity import analyze_complexity
        repo = state.get("repo_path", os.getcwd())
        print(dim("  Analyzing complexity..."))
        report = analyze_complexity(repo, arg or "")
        print(report)
        print()

    elif command in ("/security", "/security-scan"):
        from code_agents.analysis.security_scanner import SecurityScanner
        repo = state.get("repo_path", os.getcwd())
        print(dim("  Running security scan..."))
        scanner = SecurityScanner(repo)
        report = scanner.scan()
        print(scanner.format_report(report))
        print()

    elif command == "/coverage":
        from code_agents.tools.auto_coverage import get_coverage_report
        repo = state.get("repo_path", os.getcwd())
        report = get_coverage_report(repo)
        print(report)
        print()

    elif command in ("/screenshot", "/s2c", "/screenshot-to-code"):
        from code_agents.ui.screenshot_to_code import ScreenshotToCode, format_generated_ui

        repo = state.get("repo_path", os.getcwd())
        parts = arg.strip().split() if arg else []
        image_path = ""
        framework = ""
        description = ""
        output_path = ""
        i = 0
        desc_parts: list[str] = []
        while i < len(parts):
            if parts[i] in ("--image", "-i") and i + 1 < len(parts):
                image_path = parts[i + 1]; i += 2
            elif parts[i] in ("--framework", "-f") and i + 1 < len(parts):
                framework = parts[i + 1]; i += 2
            elif parts[i] in ("--description", "-d") and i + 1 < len(parts):
                description = parts[i + 1]; i += 2
            elif parts[i] in ("--output", "-o") and i + 1 < len(parts):
                output_path = parts[i + 1]; i += 2
            else:
                desc_parts.append(parts[i]); i += 1
        if not description and desc_parts:
            description = " ".join(desc_parts)

        if not image_path and not description:
            print(f"  {yellow('Usage: /screenshot --description \"login form\" [--framework react|vue|html] [--output file]')}")
            print(f"  {dim('Or: /screenshot --image mockup.png')}")
            print()
        else:
            gen = ScreenshotToCode(cwd=repo)
            result = gen.generate(image_path=image_path, framework=framework, description=description)
            if output_path:
                from pathlib import Path as _Path
                _Path(output_path).write_text(result.code)
                print(f"  {green(f'Written to {output_path}')} ({len(result.code)} bytes)")
            else:
                output = format_generated_ui(result)
                for line in output.splitlines():
                    print(f"  {line}")
            print()

    elif command in ("/imports", "/import-optimizer", "/optimize-imports"):
        from code_agents.reviews.import_optimizer import ImportOptimizer, format_import_report
        import json as _json

        repo = state.get("repo_path", os.getcwd())
        parts = arg.strip().split() if arg else []
        do_fix = "--fix" in parts
        json_output = "--json" in parts
        target = ""
        for p in parts:
            if not p.startswith("-"):
                target = p
                break

        print()
        print(bold(cyan("  Import Optimizer")))
        print(dim(f"  Scanning {repo}..."))
        print()

        optimizer = ImportOptimizer(cwd=repo)

        if do_fix:
            count = optimizer.fix(target=target)
            if count:
                print(green(f"  Fixed {count} unused import(s)."))
            else:
                print(dim("  No unused imports to fix."))
            print()
        else:
            findings = optimizer.scan(target=target)
            if json_output:
                data = [
                    {
                        "file": f.file, "line": f.line,
                        "import_statement": f.import_statement,
                        "issue": f.issue, "severity": f.severity,
                        "suggestion": f.suggestion,
                    }
                    for f in findings
                ]
                print(_json.dumps(data, indent=2))
            else:
                print(format_import_report(findings))
            print()

    else:
        return "_not_handled"

    return None


def _handle_slack_command(arg: str, state: dict) -> None:
    """Handle /slack subcommands: test, send, status, channels."""
    import asyncio

    parts = arg.strip().split(maxsplit=1) if arg else []
    sub = parts[0].lower() if parts else ""
    rest = parts[1] if len(parts) > 1 else ""

    if sub == "test":
        webhook_url = rest or os.getenv("CODE_AGENTS_SLACK_WEBHOOK_URL", "")
        if not webhook_url:
            print(red("  No webhook URL. Set CODE_AGENTS_SLACK_WEBHOOK_URL or: /slack test <url>"))
            print()
            return
        print(dim("  Sending test message..."))
        from code_agents.domain.notifications import send_slack
        success = asyncio.run(
            send_slack("🧪 *Code Agents* — Slack webhook test from chat!", webhook_url=webhook_url)
        )
        if success:
            print(f"  {green('✓ Test message sent!')}")
        else:
            print(f"  {red('✗ Failed to send.')}")
        print()

    elif sub == "send":
        if not rest:
            print(yellow("  Usage: /slack send <message>"))
            print()
            return
        webhook_url = os.getenv("CODE_AGENTS_SLACK_WEBHOOK_URL", "")
        if not webhook_url:
            print(red("  No webhook URL configured."))
            print()
            return
        from code_agents.domain.notifications import send_slack
        success = asyncio.run(send_slack(rest, webhook_url=webhook_url))
        if success:
            print(f"  {green('✓ Sent.')}")
        else:
            print(f"  {red('✗ Failed.')}")
        print()

    elif sub == "status":
        bot_token = bool(os.getenv("CODE_AGENTS_SLACK_BOT_TOKEN", ""))
        signing_secret = bool(os.getenv("CODE_AGENTS_SLACK_SIGNING_SECRET", ""))
        webhook = bool(os.getenv("CODE_AGENTS_SLACK_WEBHOOK_URL", ""))
        channel_map = os.getenv("CODE_AGENTS_SLACK_CHANNEL_MAP", "")

        print()
        print(bold("  Slack Status"))
        _ok = lambda v: green("✓") if v else red("✗")
        print(f"  {_ok(bot_token)} Bot Token   {_ok(signing_secret)} Signing Secret   {_ok(webhook)} Webhook URL")
        if channel_map:
            print(f"  {green('✓')} Channel Map: {dim(channel_map)}")
        print()

    elif sub == "channels":
        channel_map = os.getenv("CODE_AGENTS_SLACK_CHANNEL_MAP", "")
        if not channel_map:
            print(dim("  No channel mappings. Set CODE_AGENTS_SLACK_CHANNEL_MAP"))
            print()
            return
        from code_agents.integrations.slack_bot import SlackBot
        bot = SlackBot()
        print()
        for ch, agent in bot._channel_map.items():
            print(f"  {cyan(ch)} → {green(agent)}")
        print()

    else:
        print()
        print(bold("  /slack commands"))
        print(f"  {cyan('/slack test')}          {dim('Send a test webhook message')}")
        print(f"  {cyan('/slack test <url>')}    {dim('Test a specific webhook URL')}")
        print(f"  {cyan('/slack send <msg>')}    {dim('Send a message via webhook')}")
        print(f"  {cyan('/slack status')}        {dim('Show Slack config status')}")
        print(f"  {cyan('/slack channels')}      {dim('Show channel-agent mappings')}")
        print()


def _handle_commands_smart(arg: str, state: dict) -> None:
    """Smart /commands with agent routing — fuzzy-match query to best agent + commands."""
    from code_agents.ui.command_advisor import CommandAdvisor, format_all_commands

    advisor = CommandAdvisor()
    query = arg.strip()

    suggestions = advisor.suggest(query)
    if suggestions:
        print()
        print(bold(f"  Commands matching '{query}':"))
        print()
        print(advisor.format_suggestions(suggestions))
    else:
        # No matches — show full reference
        print()
        print(yellow(f"  No commands matched '{query}'."))
        print(format_all_commands())
    print()


def _handle_commands_browser(arg: str, state: dict) -> None:
    """Interactive command browser — category → command → subcommand drill-down."""
    from .command_panel import show_panel
    from .command_panel_options import (
        get_commands_categories,
        get_commands_for_category,
        get_subcommands_for_command,
    )

    # If arg is given, jump directly to that category or command
    if arg:
        _run_cli_command(arg.strip(), state)
        return

    # Level 1: Category selection
    while True:
        title, subtitle, cat_opts = get_commands_categories()
        cat_idx = show_panel(title, subtitle, cat_opts)
        if cat_idx is None:
            print(f"  {dim('Cancelled.')}")
            print()
            return

        category = cat_opts[cat_idx]["name"]

        # Level 2: Command selection within category
        while True:
            cmd_title, cmd_subtitle, cmd_opts = get_commands_for_category(category)
            cmd_idx = show_panel(cmd_title, cmd_subtitle, cmd_opts)
            if cmd_idx is None:
                break  # Back to categories

            command = cmd_opts[cmd_idx]["name"]
            subs = get_subcommands_for_command(category, command)

            if not subs:
                # No subcommands — execute directly
                _run_cli_command(command, state)
                return

            # Level 3: Subcommand/flag selection
            sub_opts = [{"name": s, "description": "", "active": False} for s in subs]
            sub_opts.insert(0, {"name": f"(run bare: code-agents {command})", "description": "No flags", "active": False})

            sub_idx = show_panel(
                f"{command}",
                f"Select flag/subcommand, or run bare.",
                sub_opts,
            )
            if sub_idx is None:
                continue  # Back to command list
            if sub_idx == 0:
                _run_cli_command(command, state)
            else:
                sub = subs[sub_idx - 1]
                _run_cli_command(f"{command} {sub}", state)
            return


def _run_cli_command(cmd_str: str, state: dict) -> None:
    """Execute a code-agents CLI command from the /commands browser."""
    import subprocess

    repo = state.get("repo_path", os.getcwd())
    full_cmd = f"code-agents {cmd_str}"

    print()
    print(f"  {bold(cyan(f'> {full_cmd}'))}")
    print()

    # Commands that need interactive terminal — just show the command
    interactive_cmds = {"chat", "setup", "init"}
    base_cmd = cmd_str.split()[0] if cmd_str else ""
    if base_cmd in interactive_cmds:
        print(f"  {yellow('Interactive command — run in your terminal:')}")
        print(f"    {dim(full_cmd)}")
        print()
        return

    try:
        result = subprocess.run(
            ["code-agents"] + cmd_str.split(),
            capture_output=True, text=True, timeout=60,
            cwd=repo,
        )
        output = (result.stdout or "") + (result.stderr or "")
        if output.strip():
            for line in output.strip().splitlines():
                print(f"  {line}")
        print()
    except subprocess.TimeoutExpired:
        print(f"  {red('Command timed out (60s)')}")
        print()
    except FileNotFoundError:
        print(f"  {yellow('Run in terminal:')} {dim(full_cmd)}")
        print()
