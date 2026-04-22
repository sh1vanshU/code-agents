#!/usr/bin/env python3
"""
Initiater — Project quality audit runner.

Reads rule files from initiater/rules/, scans the project for relevant files,
builds a structured prompt, and calls an LLM to evaluate compliance.

Usage:
    poetry run python initiater/run_audit.py
    poetry run python initiater/run_audit.py --rules documentation,workflow
    poetry run python initiater/run_audit.py --format json
    poetry run python initiater/run_audit.py --backend anthropic
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    import httpx
except ImportError:
    print("Error: httpx not installed. Run: poetry install", file=sys.stderr)
    sys.exit(1)

try:
    import yaml
except ImportError:
    print("Error: pyyaml not installed. Run: poetry install", file=sys.stderr)
    sys.exit(1)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RULES_DIR = Path(__file__).resolve().parent / "rules"
DEFAULT_SERVER_URL = "http://localhost:8000"


def parse_rule_file(path: Path) -> dict:
    """Parse a rule markdown file, extracting frontmatter and body."""
    text = path.read_text()
    frontmatter = {}
    body = text

    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if fm_match:
        frontmatter = yaml.safe_load(fm_match.group(1)) or {}
        body = text[fm_match.end():]

    return {
        "file": path.name,
        "dimension": frontmatter.get("dimension", path.stem),
        "severity": frontmatter.get("severity", "info"),
        "body": body.strip(),
    }


def load_rules(filter_names: list[str] | None = None) -> list[dict]:
    """Load all rule files, optionally filtering by dimension name."""
    rules = []
    for path in sorted(RULES_DIR.glob("*.md")):
        rule = parse_rule_file(path)
        if filter_names is None or rule["dimension"] in filter_names:
            rules.append(rule)
    return rules


def scan_project() -> dict:
    """Collect project state relevant to audit rules."""
    state = {}

    # Agent YAML files (nested agents/<name>/*.yaml, exclude autorun-only noise)
    agents_dir = PROJECT_ROOT / "agents"
    agent_files = []
    if agents_dir.exists():
        for f in sorted(agents_dir.rglob("*.yaml")):
            if f.name == "autorun.yaml":
                continue
            if "_shared" in f.parts:
                continue
            try:
                rel = f.relative_to(PROJECT_ROOT)
            except ValueError:
                rel = f
            agent_files.append({
                "filename": str(rel),
                "content": f.read_text(),
            })
    state["agent_yamls"] = agent_files

    # Key documentation files
    for name in ["README.md", "Agents.md", "setup.md", ".gitignore", ".env.example"]:
        path = PROJECT_ROOT / name
        if path.exists():
            content = path.read_text()
            # Truncate very large files
            if len(content) > 15000:
                content = content[:15000] + "\n... (truncated)"
            state[name] = content
        else:
            state[name] = None

    # Python source files (just names and first-line signatures)
    code_dir = PROJECT_ROOT / "code_agents"
    if code_dir.exists():
        py_files = []
        for f in sorted(code_dir.rglob("*.py")):
            rel = f.relative_to(PROJECT_ROOT)
            py_files.append(str(rel))
        state["python_files"] = py_files

    # Scripts
    scripts_dir = PROJECT_ROOT / "scripts"
    if scripts_dir.exists():
        state["scripts"] = [f.name for f in sorted(scripts_dir.iterdir()) if f.is_file()]

    # Project config
    pyproject = PROJECT_ROOT / "pyproject.toml"
    if pyproject.exists():
        state["pyproject.toml"] = pyproject.read_text()

    # Dockerfile
    dockerfile = PROJECT_ROOT / "Dockerfile"
    state["has_dockerfile"] = dockerfile.exists()

    # Tests
    tests_dir = PROJECT_ROOT / "tests"
    if tests_dir.exists():
        state["test_files"] = [str(f.relative_to(PROJECT_ROOT)) for f in sorted(tests_dir.rglob("*.py"))]
    else:
        state["test_files"] = []

    return state


def build_prompt(rules: list[dict], project_state: dict) -> str:
    """Build the audit prompt combining rules and project state."""
    rules_section = ""
    for rule in rules:
        rules_section += f"\n### [{rule['severity'].upper()}] {rule['dimension']}\n"
        rules_section += f"{rule['body']}\n"

    # Format project state
    state_section = "## Project State\n\n"

    # Agent YAMLs
    state_section += "### Agent YAML Files\n"
    for agent in project_state.get("agent_yamls", []):
        state_section += f"\n**{agent['filename']}:**\n```yaml\n{agent['content']}```\n"

    # Documentation files
    for name in ["README.md", "Agents.md", "setup.md", ".gitignore", ".env.example"]:
        if project_state.get(name):
            state_section += f"\n### {name}\n```\n{project_state[name]}\n```\n"
        elif project_state.get(name) is None:
            state_section += f"\n### {name}\n*File does not exist*\n"

    # Python files
    if project_state.get("python_files"):
        state_section += "\n### Python Source Files\n"
        state_section += "\n".join(f"- `{f}`" for f in project_state["python_files"])
        state_section += "\n"

    # Test files
    state_section += "\n### Test Files\n"
    if project_state.get("test_files"):
        state_section += "\n".join(f"- `{f}`" for f in project_state["test_files"])
    else:
        state_section += "*No test files found*"
    state_section += "\n"

    # Other state
    state_section += f"\n### Other\n"
    state_section += f"- Dockerfile exists: {project_state.get('has_dockerfile', False)}\n"
    if project_state.get("scripts"):
        state_section += f"- Scripts: {', '.join(project_state['scripts'])}\n"

    prompt = f"""You are a project quality auditor. Evaluate the project against each rule below.

