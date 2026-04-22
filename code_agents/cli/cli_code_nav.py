"""CLI commands for code navigation and understanding tools.

Commands:
  code-agents usage-trace <symbol>          Find all usages of a symbol
  code-agents codebase-nav <query>          Semantic codebase search
  code-agents git-story <file> <line>       Full story behind a line of code
  code-agents call-chain <function>         Show call tree up and down
  code-agents code-examples <query>         Find code examples for a concept
  code-agents dep-graph <module> [--mermaid] Dependency graph with visualization
"""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_code_nav")


def _user_cwd() -> str:
    return os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()


def cmd_usage_trace(rest: list[str] | None = None):
    """Find all usages of a symbol across the codebase.

    Usage: code-agents usage-trace <symbol>
    """
    from .cli_helpers import _colors, _load_env

    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    rest = rest or []

    if not rest:
        print(f"\n  {red('Usage: code-agents usage-trace <symbol>')}")
        print(f"  {dim('Example: code-agents usage-trace build_prompt')}")
        return

    symbol = rest[0]
    include_tests = "--no-tests" not in rest
    cwd = _user_cwd()

    from code_agents.domain.usage_tracer import UsageTracer, UsageTraceConfig, format_usage

    config = UsageTraceConfig(cwd=cwd, include_tests=include_tests)
    result = UsageTracer(config).trace(symbol)
    print(format_usage(result))


def cmd_codebase_nav(rest: list[str] | None = None):
    """Semantic codebase search — find where concepts are implemented.

    Usage: code-agents nav <query>
    Example: code-agents nav "authentication flow"
    """
    from .cli_helpers import _colors, _load_env

    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    rest = rest or []

    if not rest:
        print(f"\n  {red('Usage: code-agents nav <query>')}")
        print(f"  {dim('Example: code-agents nav \"where does authentication happen\"')}")
        return

    query = " ".join(rest)
    cwd = _user_cwd()

    from code_agents.knowledge.codebase_nav import CodebaseNavigator, NavConfig, format_nav_results

    config = NavConfig(cwd=cwd)
    result = CodebaseNavigator(config).search(query)
    print(format_nav_results(result))


def cmd_git_story(rest: list[str] | None = None):
    """Reconstruct the full story behind a line of code.

    Usage: code-agents git-story <file> <line>
    Example: code-agents git-story code_agents/stream.py 42
    """
    from .cli_helpers import _colors, _load_env

    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    rest = rest or []

    if len(rest) < 2:
        print(f"\n  {red('Usage: code-agents git-story <file> <line>')}")
        print(f"  {dim('Example: code-agents git-story code_agents/stream.py 42')}")
        return

    file_path = rest[0]
    try:
        line_number = int(rest[1])
    except ValueError:
        print(f"  {red('Error: line number must be an integer')}")
        return

    cwd = _user_cwd()

    from code_agents.git_ops.git_story import GitStoryTeller, GitStoryConfig, format_story

    config = GitStoryConfig(cwd=cwd)
    result = GitStoryTeller(config).tell_story(file_path, line_number)
    print(format_story(result))


def cmd_call_chain(rest: list[str] | None = None):
    """Show full call tree (callers and callees) for a function.

    Usage: code-agents call-chain <function_name>
    Example: code-agents call-chain build_prompt
    """
    from .cli_helpers import _colors, _load_env

    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    rest = rest or []

    if not rest:
        print(f"\n  {red('Usage: code-agents call-chain <function_name>')}")
        print(f"  {dim('Example: code-agents call-chain build_prompt')}")
        return

    target = rest[0]
    max_depth = 3
    if "--depth" in rest:
        idx = rest.index("--depth")
        if idx + 1 < len(rest):
            try:
                max_depth = int(rest[idx + 1])
            except ValueError:
                pass

    cwd = _user_cwd()

    from code_agents.observability.call_chain import CallChainAnalyzer, CallChainConfig, format_call_chain

    config = CallChainConfig(cwd=cwd, max_depth=max_depth)
    result = CallChainAnalyzer(config).analyze(target)
    print(format_call_chain(result))


def cmd_code_examples(rest: list[str] | None = None):
    """Find code examples for a concept or library usage.

    Usage: code-agents examples <query>
    Example: code-agents examples "Redis"
    """
    from .cli_helpers import _colors, _load_env

    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    rest = rest or []

    if not rest:
        print(f"\n  {red('Usage: code-agents examples <query>')}")
        print(f"  {dim('Example: code-agents examples Redis')}")
        return

    query = " ".join(rest)
    include_tests = "--no-tests" not in rest
    cwd = _user_cwd()

    from code_agents.knowledge.code_example import ExampleFinder, ExampleConfig, format_examples

    config = ExampleConfig(cwd=cwd, include_tests=include_tests)
    result = ExampleFinder(config).find(query)
    print(format_examples(result))


def cmd_dep_graph_viz(rest: list[str] | None = None):
    """Dependency graph with Mermaid/DOT visualization output.

    Usage: code-agents dep-graph <module> [--mermaid] [--dot] [--depth N]
    Example: code-agents dep-graph stream --mermaid
    """
    from .cli_helpers import _colors, _load_env

    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    rest = rest or []

    if not rest:
        print(f"\n  {red('Usage: code-agents dep-graph <module> [--mermaid] [--dot]')}")
        print(f"  {dim('Example: code-agents dep-graph stream --mermaid')}")
        return

    module_name = rest[0]
    output_format = "ascii"
    if "--mermaid" in rest:
        output_format = "mermaid"
    elif "--dot" in rest:
        output_format = "dot"

    depth = 3
    if "--depth" in rest:
        idx = rest.index("--depth")
        if idx + 1 < len(rest):
            try:
                depth = int(rest[idx + 1])
            except ValueError:
                pass

    cwd = _user_cwd()

    from code_agents.analysis.dependency_graph import DependencyGraph

    print(f"  {cyan('Building dependency graph...')}")
    dg = DependencyGraph(cwd)
    dg.build_graph()

    if output_format == "mermaid":
        print(dg.format_mermaid(module_name, depth=depth))
    elif output_format == "dot":
        print(dg.format_dot(module_name, depth=depth))
    else:
        print(dg.format_tree(module_name, depth=depth))
