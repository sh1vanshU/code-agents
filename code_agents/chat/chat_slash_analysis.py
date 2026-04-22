"""Code analysis slash commands: /investigate, /blame, /generate-tests, /refactor, /deps, /config-diff, /flags, /pr-preview, /impact, /solve, /review-reply, /qa-suite, /debug, /review."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.chat.chat_slash_analysis")

from .chat_ui import bold, green, yellow, red, cyan, dim


def _handle_analysis(command: str, arg: str, state: dict, url: str) -> Optional[str]:
    """Handle code analysis slash commands."""

    if command == "/generate-tests":
        if not arg:
            print(yellow("  Usage: /generate-tests <file>"))
            print(dim("  Analyzes a source file and generates unit + integration tests."))
            print(dim("  Example: /generate-tests src/auth/login.py"))
            print()
            return None

        from code_agents.generators.test_generator import TestGenerator, format_analysis

        file_path = arg.strip()
        repo = state.get("repo_path") or os.getcwd()

        # Resolve relative path
        full_path = file_path if os.path.isabs(file_path) else os.path.join(repo, file_path)
        if not os.path.isfile(full_path):
            print(red(f"  File not found: {file_path}"))
            print(dim(f"  Resolved to: {full_path}"))
            print()
            return None

        try:
            gen = TestGenerator(file_path, repo)
            if gen.language == "unknown":
                print(yellow(f"  Unsupported file type: {Path(file_path).suffix}"))
                print(dim("  Supported: .py, .java, .js, .ts, .go, .rb, .kt, .scala"))
                print()
                return None

            analysis = gen.analyze_source()

            # Show analysis summary
            print()
            print(bold("  Test Generation Analysis"))
            print(format_analysis(analysis))
            test_path = gen.generate_test_path()
            print(f"  Test file: {cyan(test_path)}")
            print()

            logger.info(
                "generate-tests: file=%s lang=%s framework=%s classes=%d funcs=%d deps=%d",
                file_path, gen.language, gen.framework,
                len(analysis["classes"]), len(analysis["functions"]),
                len(analysis["dependencies"]),
            )

            # Build prompt and inject as user message for the agent
            prompt = gen.build_prompt(analysis)
            state["_exec_feedback"] = {
                "command": f"/generate-tests {file_path}",
                "output": prompt,
            }
            return "exec_feedback"

        except OSError as e:
            print(red(f"  Error reading file: {e}"))
            print()
            return None

    elif command == "/qa-suite":
        from code_agents.generators.qa_suite_generator import QASuiteGenerator, format_analysis

        repo = state.get("repo_path") or os.getcwd()

        print()
        print(bold("  QA Suite Generator"))
        print(dim(f"  Analyzing {repo}..."))
        print()

        try:
            gen = QASuiteGenerator(cwd=repo)
            analysis = gen.analyze()

            if not analysis.language:
                print(yellow("  Could not detect project language/framework."))
                print(dim("  Supported: Java (Maven/Gradle), Python, JS, Go"))
                print()
                return None

            print(format_analysis(analysis))
            print()

            # Generate test suite
            generated = gen.generate_suite()

            if not generated:
                print(yellow("  No test files generated (no endpoints/services discovered)."))
                print()
                return None

            logger.info(
                "qa-suite: lang=%s framework=%s endpoints=%d services=%d generated=%d",
                analysis.language, analysis.framework,
                len(analysis.endpoints), len(analysis.services), len(generated),
            )

            # Build agent prompt and inject as exec_feedback
            prompt = gen.build_agent_prompt()

            # Auto-switch to qa-regression agent if not already
            current_agent = state.get("agent", "")
            if current_agent != "qa-regression":
                print(dim("  Switching to qa-regression agent..."))
                state["agent"] = "qa-regression"

            state["_exec_feedback"] = {
                "command": "/qa-suite",
                "output": prompt,
            }
            return "exec_feedback"

        except Exception as e:
            logger.exception("qa-suite error: %s", e)
            print(red(f"  Error: {e}"))
            print()
            return None

    elif command == "/blame":
        if not arg or len(arg.split()) < 2:
            print(yellow("  Usage: /blame <file> <line>"))
            print(dim("  Deep blame: who changed it, what PR, what Jira ticket, full context."))
            print()
            return None
        blame_parts = arg.split()
        blame_file = blame_parts[0]
        try:
            blame_line = int(blame_parts[1])
        except ValueError:
            print(yellow(f"  Invalid line number: {blame_parts[1]}"))
            return None
        from code_agents.git_ops.blame_investigator import BlameInvestigator, format_blame
        repo = state.get("repo_path") or os.getcwd()
        print()
        print(dim(f"  Investigating: {blame_file}:{blame_line}"))
        print(dim("  Running git blame, searching PRs, extracting Jira tickets..."))
        investigator = BlameInvestigator(cwd=repo)
        blame_result = investigator.investigate(blame_file, blame_line)
        print()
        print(format_blame(blame_result))
        print()
        # Feed blame to agent for deeper analysis
        state["_exec_feedback"] = {
            "command": f"/blame {blame_file} {blame_line}",
            "output": format_blame(blame_result),
        }
        return "exec_feedback"

    elif command == "/investigate":
        if not arg:
            print(yellow("  Usage: /investigate <error pattern>"))
            print(dim("  Searches logs, correlates with deploys, finds root cause."))
            print()
            return None
        from code_agents.observability.log_investigator import LogInvestigator, format_investigation
        repo = state.get("repo_path") or os.getcwd()
        print()
        print(dim(f"  Investigating: {arg}"))
        print(dim("  Searching logs, correlating deploys, checking commits..."))
        investigator = LogInvestigator(query=arg, cwd=repo)
        inv = investigator.investigate()
        print()
        print(format_investigation(inv))
        print()
        # Feed investigation to agent for deeper analysis
        state["_exec_feedback"] = {
            "command": f"/investigate {arg}",
            "output": format_investigation(inv),
        }
        return "exec_feedback"

    elif command == "/review-reply":
        from code_agents.reviews.review_responder import ReviewResponder, format_review_comments
        repo = state.get("repo_path") or os.getcwd()
        pr_number = int(arg) if arg and arg.isdigit() else None
        print()
        print(dim("  Fetching PR review comments..."))
        responder = ReviewResponder(cwd=repo)
        comments = responder.get_pr_comments(pr_number=pr_number)
        if not comments:
            print(yellow("  No PR comments found."))
            print(dim("  Usage: /review-reply [PR#]"))
            print(dim("  Tip: Make sure you're on a branch with an active PR."))
            print()
            return None
        print(bold("  PR Review Comments:"))
        print(format_review_comments(comments))
        print()
        # Build prompt for each unresolved comment and feed to agent
        prompts = []
        for c in comments:
            ctx = responder.get_source_context(c.file_path, c.line)
            prompts.append(responder.build_reply_prompt(c, ctx))
        combined = "\n---\n".join(prompts)
        state["_exec_feedback"] = {
            "command": f"/review-reply {pr_number or 'auto'}",
            "output": combined,
        }
        return "exec_feedback"

    elif command == "/refactor":
        if not arg:
            print(yellow("  Usage: /refactor <file>"))
            print(dim("  Analyzes code smells, suggests refactoring steps, estimates risk."))
            print()
            return None
        from code_agents.tools.refactor_planner import RefactorPlanner, format_refactor_plan
        repo = state.get("repo_path", ".")
        planner = RefactorPlanner(cwd=repo)
        plan = planner.analyze(arg)
        output = format_refactor_plan(plan)
        print(output)

    elif command == "/deps":
        if not arg:
            print(yellow("  Usage: /deps <class-or-module>"))
            print(dim("  Show dependency tree: who calls it, what it calls, circular deps."))
            print()
            return None
        from code_agents.analysis.dependency_graph import DependencyGraph
        repo = state.get("repo_path", os.getcwd())
        print(dim(f"  Scanning {repo}..."))
        dg = DependencyGraph(repo)
        dg.build_graph()
        matches = dg._resolve_name(arg.strip())
        if not matches:
            print(red(f"  '{arg}' not found in dependency graph."))
            print(dim(f"  Known modules: {len(dg.all_names)}"))
            # Suggest close matches
            lower = arg.strip().lower()
            suggestions = [n for n in sorted(dg.all_names) if lower in n.lower()][:5]
            if suggestions:
                print(dim(f"  Did you mean: {', '.join(suggestions)}"))
            print()
            return None
        output = dg.format_tree(arg.strip())
        print()
        print(output)
        print()

    elif command == "/config-diff":
        from code_agents.analysis.config_drift import ConfigDriftDetector, format_drift_report
        cwd = state.get("repo_path", os.getcwd())
        detector = ConfigDriftDetector(cwd)
        configs = detector.load_configs()
        if not configs:
            print(yellow("  No environment configs detected."))
            print(dim("  Supports: application-{env}.yml, .env.{env}, config/{env}/, k8s ConfigMaps"))
        else:
            env_args = arg.split() if arg else []
            if len(env_args) == 2:
                env_a, env_b = env_args[0], env_args[1]
                if env_a not in configs or env_b not in configs:
                    available = ', '.join(sorted(configs.keys()))
                    print(red(f"  Environment not found. Available: {available}"))
                else:
                    diff = detector.compare(env_a, env_b)
                    from code_agents.analysis.config_drift import DriftReport
                    report = DriftReport(environments=[env_a, env_b], diffs=[diff])
                    print(format_drift_report(report))
            else:
                report = detector.compare_all()
                print(format_drift_report(report))
        print()

    elif command == "/flags":
        from code_agents.analysis.feature_flags import FeatureFlagScanner, format_flag_report
        cwd = state.get("repo_path", os.getcwd())
        print(dim(f"  Scanning {cwd} for feature flags..."))
        scanner = FeatureFlagScanner(cwd=cwd)
        report = scanner.scan()
        if report.total_flags == 0:
            print(yellow("  No feature flags detected."))
            print(dim("  Scans .env files, Java @Value annotations, YAML configs, Python os.getenv"))
        else:
            stale_only = arg and arg.strip() == "--stale"
            if stale_only:
                if report.stale_flags:
                    print(bold(f"  Stale Flags ({len(report.stale_flags)}):"))
                    for flag in report.stale_flags:
                        print(f"    x {flag.name} ({flag.file}:{flag.line})")
                else:
                    print(green("  No stale flags found."))
            else:
                print(format_flag_report(report))
        print()

    elif command == "/pr-preview":
        from code_agents.tools.pr_preview import PRPreview
        cwd = state.get("repo_path", os.getcwd())
        base = arg.strip() if arg else "main"
        preview = PRPreview(cwd=cwd, base=base)
        commits = preview.get_commits()
        if not commits:
            print(yellow(f"  No commits found ahead of {base}."))
            print(dim(f"  Make sure you're on a feature branch with commits not in {base}."))
        else:
            print(preview.format_preview())
        print()

    elif command == "/impact":
        if not arg:
            print(yellow("  Usage: /impact <file>"))
            print(dim("  Show what's affected: dependents, tests, endpoints, risk level."))
            print()
            return None
        from code_agents.analysis.impact_analysis import ImpactAnalyzer, format_impact_report
        repo = state.get("repo_path", os.getcwd())
        print(dim(f"  Scanning {repo}..."))
        analyzer = ImpactAnalyzer(cwd=repo)
        report = analyzer.analyze(arg.strip())
        print()
        print(format_impact_report(report))
        print()

    elif command == "/solve":
        if not arg:
            print("  Usage: /solve <describe your problem>")
            print("  Example: /solve I need to deploy my service to staging")
            print("  Example: /solve production is throwing NullPointerException")
            print("  Example: /solve how do I improve test coverage")
            print()
        else:
            from code_agents.knowledge.problem_solver import ProblemSolver, format_problem_analysis
            solver = ProblemSolver()
            analysis = solver.analyze(arg)
            print(format_problem_analysis(analysis))

            # Offer to execute recommended action
            if analysis.recommended:
                r = analysis.recommended
                if r.action_type == "agent":
                    print(f"\n  Type /agent {r.action} to switch to this agent")
                elif r.action_type == "slash":
                    print(f"\n  Type {r.action} to execute")
                elif r.action_type == "command":
                    print(f"\n  Run in terminal: {r.action}")
            print()

    elif command == "/kb":
        from code_agents.knowledge.knowledge_base import KnowledgeBase, format_kb_results
        repo = state.get("repo_path", os.getcwd())
        kb = KnowledgeBase(cwd=repo)

        if arg == "--rebuild":
            count = kb.rebuild_index()
            print(f"  KB rebuilt: {count} entries indexed")
        elif arg == "--stats":
            sources: dict[str, int] = {}
            if not kb.entries:
                kb.rebuild_index()
            for e in kb.entries:
                sources[e.source] = sources.get(e.source, 0) + 1
            print(f"  KB: {len(kb.entries)} entries")
            for src, count in sorted(sources.items()):
                print(f"    {src}: {count}")
        elif arg:
            results = kb.search(arg)
            print(format_kb_results(results, arg))
        else:
            print("  Usage: /kb <search-term>")
            print("         /kb --rebuild    Re-index knowledge base")
            print("         /kb --stats      Show KB statistics")
        print()

    elif command == "/debug":
        import asyncio
        from code_agents.observability.debug_engine import DebugEngine, format_debug_result

        if not arg:
            print(yellow("  Usage: /debug <test-or-error-description>"))
            print(dim("  Examples:"))
            print(dim("    /debug tests/test_auth.py::test_login"))
            print(dim("    /debug pytest tests/test_foo.py -x"))
            print(dim('    /debug "AttributeError in login()"'))
            print(dim("    /debug --no-fix tests/test_auth.py   (analyze only)"))
            print()
            return None

        # Parse flags
        parts = arg.split()
        auto_fix = "--no-fix" not in parts
        auto_commit = "--commit" in parts
        bug_input = " ".join(p for p in parts if p not in ("--no-fix", "--commit"))

        repo = state.get("repo_path") or os.getcwd()
        engine = DebugEngine(cwd=repo, auto_fix=auto_fix, auto_commit=auto_commit)

        print()
        print(bold(cyan("  Autonomous Debug Engine")))
        print(f"  Input: {bug_input}")
        print(f"  Auto-fix: {'ON' if auto_fix else 'OFF'}")
        print()

        def progress(status, msg):
            print(f"  [{status.upper():>12}] {msg}")

        result = asyncio.run(engine.run(bug_input, progress_callback=progress))
        format_debug_result(result)

        if result.is_resolved:
            return f"Bug fixed: {result.root_cause}"
        return None

    elif command == "/review":
        from code_agents.reviews.review_autofix import ReviewAutoFixer, format_autofix_report

        parts = arg.split() if arg else []
        fix = "--fix" in parts
        post_comments = "--post" in parts
        severity_filter = ""
        pr_id = ""

        for i, p in enumerate(parts):
            if p == "--severity" and i + 1 < len(parts):
                severity_filter = parts[i + 1]
            if p == "--pr" and i + 1 < len(parts):
                pr_id = parts[i + 1]

        base = "main"
        for i, p in enumerate(parts):
            if p == "--base" and i + 1 < len(parts):
                base = parts[i + 1]

        repo = state.get("repo_path") or os.getcwd()

        print()
        print(bold(cyan("  AI Code Review + Auto-Fix")))
        print(dim(f"  Reviewing {base}...HEAD"))
        if fix:
            print(dim("  Auto-fix: ON"))
        print()

        fixer = ReviewAutoFixer(cwd=repo)
        report = fixer.run(
            base=base, fix=fix,
            post_comments=post_comments, pr_id=pr_id,
            severity_filter=severity_filter,
        )
        format_autofix_report(report)

    elif command in ("/spec-validate", "/spec-check", "/validate-spec"):
        from code_agents.testing.spec_validator import SpecValidator, format_spec_report

        parts = arg.split() if arg else []
        spec_text = ""
        jira_key = ""
        prd_file = ""
        fmt = "text"
        i = 0
        while i < len(parts):
            if parts[i] == "--spec" and i + 1 < len(parts):
                spec_text = parts[i + 1]
                i += 1
            elif parts[i] == "--jira" and i + 1 < len(parts):
                jira_key = parts[i + 1]
                i += 1
            elif parts[i] == "--prd" and i + 1 < len(parts):
                prd_file = parts[i + 1]
                i += 1
            elif parts[i] == "--format" and i + 1 < len(parts):
                fmt = parts[i + 1]
                i += 1
            i += 1

        if not spec_text and not jira_key and not prd_file:
            print(yellow("  Usage: /spec-validate --spec <text> | --jira <key> | --prd <file>"))
            print(dim("  Options: --format text|json"))
            print()
            return None

        repo = state.get("repo_path") or os.getcwd()
        validator = SpecValidator(cwd=repo)
        report = validator.validate(spec_text=spec_text, jira_key=jira_key, prd_file=prd_file)
        output = format_spec_report(report, fmt=fmt)
        print(output)
        print()

    else:
        return "_not_handled"

    return None