For each dimension, go through every rule (checkbox item) and determine:
- **PASS**: The rule is satisfied based on the project state provided
- **FAIL**: The rule is clearly violated
- **WARN**: Partial compliance or cannot fully verify

## Rules to Evaluate

{rules_section}

{state_section}

## Output Format

For each dimension, output:

### <dimension name> [<severity>]
| Status | Rule | Details |
|--------|------|---------|
| PASS/FAIL/WARN | Rule description | Brief explanation |

At the end, provide a summary:

## Summary
- Total rules: <N>
- Pass: <N>
- Fail: <N>
- Warn: <N>
- Critical failures: <list any FAIL items from critical-severity dimensions>
"""
    return prompt


def call_local_server(prompt: str, server_url: str) -> str:
    """Call the project's own API server."""
    url = f"{server_url}/v1/agents/code-reasoning/chat/completions"
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    resp = httpx.post(url, json=payload, timeout=300.0)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def call_anthropic(prompt: str) -> str:
    """Call Anthropic API directly."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 8192,
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = httpx.post(url, json=payload, headers=headers, timeout=300.0)
    resp.raise_for_status()
    data = resp.json()
    return data["content"][0]["text"]


def format_json_report(llm_output: str, rules: list[dict]) -> str:
    """Wrap the LLM output in a JSON structure."""
    report = {
        "dimensions_audited": [r["dimension"] for r in rules],
        "severities": {r["dimension"]: r["severity"] for r in rules},
        "report": llm_output,
    }
    return json.dumps(report, indent=2)


def _format_llm_failure_message(args, exc: BaseException) -> str:
    """Short, user-facing explanation for stderr / offline report."""
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code} from LLM endpoint ({args.server_url})"
    if isinstance(exc, httpx.ConnectError):
        return f"cannot connect to Code Agents server at {args.server_url}"
    if isinstance(exc, httpx.TimeoutException):
        return "LLM request timed out"
    if isinstance(exc, httpx.RequestError):
        return f"request failed: {exc}"
    return f"{type(exc).__name__}: {exc}"


def build_offline_report(rules: list[dict], project_state: dict, reason: str) -> str:
    """Markdown when no LLM is available: dimensions + project snapshot for manual review."""
    lines = [
        "# Initiater audit (offline)",
        "",
        f"**LLM evaluation was not run.** {reason}",
        "",
        "To get a full LLM pass/fail table: start the server (`code-agents start`) and re-run, "
        "or use `--backend anthropic` with `ANTHROPIC_API_KEY` set.",
        "",
        "## Dimensions requested",
        "",
        "| Dimension | Severity | Rule file |",
        "|-----------|----------|-----------|",
    ]
    for r in rules:
        lines.append(f"| {r['dimension']} | {r['severity']} | `{r['file']}` |")
    lines.extend(["", "## Project scan snapshot", ""])

    n_agents = len(project_state.get("agent_yamls") or [])
    n_tests = len(project_state.get("test_files") or [])
    n_py = len(project_state.get("python_files") or [])
    lines.extend(
        [
            f"- **Agent YAML configs collected:** {n_agents}",
            f"- **Python source files (under code_agents/):** {n_py}",
            f"- **Test files:** {n_tests}",
            f"- **Dockerfile present:** {project_state.get('has_dockerfile', False)}",
            f"- **README.md present:** {bool(project_state.get('README.md'))}",
            f"- **setup.md present:** {bool(project_state.get('setup.md'))}",
            f"- **.env.example present:** {bool(project_state.get('.env.example'))}",
            "",
            "*This summary is generated from repository scans only — no AI scoring was applied.*",
            "",
        ]
    )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Run project quality audit")
    parser.add_argument(
        "--rules",
        type=str,
        default=None,
        help="Comma-separated list of dimensions to audit (default: all)",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--backend",
        choices=["local", "anthropic"],
        default="local",
        help="LLM backend: 'local' (Code Agents server) or 'anthropic' (direct API)",
    )
    parser.add_argument(
        "--server-url",
        type=str,
        default=DEFAULT_SERVER_URL,
        help=f"Code Agents server URL (default: {DEFAULT_SERVER_URL})",
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Do not call any LLM; print an offline scan summary (dimensions + repo snapshot).",
    )
    parser.add_argument(
        "--require-llm",
        action="store_true",
        help="Exit with an error if the LLM call fails. Default: print offline summary instead.",
    )
    args = parser.parse_args()

    # Load rules
    filter_names = args.rules.split(",") if args.rules else None
    rules = load_rules(filter_names)

    if not rules:
        print("No matching rule files found.", file=sys.stderr)
        sys.exit(1)

    print(f"Auditing {len(rules)} dimension(s): {', '.join(r['dimension'] for r in rules)}", file=sys.stderr)

    # Scan project
    print("Scanning project state...", file=sys.stderr)
    project_state = scan_project()

    # Build prompt
    prompt = build_prompt(rules, project_state)

    if args.skip_llm:
        reason = "Requested --skip-llm (no API call)."
        offline = build_offline_report(rules, project_state, reason)
        if args.format == "json":
            print(format_json_report(offline, rules))
        else:
            print(offline)
        return

    # Call LLM
    print(f"Calling LLM ({args.backend})...", file=sys.stderr)
    result: str | None = None
    llm_exc: BaseException | None = None
    try:
        if args.backend == "local":
            result = call_local_server(prompt, args.server_url)
        else:
            result = call_anthropic(prompt)
    except httpx.HTTPStatusError as e:
        llm_exc = e
    except httpx.RequestError as e:
        llm_exc = e
    except Exception as e:
        llm_exc = e

    if result is None and llm_exc is not None:
        detail = _format_llm_failure_message(args, llm_exc)
        if args.require_llm:
            print(f"Error: {detail}", file=sys.stderr)
            if isinstance(llm_exc, httpx.HTTPStatusError) and llm_exc.response.text:
                print(llm_exc.response.text[:2000], file=sys.stderr)
            sys.exit(1)
        print(f"Warning: {detail}. Emitting offline scan summary.", file=sys.stderr)
        result = build_offline_report(rules, project_state, reason=detail)

    assert result is not None

    # Output
    if args.format == "json":
        print(format_json_report(result, rules))
    else:
        print(result)


if __name__ == "__main__":
    main()
