"""CLI commands for API development tools.

Commands:
  code-agents endpoint-gen <Resource> [--framework fastapi]   Generate CRUD endpoints
  code-agents api-sync <spec-file>                            Check spec/code sync
  code-agents response-optimize                               Scan for response optimization
  code-agents rest-to-grpc                                    Convert REST to gRPC
  code-agents api-changelog <old-spec> <new-spec>             Diff API versions
"""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_api_tools")


def _user_cwd() -> str:
    return os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()


def cmd_endpoint_gen(rest: list[str] | None = None):
    """Generate CRUD endpoints for a resource.

    Usage:
      code-agents endpoint-gen User
      code-agents endpoint-gen Order --framework fastapi
      code-agents endpoint-gen Product --framework express
    """
    from .cli_helpers import _colors, _load_env

    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    rest = rest or []

    if not rest or rest[0] in ("--help", "-h"):
        print(cmd_endpoint_gen.__doc__)
        return

    resource_name = rest[0]
    framework = "fastapi"
    fields: list[str] = []

    i = 1
    while i < len(rest):
        a = rest[i]
        if a == "--framework" and i + 1 < len(rest):
            framework = rest[i + 1].lower()
            i += 1
        elif a == "--fields" and i + 1 < len(rest):
            fields = [f.strip() for f in rest[i + 1].split(",")]
            i += 1
        i += 1

    if framework not in ("fastapi", "express", "flask", "django"):
        print(red(f"  Unknown framework: {framework}"))
        print(dim("  Supported: fastapi, express, flask, django"))
        return

    print(f"  {cyan(f'Generating CRUD endpoints for {resource_name} ({framework})...')}")

    from code_agents.api.endpoint_generator import EndpointGenerator, EndpointGenConfig, format_endpoint

    config = EndpointGenConfig(
        resource_name=resource_name,
        framework=framework,
        fields=fields or None,
        cwd=_user_cwd(),
    )
    result = EndpointGenerator(config).generate()
    print(format_endpoint(result))


def cmd_api_sync(rest: list[str] | None = None):
    """Check if API spec and code are in sync.

    Usage:
      code-agents api-sync openapi.yaml
      code-agents api-sync swagger.json --format json
    """
    from .cli_helpers import _colors, _load_env

    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    rest = rest or []

    if not rest or rest[0] in ("--help", "-h"):
        print(cmd_api_sync.__doc__)
        return

    spec_file = rest[0]
    fmt = "text"
    if "--format" in rest:
        idx = rest.index("--format")
        if idx + 1 < len(rest):
            fmt = rest[idx + 1].lower()

    print(f"  {cyan(f'Checking spec/code sync for {spec_file}...')}")

    from code_agents.api.api_sync import ApiSyncer, ApiSyncConfig, format_api_sync

    config = ApiSyncConfig(spec_file=spec_file, cwd=_user_cwd())
    result = ApiSyncer(config).check()
    print(format_api_sync(result, fmt=fmt))


def cmd_response_optimize(rest: list[str] | None = None):
    """Scan for API response optimization opportunities.

    Usage:
      code-agents response-optimize
      code-agents response-optimize --path src/api/
      code-agents response-optimize --format json
    """
    from .cli_helpers import _colors, _load_env

    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    rest = rest or []

    if rest and rest[0] in ("--help", "-h"):
        print(cmd_response_optimize.__doc__)
        return

    cwd = _user_cwd()
    fmt = "text"
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--path" and i + 1 < len(rest):
            cwd = rest[i + 1]
            i += 1
        elif a == "--format" and i + 1 < len(rest):
            fmt = rest[i + 1].lower()
            i += 1
        i += 1

    print(f"  {cyan('Scanning for response optimization opportunities...')}")

    from code_agents.core.response_optimizer import ResponseOptimizer, ResponseOptimizerConfig, format_response_report

    config = ResponseOptimizerConfig(cwd=cwd)
    result = ResponseOptimizer(config).scan()
    print(format_response_report(result, fmt=fmt))


def cmd_rest_to_grpc(rest: list[str] | None = None):
    """Convert REST endpoints to gRPC proto definitions.

    Usage:
      code-agents rest-to-grpc
      code-agents rest-to-grpc --path src/api/
      code-agents rest-to-grpc --output service.proto
    """
    from .cli_helpers import _colors, _load_env

    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    rest = rest or []

    if rest and rest[0] in ("--help", "-h"):
        print(cmd_rest_to_grpc.__doc__)
        return

    cwd = _user_cwd()
    output_path = None
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--path" and i + 1 < len(rest):
            cwd = rest[i + 1]
            i += 1
        elif a == "--output" and i + 1 < len(rest):
            output_path = rest[i + 1]
            i += 1
        i += 1

    print(f"  {cyan('Converting REST endpoints to gRPC proto...')}")

    from code_agents.api.rest_to_grpc import RestToGrpcConverter, RestToGrpcConfig, format_grpc_output

    config = RestToGrpcConfig(cwd=cwd)
    result = RestToGrpcConverter(config).convert()
    output = format_grpc_output(result)
    print(output)

    if output_path:
        from pathlib import Path

        out = Path(output_path).resolve()
        out.write_text(result.proto_content, encoding="utf-8")
        print(green(f"  Written to {out}"))


def cmd_api_changelog(rest: list[str] | None = None):
    """Generate API changelog between two spec versions.

    Usage:
      code-agents api-changelog old-spec.yaml new-spec.yaml
      code-agents api-changelog v1.json v2.json --format markdown
    """
    from .cli_helpers import _colors, _load_env

    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    rest = rest or []

    if len(rest) < 2 or rest[0] in ("--help", "-h"):
        print(cmd_api_changelog.__doc__)
        return

    old_spec = rest[0]
    new_spec = rest[1]
    fmt = "text"
    if "--format" in rest:
        idx = rest.index("--format")
        if idx + 1 < len(rest):
            fmt = rest[idx + 1].lower()

    print(f"  {cyan(f'Diffing API specs: {old_spec} → {new_spec}...')}")

    from code_agents.api.api_changelog_gen import ApiChangelogGenerator, ApiChangelogConfig, format_api_changelog

    config = ApiChangelogConfig(old_spec=old_spec, new_spec=new_spec, cwd=_user_cwd())
    result = ApiChangelogGenerator(config).generate()
    print(format_api_changelog(result, fmt=fmt))
