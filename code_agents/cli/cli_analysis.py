"""CLI code analysis commands — deadcode, flags, security, complexity, techdebt, config-diff, api-check, apidoc, audit."""

from __future__ import annotations

import logging
import os
import sys

from .cli_helpers import (
    _colors, _server_url, _api_get, _api_post, _load_env,
    _user_cwd, _find_code_agents_home, prompt_yes_no,
)

logger = logging.getLogger("code_agents.cli.cli_analysis")


def cmd_deadcode(rest: list[str] | None = None):
    """Find dead code — unused imports, functions, endpoints.

    Usage:
      code-agents deadcode              # scan current repo
      code-agents deadcode --language python  # force language
      code-agents deadcode --json       # JSON output
    """
    import json as _json
    from code_agents.analysis.deadcode import DeadCodeFinder, format_deadcode_report

    bold, green, yellow, red, cyan, dim = _colors()
    rest = rest or []

    cwd = os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()

    # Parse flags
    language = None
    json_output = "--json" in rest
    if "--language" in rest:
        idx = rest.index("--language")
        if idx + 1 < len(rest):
            language = rest[idx + 1]

    print()
    print(bold(cyan("  Dead Code Finder")))
    print(dim(f"  Scanning {cwd}..."))
    print()

    finder = DeadCodeFinder(cwd=cwd, language=language)
    report = finder.scan()

    if json_output:
        import dataclasses
        print(_json.dumps(dataclasses.asdict(report), indent=2))
    else:
        print(format_deadcode_report(report))
        print()


def cmd_flags(rest: list[str] | None = None):
    """List feature flags in codebase.

    Usage:
      code-agents flags              # scan and list all flags
      code-agents flags --stale      # show only stale flags
      code-agents flags --matrix     # show environment matrix only
      code-agents flags --json       # JSON output
    """
    import json as _json
    from code_agents.analysis.feature_flags import FeatureFlagScanner, format_flag_report

    bold, green, yellow, red, cyan, dim = _colors()
    rest = rest or []

    cwd = os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()

    print()
    print(bold(cyan("  Feature Flag Scanner")))
    print(dim(f"  Scanning {cwd}..."))
    print()

    scanner = FeatureFlagScanner(cwd=cwd)
    report = scanner.scan()

    json_output = "--json" in rest
    stale_only = "--stale" in rest
    matrix_only = "--matrix" in rest

    if json_output:
        from dataclasses import asdict
        data = asdict(report)
        if stale_only:
            data["flags"] = [f for f in data["flags"] if f.get("stale")]
        print(_json.dumps(data, indent=2))
        return

    if report.total_flags == 0:
        print(yellow("  No feature flags detected."))
        print(dim("  Scans .env files, Java @Value annotations, YAML configs, Python os.getenv"))
        print()
        return

    if stale_only:
        if report.stale_flags:
            print(bold(f"  Stale Flags ({len(report.stale_flags)}):"))
            for flag in report.stale_flags:
                print(f"    x {red(flag.name)} ({flag.file}:{flag.line})")
        else:
            print(green("  No stale flags found."))
        print()
        return

    if matrix_only and report.env_matrix:
        envs_set = set()
        for vals in report.env_matrix.values():
            envs_set.update(vals.keys())
        env_list = sorted(envs_set)

        header = f"    {'Flag':<35} " + " ".join(f"{e:>10}" for e in env_list)
        print(header)
        print(f"    {'-' * len(header)}")
        for flag_name, vals in report.env_matrix.items():
            row = f"    {flag_name:<35} "
            for env in env_list:
                val = vals.get(env, "-")
                row += f" {val:>10}"
            print(row)
        print()
        return

    print(format_flag_report(report))
    print()
    print(dim(f"  Scanned: {cwd}"))
    print(dim(f"  Total: {report.total_flags} flags, {len(report.stale_flags)} stale"))
    print()


def cmd_security(rest: list[str] | None = None):
    """OWASP security scan — find vulnerabilities in code.

    Usage:
      code-agents security              # full scan
      code-agents security --json       # JSON output
      code-agents security --category sql-injection  # filter by category
    """
    import json as _json
    from code_agents.analysis.security_scanner import SecurityScanner, format_security_report

    bold, green, yellow, red, cyan, dim = _colors()
    rest = rest or []

    cwd = os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()

    # Parse flags
    json_output = "--json" in rest
    category_filter = None
    if "--category" in rest:
        idx = rest.index("--category")
        if idx + 1 < len(rest):
            category_filter = rest[idx + 1]

    print()
    print(bold(cyan("  Security Scanner")))
    print(dim(f"  OWASP top 10 static analysis — scanning {cwd}..."))
    print()

    scanner = SecurityScanner(cwd=cwd)
    report = scanner.scan()

    # Apply category filter
    if category_filter:
        report.findings = [f for f in report.findings if f.category == category_filter]

    if json_output:
        import dataclasses
        print(_json.dumps(dataclasses.asdict(report), indent=2))
    else:
        print(format_security_report(report))
        print()


