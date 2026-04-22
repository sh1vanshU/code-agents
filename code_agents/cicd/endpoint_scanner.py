"""
Endpoint & Contract Auto-Discovery — scan repos for REST/gRPC/Kafka endpoints.

Scans Java/Spring repos for @RestController, @RequestMapping, .proto files,
@KafkaListener, etc. Generates curl/grpcurl/kafka test commands.

Cache: .code-agents/{repo-name}.endpoints.cache.json (per-repo, by repo folder name)
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger("code_agents.endpoint_scanner")


@dataclass
class RestEndpoint:
    method: str  # GET, POST, PUT, DELETE, PATCH
    path: str
    controller: str = ""
    request_body: str = ""
    file: str = ""
    line: int = 0


@dataclass
class GrpcService:
    service_name: str
    methods: list[dict] = field(default_factory=list)  # [{name, request_type, response_type}]
    file: str = ""


@dataclass
class KafkaListener:
    topic: str
    group: str = ""
    method: str = ""
    file: str = ""
    line: int = 0


@dataclass
class ScanResult:
    repo_name: str
    rest_endpoints: list[RestEndpoint] = field(default_factory=list)
    grpc_services: list[GrpcService] = field(default_factory=list)
    kafka_listeners: list[KafkaListener] = field(default_factory=list)
    db_queries: list[dict] = field(default_factory=list)

    @property
    def total(self) -> int:
        rest = len(self.rest_endpoints)
        grpc = sum(len(s.methods) for s in self.grpc_services)
        kafka = len(self.kafka_listeners)
        db = len(self.db_queries)
        return rest + grpc + kafka + db

    def summary(self) -> str:
        rest = len(self.rest_endpoints)
        grpc = sum(len(s.methods) for s in self.grpc_services)
        kafka = len(self.kafka_listeners)
        db = len(self.db_queries)
        parts = []
        if rest: parts.append(f"{rest} REST")
        if grpc: parts.append(f"{grpc} gRPC")
        if kafka: parts.append(f"{kafka} Kafka")
        if db: parts.append(f"{db} DB queries")
        return f"{self.total} endpoints ({', '.join(parts)})" if parts else "0 endpoints"


# Spring annotation patterns
_MAPPING_RE = re.compile(
    r'@(Get|Post|Put|Delete|Patch|Request)Mapping\s*\(\s*(?:value\s*=\s*)?["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_CONTROLLER_RE = re.compile(r'@(?:Rest)?Controller')
_CLASS_MAPPING_RE = re.compile(
    r'@RequestMapping\s*\(\s*(?:value\s*=\s*)?["\']([^"\']+)["\']'
)
_REQUEST_BODY_RE = re.compile(r'@RequestBody\s+(\w+)')
# Kafka: match @KafkaListener with various topic formats
_KAFKA_LISTENER_START_RE = re.compile(r'@KafkaListener\s*\(')
_KAFKA_TOPIC_PATTERNS = [
    # topics = "single-topic"
    re.compile(r'topics?\s*=\s*"([^"]+)"'),
    # topics = {"topic1", "topic2"}
    re.compile(r'topics?\s*=\s*\{([^}]+)\}'),
    # topics = '${config.topic}'
    re.compile(r"topics?\s*=\s*'([^']+)'"),
    # topicPattern = "prefix.*"
    re.compile(r'topicPattern\s*=\s*"([^"]+)"'),
    # topics = CONSTANT_NAME (capture the constant)
    re.compile(r'topics?\s*=\s*([A-Z][A-Z0-9_.]+)'),
]
_KAFKA_GROUP_RE = re.compile(r'groupId\s*=\s*["\']([^"\']+)["\']')
_KAFKA_CONTAINER_RE = re.compile(r'containerFactory\s*=\s*["\']([^"\']+)["\']')

# gRPC proto patterns
_GRPC_SERVICE_RE = re.compile(r'service\s+(\w+)\s*\{')
_GRPC_RPC_RE = re.compile(r'rpc\s+(\w+)\s*\(\s*(\w+)\s*\)\s*returns\s*\(\s*(\w+)\s*\)')


def scan_rest_endpoints(repo_path: str) -> list[RestEndpoint]:
    """Scan Java/Spring repo for REST endpoints."""
    endpoints = []
    repo = Path(repo_path)

    for java_file in repo.rglob("*.java"):
        if any(p in str(java_file) for p in ["/target/", "/build/", "/.git/", "/node_modules/"]):
            continue
        try:
            content = java_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        if not _CONTROLLER_RE.search(content):
            continue

        # Get class-level path prefix
        class_prefix = ""
        class_match = _CLASS_MAPPING_RE.search(content)
        if class_match:
            class_prefix = class_match.group(1).rstrip("/")

        # Find method-level mappings
        for i, line in enumerate(content.splitlines(), 1):
            match = _MAPPING_RE.search(line)
            if match:
                method_type = match.group(1).upper()
                if method_type == "REQUEST":
                    method_type = "GET"  # default for @RequestMapping
                path = class_prefix + "/" + match.group(2).lstrip("/")
                path = "/" + path.lstrip("/")

                # Look for @RequestBody in next few lines
                body_type = ""
                chunk = "\n".join(content.splitlines()[i:i+5])
                body_match = _REQUEST_BODY_RE.search(chunk)
                if body_match:
                    body_type = body_match.group(1)

                endpoints.append(RestEndpoint(
                    method=method_type,
                    path=path,
                    controller=java_file.stem,
                    request_body=body_type,
                    file=str(java_file.relative_to(repo)),
                    line=i,
                ))

    logger.info("Scanned %d REST endpoints in %s", len(endpoints), repo_path)
    return endpoints


def scan_grpc_services(repo_path: str) -> list[GrpcService]:
    """Scan for .proto files and extract gRPC service definitions."""
    services = []
    repo = Path(repo_path)

    for proto_file in repo.rglob("*.proto"):
        if any(p in str(proto_file) for p in ["/target/", "/build/", "/.git/"]):
            continue
        try:
            content = proto_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        for svc_match in _GRPC_SERVICE_RE.finditer(content):
            service_name = svc_match.group(1)
            # Find RPCs within this service block
            start = svc_match.end()
            # Find matching closing brace
            depth = 1
            end = start
            for j in range(start, len(content)):
                if content[j] == "{":
                    depth += 1
                elif content[j] == "}":
                    depth -= 1
                    if depth == 0:
                        end = j
                        break

            block = content[start:end]
            methods = []
            for rpc_match in _GRPC_RPC_RE.finditer(block):
                methods.append({
                    "name": rpc_match.group(1),
                    "request_type": rpc_match.group(2),
                    "response_type": rpc_match.group(3),
                })

            services.append(GrpcService(
                service_name=service_name,
                methods=methods,
                file=str(proto_file.relative_to(repo)),
            ))

    logger.info("Scanned %d gRPC services in %s", len(services), repo_path)
    return services


def scan_kafka_listeners(repo_path: str) -> list[KafkaListener]:
    """Scan for @KafkaListener annotations (handles multi-line, arrays, SpEL, constants)."""
    listeners = []
    repo = Path(repo_path)

    for java_file in repo.rglob("*.java"):
        if any(p in str(java_file) for p in ["/target/", "/build/", "/.git/"]):
            continue
        try:
            content = java_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        lines = content.splitlines()
        for i, line in enumerate(lines, 1):
            if not _KAFKA_LISTENER_START_RE.search(line):
                continue

            # Collect the full annotation (may span multiple lines)
            annotation = line
            if ')' not in annotation:
                for j in range(i, min(i + 10, len(lines))):
                    annotation += " " + lines[j]
                    if ')' in lines[j]:
                        break

            # Try each topic pattern
            topics = []
            for pattern in _KAFKA_TOPIC_PATTERNS:
                match = pattern.search(annotation)
                if match:
                    raw = match.group(1)
                    # Handle array: "topic1", "topic2"
                    if '"' in raw:
                        topics.extend(t.strip().strip('"').strip("'") for t in raw.split(","))
                    else:
                        topics.append(raw.strip())
                    break

            if not topics:
                # Fallback: just note there's a listener without parsed topic
                topics = ["(unparsed — check source)"]

            # Extract group
            group = ""
            group_match = _KAFKA_GROUP_RE.search(annotation)
            if group_match:
                group = group_match.group(1)

            for topic in topics:
                if topic:
                    listeners.append(KafkaListener(
                        topic=topic,
                        group=group,
                        file=str(java_file.relative_to(repo)),
                        line=i,
                    ))

    logger.info("Scanned %d Kafka listeners in %s", len(listeners), repo_path)
    return listeners


def scan_db_queries(repo_path: str) -> list[dict]:
    """Scan for JPA @Repository, @Query, native SQL in Java files."""
    queries = []
    repo = Path(repo_path)
    _QUERY_RE = re.compile(r'@Query\s*\(\s*(?:value\s*=\s*)?["\']([^"\']+)["\']', re.IGNORECASE)
    _REPO_RE = re.compile(r'@Repository')
    _NATIVE_RE = re.compile(r'nativeQuery\s*=\s*true')

    for java_file in repo.rglob("*.java"):
        if any(p in str(java_file) for p in ["/target/", "/build/", "/.git/"]):
            continue
        try:
            content = java_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        is_repo = bool(_REPO_RE.search(content))
        for i, line in enumerate(content.splitlines(), 1):
            match = _QUERY_RE.search(line)
            if match:
                query = match.group(1)
                is_native = bool(_NATIVE_RE.search(line))
                queries.append({
                    "query": query[:200],
                    "file": str(java_file.relative_to(repo)),
                    "line": i,
                    "native": is_native,
                    "repository": is_repo,
                })

    logger.info("Scanned %d DB queries in %s", len(queries), repo_path)
    return queries


def scan_all(repo_path: str) -> ScanResult:
    """Run all scanners and return combined result."""
    repo_name = Path(repo_path).name
    return ScanResult(
        repo_name=repo_name,
        rest_endpoints=scan_rest_endpoints(repo_path),
        grpc_services=scan_grpc_services(repo_path),
        kafka_listeners=scan_kafka_listeners(repo_path),
        db_queries=scan_db_queries(repo_path),
    )


# Java type → sample JSON value mapping
_JAVA_TYPE_SAMPLES: dict[str, object] = {
    "string": "string", "char": "a", "character": "a",
    "int": 0, "integer": 0, "long": 0, "short": 0, "byte": 0,
    "double": 0.0, "float": 0.0, "bigdecimal": 0.0, "number": 0,
    "boolean": False,
    "list": [], "set": [], "collection": [], "arraylist": [], "linkedlist": [],
    "map": {}, "hashmap": {}, "linkedhashmap": {}, "treemap": {},
    "localdate": "2026-01-01", "localdatetime": "2026-01-01T00:00:00",
    "date": "2026-01-01", "instant": "2026-01-01T00:00:00Z",
    "zoneddatetime": "2026-01-01T00:00:00Z", "timestamp": "2026-01-01T00:00:00",
    "uuid": "00000000-0000-0000-0000-000000000000",
    "biginteger": 0, "optional": None,
}


def _extract_dto_fields(repo_path: str, class_name: str) -> str | None:
    """Extract fields from a Java DTO class and generate a sample JSON body.

    Searches the repo for the class file, parses field declarations,
    and maps Java types to sample JSON values.
    Returns JSON string or None if class not found.
    """
    if not class_name or not repo_path:
        return None
    try:
        # Find Java files containing this class
        from pathlib import Path
        repo = Path(repo_path)
        candidates = []
        for java_file in repo.rglob("*.java"):
            # Skip test files and build dirs
            parts_str = str(java_file)
            if "/test/" in parts_str or "/build/" in parts_str or "/target/" in parts_str:
                continue
            try:
                content = java_file.read_text(encoding="utf-8", errors="ignore")
                if re.search(rf'\bclass\s+{re.escape(class_name)}\b', content):
                    candidates.append(content)
            except OSError:
                continue

        if not candidates:
            return None

        content = candidates[0]
        # Extract field declarations: private/protected Type fieldName;
        field_pattern = re.compile(
            r'(?:private|protected|public)\s+'
            r'(?:final\s+)?'
            r'(\w+(?:<[^>]+>)?)\s+'  # type (with optional generics)
            r'(\w+)\s*[;=]',         # field name
        )
        fields: dict[str, object] = {}
        for match in field_pattern.finditer(content):
            java_type = match.group(1).split("<")[0].strip().lower()  # strip generics
            field_name = match.group(2)
            # Skip common non-data fields
            if field_name in ("serialVersionUID", "log", "logger", "LOG"):
                continue
            sample = _JAVA_TYPE_SAMPLES.get(java_type, "string")
            fields[field_name] = sample

        if not fields:
            return None
        return json.dumps(fields)
    except Exception:
        logger.debug("DTO extraction failed for %s", class_name)
        return None


def _load_openapi_schemas(repo_path: str) -> dict[str, str]:
    """Load request body schemas from OpenAPI/Swagger spec if available.

    Returns dict mapping 'METHOD /path' to sample JSON body string.
    """
    from pathlib import Path
    spec_locations = [
        "openapi.yaml", "openapi.yml", "openapi.json",
        "swagger.yaml", "swagger.yml", "swagger.json",
        "src/main/resources/openapi.yaml", "src/main/resources/openapi.yml",
        "src/main/resources/openapi.json",
        "docs/openapi.yaml", "docs/swagger.json",
        "api-docs.json", "api-docs.yaml",
    ]
    repo = Path(repo_path)
    spec_data = None
    for loc in spec_locations:
        spec_file = repo / loc
        if spec_file.is_file():
            try:
                raw = spec_file.read_text(encoding="utf-8", errors="ignore")
                if spec_file.suffix in (".yaml", ".yml"):
                    import yaml
                    spec_data = yaml.safe_load(raw)
                else:
                    spec_data = json.loads(raw)
                break
            except Exception:
                continue

    if not spec_data or not isinstance(spec_data, dict):
        return {}

    schemas: dict[str, str] = {}
    paths = spec_data.get("paths", {})
    components = spec_data.get("components", {}).get("schemas", {})
    # Also check Swagger 2.0 definitions
    if not components:
        components = spec_data.get("definitions", {})

    def _schema_to_sample(schema: dict) -> object:
        """Convert a JSON schema to a sample value."""
        if not isinstance(schema, dict):
            return "string"
        # Handle $ref
        ref = schema.get("$ref", "")
        if ref:
            ref_name = ref.split("/")[-1]
            if ref_name in components:
                return _schema_to_sample(components[ref_name])
            return {"ref": ref_name}

        schema_type = schema.get("type", "object")
        if schema_type == "string":
            fmt = schema.get("format", "")
            if fmt == "date":
                return "2026-01-01"
            if fmt in ("date-time", "datetime"):
                return "2026-01-01T00:00:00Z"
            if fmt == "uuid":
                return "00000000-0000-0000-0000-000000000000"
            if fmt == "email":
                return "user@example.com"
            return schema.get("example", "string")
        if schema_type == "integer":
            return schema.get("example", 0)
        if schema_type == "number":
            return schema.get("example", 0.0)
        if schema_type == "boolean":
            return schema.get("example", False)
        if schema_type == "array":
            items = schema.get("items", {})
            return [_schema_to_sample(items)]
        if schema_type == "object":
            props = schema.get("properties", {})
            if not props:
                return {}
            return {k: _schema_to_sample(v) for k, v in props.items()}
        return "string"

    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for method, details in methods.items():
            if method.lower() in ("get", "head", "options", "parameters"):
                continue
            if not isinstance(details, dict):
                continue
            # OpenAPI 3.x
            req_body = details.get("requestBody", {})
            if isinstance(req_body, dict):
                content = req_body.get("content", {})
                json_schema = content.get("application/json", {}).get("schema", {})
                if json_schema:
                    sample = _schema_to_sample(json_schema)
                    key = f"{method.upper()} {path}"
                    schemas[key] = json.dumps(sample) if not isinstance(sample, str) else sample
                    continue
            # Swagger 2.x — check parameters with in: body
            params = details.get("parameters", [])
            for param in params:
                if isinstance(param, dict) and param.get("in") == "body":
                    schema = param.get("schema", {})
                    if schema:
                        sample = _schema_to_sample(schema)
                        key = f"{method.upper()} {path}"
                        schemas[key] = json.dumps(sample) if not isinstance(sample, str) else sample
                        break

    return schemas


def _generate_sample_body(class_name: str) -> str:
    """Generate a plausible sample JSON body from a class name."""
    if not class_name:
        return '{"field1": "value1"}'
    # Extract words from CamelCase
    words = [w.lower() for w in re.findall(r'[A-Z][a-z]+', class_name)]
    # Common field heuristics
    fields = {}
    for w in words:
        if w in ('user', 'account', 'person', 'member'):
            fields.update({"name": "string", "email": "user@example.com"})
        elif w in ('payment', 'transaction', 'order', 'charge'):
            fields.update({"amount": 100, "currency": "INR"})
        elif w in ('create', 'add', 'new', 'register', 'save'):
            continue  # verb, skip
        elif w in ('request', 'req', 'dto', 'body', 'input', 'payload'):
            continue  # generic, skip
        else:
            fields[w] = "string"
    if not fields:
        fields = {"id": 1, "data": "string"}
    return json.dumps(fields)


def generate_curls(
    endpoints: list[RestEndpoint],
    base_url: str = "http://localhost:8080",
    repo_path: str = "",
) -> list[str]:
    """Generate curl commands for REST endpoints.

    Payload priority: OpenAPI schema → Java DTO fields → heuristic guess.
    """
    # Try loading OpenAPI schemas for best-quality payloads
    openapi_schemas: dict[str, str] = {}
    if repo_path:
        try:
            openapi_schemas = _load_openapi_schemas(repo_path)
        except Exception:
            pass

    curls = []
    for ep in endpoints:
        if ep.method == "GET":
            curls.append(f'curl -sS -w \'\\n%{{http_code}}\' "{base_url}{ep.path}"')
        else:
            body = None
            # 1. OpenAPI schema (best)
            key = f"{ep.method} {ep.path}"
            if key in openapi_schemas:
                body = openapi_schemas[key]
            # 2. Java DTO field extraction (good)
            if not body and repo_path and ep.request_body:
                body = _extract_dto_fields(repo_path, ep.request_body)
            # 3. Heuristic from class name (fallback)
            if not body:
                body = _generate_sample_body(ep.request_body) if ep.request_body else '{}'
            curls.append(
                f'curl -sS -w \'\\n%{{http_code}}\' -X {ep.method} "{base_url}{ep.path}" '
                f'-H "Content-Type: application/json" -d \'{body}\''
            )
    return curls


def generate_grpc_cmds(services: list[GrpcService], host: str = "localhost:9090") -> list[str]:
    """Generate grpcurl commands for gRPC services."""
    cmds = []
    for svc in services:
        for method in svc.methods:
            req_type = method.get("request_type", "")
            type_comment = f'  # request: {req_type}' if req_type else ''
            cmds.append(
                f'grpcurl -plaintext -d \'{{}}\' {host} {svc.service_name}/{method["name"]}{type_comment}'
            )
    return cmds


def generate_kafka_cmds(listeners: list[KafkaListener], bootstrap: str = "localhost:9092") -> list[str]:
    """Generate kafka-console-producer commands."""
    cmds = []
    for kl in listeners:
        cmds.append(
            f'echo \'{{"test": true}}\' | kafka-console-producer.sh '
            f'--broker-list {bootstrap} --topic {kl.topic}'
        )
    return cmds


# Cache management — per-repo by folder name
def _cache_path(repo_path: str) -> Path:
    """Cache path: .code-agents/{repo-name}.endpoints.cache.json"""
    repo_name = Path(repo_path).name
    cache_dir = Path(repo_path) / ".code-agents"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{repo_name}.endpoints.cache.json"


def save_cache(repo_path: str, result: ScanResult) -> str:
    """Save scan results to cache file."""
    path = _cache_path(repo_path)
    data = {
        "repo_name": result.repo_name,
        "rest_endpoints": [asdict(e) for e in result.rest_endpoints],
        "grpc_services": [asdict(s) for s in result.grpc_services],
        "kafka_listeners": [asdict(l) for l in result.kafka_listeners],
        "db_queries": result.db_queries,
        "total": result.total,
        "summary": result.summary(),
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("Saved endpoint cache: %s (%d endpoints)", path, result.total)
    return str(path)


def load_cache(repo_path: str) -> Optional[dict]:
    """Load cached scan results."""
    path = _cache_path(repo_path)
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.debug("Failed to load endpoint scan cache: %s", e)
    return None


def background_scan(repo_path: str) -> None:
    """Run scan in background and cache results. Safe to call from a thread."""
    try:
        result = scan_all(repo_path)
        if result.total > 0:
            save_cache(repo_path, result)
            logger.info("Background scan complete: %s", result.summary())
        else:
            logger.info("Background scan: no endpoints found in %s", repo_path)
    except Exception as e:
        logger.warning("Background scan failed: %s", e)


def run_single_endpoint(cmd: str, timeout: int = 10) -> dict:
    """Execute a single curl/grpcurl command and capture result."""
    import subprocess
    import time as _time

    t0 = _time.monotonic()
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout,
        )
        elapsed_ms = int((_time.monotonic() - t0) * 1000)

        # Extract HTTP status from curl -w '\n%{http_code}' output
        status_code = 0
        body = result.stdout or ""
        if result.returncode == 0 and body:
            lines = body.rstrip().rsplit('\n', 1)
            if len(lines) == 2 and lines[1].strip().isdigit():
                status_code = int(lines[1].strip())
                body = lines[0]
            else:
                status_code = 200  # fallback for non-curl commands

        return {
            "command": cmd[:200],
            "status_code": status_code,
            "body": body[:2000],
            "stderr": (result.stderr or "")[:500],
            "exit_code": result.returncode,
            "duration_ms": elapsed_ms,
            "passed": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {
            "command": cmd[:200], "status_code": 0, "body": "",
            "stderr": f"Timed out after {timeout}s",
            "exit_code": -1, "duration_ms": timeout * 1000, "passed": False,
        }
    except Exception as e:
        return {
            "command": cmd[:200], "status_code": 0, "body": "",
            "stderr": str(e), "exit_code": -1, "duration_ms": 0, "passed": False,
        }


def run_all_endpoints(
    result: ScanResult,
    base_url: str = "http://localhost:8080",
    auth_header: str = "",
    timeout: int = 10,
    endpoint_type: str = "all",
    repo_path: str = "",
) -> list[dict]:
    """Run all discovered endpoints and return results."""
    commands = []

    if endpoint_type in ("all", "rest"):
        for curl in generate_curls(result.rest_endpoints, base_url, repo_path=repo_path):
            if auth_header:
                curl = curl.replace('curl -sS', f'curl -sS -H "Authorization: {auth_header}"')
            # Add -w to capture HTTP status
            curl = curl.replace('curl -sS', 'curl -sS -o /dev/null -w "%{http_code}" ')
            commands.append(("rest", curl))

    if endpoint_type in ("all", "grpc"):
        for cmd in generate_grpc_cmds(result.grpc_services):
            commands.append(("grpc", cmd))

    if endpoint_type in ("all", "kafka"):
        for cmd in generate_kafka_cmds(result.kafka_listeners):
            commands.append(("kafka", cmd))

    results = []
    for ep_type, cmd in commands:
        r = run_single_endpoint(cmd, timeout=timeout)
        r["type"] = ep_type
        results.append(r)

    return results


def format_run_report(results: list[dict]) -> str:
    """Format endpoint run results as a report."""
    if not results:
        return "No endpoints to run."

    passed = sum(1 for r in results if r["passed"])
    failed = len(results) - passed

    lines = [
        "", f"Endpoint Test Report: {passed} passed, {failed} failed ({len(results)} total)", "",
    ]

    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        duration = f"{r['duration_ms']}ms"
        lines.append(f"  {status} [{r.get('type', '?'):<5}] {r['command'][:70]:<70} {duration}")
        if not r["passed"] and r["stderr"]:
            lines.append(f"       error: {r['stderr'][:80]}")

    lines.append("")
    return "\n".join(lines)


def load_endpoint_config(repo_path: str) -> dict:
    """Load .code-agents/endpoints.yaml config."""
    config_path = Path(repo_path) / ".code-agents" / "endpoints.yaml"
    if config_path.is_file():
        try:
            return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception:
            pass
    return {}