def cmd_complexity(rest: list[str] | None = None):
    """Analyze code complexity — cyclomatic complexity and nesting depth.

    Usage:
      code-agents complexity              # scan current repo
      code-agents complexity --language python  # force language
      code-agents complexity --json       # JSON output
    """
    import json as _json
    from code_agents.analysis.complexity import ComplexityAnalyzer, format_complexity_report

    bold, green, yellow, red, cyan, dim = _colors()
    rest = rest or []

    cwd = os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()

    language = None
    json_output = "--json" in rest
    if "--language" in rest:
        idx = rest.index("--language")
        if idx + 1 < len(rest):
            language = rest[idx + 1]

    print()
    print(bold(cyan("  Code Complexity Report")))
    print(dim(f"  Scanning {cwd}..."))
    print()

    analyzer = ComplexityAnalyzer(cwd=cwd, language=language)
    report = analyzer.analyze()

    if json_output:
        import dataclasses
        print(_json.dumps(dataclasses.asdict(report), indent=2))
    else:
        print(format_complexity_report(report))
        print()


def cmd_techdebt(rest: list[str] | None = None):
    """Scan for tech debt — TODOs, deprecated, skipped tests, lint disables.

    Usage:
      code-agents techdebt               # scan current repo
      code-agents techdebt --json        # JSON output
    """
    import json as _json
    from code_agents.reviews.tech_debt import TechDebtScanner, format_debt_report

    bold, green, yellow, red, cyan, dim = _colors()
    rest = rest or []

    cwd = os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()
    json_output = "--json" in rest

    print()
    print(bold(cyan("  Tech Debt Tracker")))
    print(dim(f"  Scanning {cwd}..."))
    print()

    scanner = TechDebtScanner(cwd=cwd)
    report = scanner.scan()

    if json_output:
        import dataclasses
        print(_json.dumps(dataclasses.asdict(report), indent=2))
    else:
        print(format_debt_report(report))
        print()


def cmd_config_diff(rest: list[str] | None = None):
    """Compare configs across environments (dev/staging/prod).

    Usage:
      code-agents config-diff                    # compare all detected envs
      code-agents config-diff staging prod       # compare two specific envs
      code-agents config-diff --json             # JSON output
    """
    import json as _json
    bold, green, yellow, red, cyan, dim = _colors()
    rest = rest or []

    print()
    print(bold(cyan("  Config Drift Detector")))
    print()

    cwd = os.getenv("TARGET_REPO_PATH") or os.getcwd()

    from code_agents.analysis.config_drift import ConfigDriftDetector, format_drift_report

    detector = ConfigDriftDetector(cwd)
    configs = detector.load_configs()

    if not configs:
        print(yellow("  No environment configs detected."))
        print(dim("  Supports: application-{env}.yml, .env.{env}, config/{env}/, k8s ConfigMaps"))
        print()
        return

    json_mode = "--json" in rest
    env_args = [a for a in rest if not a.startswith("--")]

    if len(env_args) == 2:
        env_a, env_b = env_args[0], env_args[1]
        if env_a not in configs:
            print(red(f"  Environment '{env_a}' not found. Available: {', '.join(sorted(configs.keys()))}"))
            print()
            return
        if env_b not in configs:
            print(red(f"  Environment '{env_b}' not found. Available: {', '.join(sorted(configs.keys()))}"))
            print()
            return
        diff = detector.compare(env_a, env_b)
        if json_mode:
            from dataclasses import asdict
            print(_json.dumps(asdict(diff), indent=2))
        else:
            from code_agents.analysis.config_drift import DriftReport
            report = DriftReport(environments=[env_a, env_b], diffs=[diff])
            print(format_drift_report(report))
            print()
    else:
        report = detector.compare_all()
        if json_mode:
            from dataclasses import asdict
            print(_json.dumps(asdict(report), indent=2))
        else:
            print(format_drift_report(report))
            print()

    print(dim(f"  Scanned: {cwd}"))
    print(dim(f"  Environments: {', '.join(sorted(configs.keys()))} ({sum(len(v) for v in configs.values())} total keys)"))
    print()


def cmd_api_check(rest: list[str] | None = None):
    """Compare API endpoints with last release to detect breaking changes.

    Usage:
      code-agents api-check              # compare against last git tag
      code-agents api-check v8.0.0       # compare against specific ref
    """
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    cwd = _user_cwd()
    args = rest or []

    base_ref = args[0] if args else ""

    from code_agents.api.api_compat import APICompatChecker

    print()
    print(bold(cyan("  API Compatibility Check")))
    print()

    checker = APICompatChecker(cwd=cwd, base_ref=base_ref)

    print(dim(f"  Comparing: {checker.base_ref} -> HEAD"))
    print(dim(f"  Scanning endpoints..."))

    report = checker.compare()
    output = checker.format_report(report)

    # Colorize the output
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("+"):
            print(green(line))
        elif stripped.startswith("- "):
            print(red(line))
        elif stripped.startswith("~"):
            print(yellow(line))
        elif "BREAKING" in stripped:
            print(red(bold(line)))
        elif "COMPATIBLE" in stripped:
            print(green(bold(line)))
        elif stripped.startswith("Non-Breaking"):
            print(green(line))
        elif stripped.startswith("Breaking"):
            print(red(line))
        else:
            print(line)


def cmd_apidoc(rest: list[str] | None = None):
    """Generate API documentation from source code.

    Usage:
      code-agents apidoc                # terminal display
      code-agents apidoc --markdown     # save as API.md
      code-agents apidoc --openapi      # save as openapi.json
      code-agents apidoc --json         # JSON output
    """
    bold, green, yellow, red, cyan, dim = _colors()
    cwd = os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()
    args = rest or []

    print()
    print(bold(cyan("  API Documentation Generator")))
    print(dim(f"  Scanning {cwd}..."))
    print()

    from code_agents.generators.api_doc_generator import APIDocGenerator

    gen = APIDocGenerator(cwd=cwd)
    gen.scan_endpoints()

    if not gen.endpoints:
        print(yellow("  No API endpoints discovered."))
        print(dim("  Supports: Spring (@GetMapping, etc.), FastAPI, Flask, Express"))
        print()
        return

    if "--json" in args:
        import json as _json
        spec = gen.generate_openapi()
        print(_json.dumps(spec, indent=2))
        return

    if "--openapi" in args:
        import json as _json
        spec = gen.generate_openapi()
        fpath = os.path.join(cwd, "openapi.json")
        with open(fpath, "w") as f:
            _json.dump(spec, f, indent=2)
        print(green(f"  Saved: {fpath}"))
        print(dim(f"  {len(gen.endpoints)} endpoints"))
        print()
        return

    if "--markdown" in args:
        md = gen.generate_markdown()
        fpath = os.path.join(cwd, "API.md")
        with open(fpath, "w") as f:
            f.write(md)
        print(green(f"  Saved: {fpath}"))
        print(dim(f"  {len(gen.endpoints)} endpoints"))
        print()
        return

    # Default: terminal display
    print(gen.format_terminal())


def cmd_audit(rest: list[str] | None = None):
    """Audit dependencies for vulnerabilities, licenses, outdated versions.

    Usage:
      code-agents audit                 # full audit
      code-agents audit --vuln          # vulnerabilities only
      code-agents audit --licenses      # license check only
      code-agents audit --outdated      # outdated packages only
      code-agents audit --json          # JSON output
    """
    bold, green, yellow, red, cyan, dim = _colors()
    cwd = os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()
    args = rest or []

    # Parse flags
    json_output = "--json" in args
    vuln_only = "--vuln" in args
    licenses_only = "--licenses" in args
    outdated_only = "--outdated" in args

    print()
    print(bold(cyan("  Dependency Audit")))
    print(dim(f"  Scanning dependencies in {cwd}..."))
    print()

    from code_agents.security.dependency_audit import DependencyAuditor

    auditor = DependencyAuditor(cwd=cwd)
    auditor.scan_dependencies()
    auditor.check_known_vulnerabilities()

    if not vuln_only:
        auditor.check_licenses()

    if outdated_only or (not vuln_only and not licenses_only):
        print(dim("  Checking for outdated packages (may take a moment)..."))
        auditor.check_outdated()

    if json_output:
        import json as _json
        print(_json.dumps(auditor.to_dict(), indent=2))
    else:
        print(auditor.format_report(
            vuln_only=vuln_only,
            licenses_only=licenses_only,
            outdated_only=outdated_only,
        ))

    print()
