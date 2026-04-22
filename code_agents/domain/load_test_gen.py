"""Load test scenario generator — produce k6, Locust, or JMeter test plans from API endpoints."""

from __future__ import annotations

import logging
import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from xml.sax.saxutils import escape as xml_escape

logger = logging.getLogger("code_agents.domain.load_test_gen")

# ── Regex patterns for endpoint detection ────────────────────────────────────

_FASTAPI_ROUTE_RE = re.compile(
    r"@(?:app|router)\.(get|post|put|patch|delete)\(\s*[\"']([^\"']+)[\"']"
)
_FLASK_ROUTE_RE = re.compile(
    r"@(?:app|blueprint|bp)\.(route|get|post|put|patch|delete)\(\s*[\"']([^\"']+)[\"']"
)
_FLASK_METHODS_RE = re.compile(r"methods\s*=\s*\[([^\]]+)\]")
_EXPRESS_ROUTE_RE = re.compile(
    r"(?:app|router)\.(get|post|put|patch|delete)\(\s*[\"']([^\"']+)[\"']"
)
_SPRING_ROUTE_RE = re.compile(
    r"@(Get|Post|Put|Patch|Delete)Mapping\(\s*(?:value\s*=\s*)?[\"']([^\"']+)[\"']"
)
_SPRING_REQUEST_RE = re.compile(
    r"@RequestMapping\(\s*(?:value\s*=\s*)?[\"']([^\"']+)[\"']"
)
_SPRING_REQUEST_METHOD_RE = re.compile(r"method\s*=\s*RequestMethod\.(\w+)")
_PATH_PARAM_RE = re.compile(r"\{(\w+)\}")
_FASTAPI_PATH_PARAM_RE = re.compile(r"\{(\w+)\}")

# ── Scenario presets ─────────────────────────────────────────────────────────

_SCENARIO_PRESETS: dict[str, dict] = {
    "smoke": {
        "description": "Low traffic smoke test to verify endpoints are healthy",
        "rps": 5,
        "duration": "1m",
        "ramp_up": "10s",
        "think_time": 2.0,
    },
    "peak": {
        "description": "Simulated peak traffic with aggressive ramp-up",
        "rps": 200,
        "duration": "5m",
        "ramp_up": "1m",
        "think_time": 0.5,
    },
    "stress": {
        "description": "Stress test with increasing load until failure",
        "rps": 500,
        "duration": "10m",
        "ramp_up": "3m",
        "think_time": 0.2,
    },
    "soak": {
        "description": "Moderate sustained traffic over a long period to detect memory leaks",
        "rps": 50,
        "duration": "30m",
        "ramp_up": "2m",
        "think_time": 1.0,
    },
}


# ── Data models ──────────────────────────────────────────────────────────────


@dataclass
class EndpointSpec:
    method: str
    path: str
    body: dict | None = None
    headers: dict = field(default_factory=dict)


@dataclass
class Scenario:
    name: str
    description: str
    endpoints: list[EndpointSpec]
    rps: int
    duration: str
    ramp_up: str
    think_time: float = 1.0


# ── Generator ────────────────────────────────────────────────────────────────


class LoadTestGenerator:
    """Scan a project for API endpoints and generate load test scripts."""

    SUPPORTED_FORMATS = ("k6", "locust", "jmeter")
    SUPPORTED_SCENARIOS = tuple(_SCENARIO_PRESETS.keys())

    def __init__(self, cwd: str):
        self.cwd = cwd
        self._repo = Path(cwd)
        logger.info("LoadTestGenerator initialized for %s", cwd)

    # ── Public API ───────────────────────────────────────────────────────

    def generate(self, scenario: str = "peak", format: str = "k6") -> str:
        """Generate a load test script.

        Args:
            scenario: One of smoke, peak, stress, soak.
            format: One of k6, locust, jmeter.

        Returns:
            Generated script as a string.
        """
        if scenario not in _SCENARIO_PRESETS:
            raise ValueError(
                f"Unknown scenario '{scenario}'. Choose from: {', '.join(_SCENARIO_PRESETS)}"
            )
        if format not in self.SUPPORTED_FORMATS:
            raise ValueError(
                f"Unknown format '{format}'. Choose from: {', '.join(self.SUPPORTED_FORMATS)}"
            )

        endpoints = self._scan_endpoints()
        if not endpoints:
            logger.warning("No endpoints found in %s", self.cwd)
            raise ValueError(
                f"No API endpoints found in {self.cwd}. "
                "Ensure the project has FastAPI, Flask, Express, or Spring routes."
            )

        spec = self._build_scenario(endpoints, scenario)
        logger.info(
            "Built %s scenario with %d endpoints, %d RPS, %s duration",
            scenario,
            len(endpoints),
            spec.rps,
            spec.duration,
        )

        if format == "k6":
            return self._format_k6(spec)
        elif format == "locust":
            return self._format_locust(spec)
        elif format == "jmeter":
            return self._format_jmeter(spec)
        else:
            raise ValueError(f"Unknown format: {format}")

    # ── Endpoint scanning ────────────────────────────────────────────────

    def _scan_endpoints(self) -> list[EndpointSpec]:
        """Scan the project for API endpoints across frameworks."""
        endpoints: list[EndpointSpec] = []

        endpoints.extend(self._scan_python_endpoints())
        endpoints.extend(self._scan_express_endpoints())
        endpoints.extend(self._scan_spring_endpoints())

        # De-duplicate by (method, path)
        seen: set[tuple[str, str]] = set()
        unique: list[EndpointSpec] = []
        for ep in endpoints:
            key = (ep.method.upper(), ep.path)
            if key not in seen:
                seen.add(key)
                unique.append(ep)

        unique.sort(key=lambda e: (e.path, e.method))
        logger.info("Scanned %d unique endpoints", len(unique))
        return unique

    def _scan_python_endpoints(self) -> list[EndpointSpec]:
        """Scan FastAPI and Flask route decorators."""
        endpoints: list[EndpointSpec] = []

        for fpath in self._iter_files(".py"):
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            for line in content.splitlines():
                # FastAPI
                match = _FASTAPI_ROUTE_RE.search(line)
                if match:
                    method = match.group(1).upper()
                    path = match.group(2)
                    body = self._guess_body(method, path)
                    endpoints.append(EndpointSpec(method=method, path=path, body=body))
                    continue

                # Flask with specific method
                match = _FLASK_ROUTE_RE.search(line)
                if match:
                    decorator = match.group(1)
                    path = match.group(2)
                    if decorator == "route":
                        methods_match = _FLASK_METHODS_RE.search(line)
                        if methods_match:
                            for m in re.findall(r"[\"'](\w+)[\"']", methods_match.group(1)):
                                body = self._guess_body(m.upper(), path)
                                endpoints.append(EndpointSpec(method=m.upper(), path=path, body=body))
                        else:
                            endpoints.append(EndpointSpec(method="GET", path=path))
                    else:
                        method = decorator.upper()
                        body = self._guess_body(method, path)
                        endpoints.append(EndpointSpec(method=method, path=path, body=body))

        return endpoints

    def _scan_express_endpoints(self) -> list[EndpointSpec]:
        """Scan Express.js route patterns."""
        endpoints: list[EndpointSpec] = []

        for fpath in self._iter_files(".js"):
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            for line in content.splitlines():
                match = _EXPRESS_ROUTE_RE.search(line)
                if match:
                    method = match.group(1).upper()
                    path = match.group(2)
                    body = self._guess_body(method, path)
                    endpoints.append(EndpointSpec(method=method, path=path, body=body))

        # Also scan .ts files
        for fpath in self._iter_files(".ts"):
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            for line in content.splitlines():
                match = _EXPRESS_ROUTE_RE.search(line)
                if match:
                    method = match.group(1).upper()
                    path = match.group(2)
                    body = self._guess_body(method, path)
                    endpoints.append(EndpointSpec(method=method, path=path, body=body))

        return endpoints

    def _scan_spring_endpoints(self) -> list[EndpointSpec]:
        """Scan Spring Boot @*Mapping annotations."""
        endpoints: list[EndpointSpec] = []

        for fpath in self._iter_files(".java"):
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            for line in content.splitlines():
                match = _SPRING_ROUTE_RE.search(line)
                if match:
                    method = match.group(1).upper()
                    path = match.group(2)
                    body = self._guess_body(method, path)
                    endpoints.append(EndpointSpec(method=method, path=path, body=body))
                    continue

                match = _SPRING_REQUEST_RE.search(line)
                if match:
                    path = match.group(1)
                    method_match = _SPRING_REQUEST_METHOD_RE.search(line)
                    method = method_match.group(1) if method_match else "GET"
                    body = self._guess_body(method, path)
                    endpoints.append(EndpointSpec(method=method, path=path, body=body))

        return endpoints

    # ── Helpers ───────────────────────────────────────────────────────────

    def _iter_files(self, extension: str):
        """Iterate over project files with given extension, skipping node_modules/vendor/venv."""
        skip = {"node_modules", "vendor", "venv", ".venv", ".git", "__pycache__", "dist", "build"}
        for fpath in self._repo.rglob(f"*{extension}"):
            if any(part in skip for part in fpath.parts):
                continue
            yield fpath

    @staticmethod
    def _guess_body(method: str, path: str) -> dict | None:
        """Generate a placeholder request body for write methods."""
        if method in ("GET", "DELETE", "HEAD", "OPTIONS"):
            return None
        return {"example_key": "example_value"}

    @staticmethod
    def _replace_path_params(path: str, style: str = "k6") -> str:
        """Replace {param} path parameters with example values.

        style: k6 uses ${param}, locust uses <param>, jmeter uses ${param}
        """
        if style == "locust":
            return _PATH_PARAM_RE.sub(r"1", path)
        # k6 and jmeter both use template literals / variables but for
        # simplicity we just replace with example values
        return _PATH_PARAM_RE.sub(r"1", path)

    # ── Scenario builder ─────────────────────────────────────────────────

    def _build_scenario(self, endpoints: list[EndpointSpec], scenario_type: str) -> Scenario:
        """Build a Scenario from detected endpoints and the chosen preset."""
        preset = _SCENARIO_PRESETS[scenario_type]
        return Scenario(
            name=scenario_type,
            description=preset["description"],
            endpoints=endpoints,
            rps=preset["rps"],
            duration=preset["duration"],
            ramp_up=preset["ramp_up"],
            think_time=preset["think_time"],
        )

    # ── k6 formatter ─────────────────────────────────────────────────────

    def _format_k6(self, scenario: Scenario) -> str:
        """Generate a k6 JavaScript load test script."""
        # Parse duration for stages
        ramp_dur = scenario.ramp_up
        main_dur = scenario.duration
        vus = max(1, scenario.rps // 10)  # rough VU estimate

        requests: list[str] = []
        for ep in scenario.endpoints:
            path = self._replace_path_params(ep.path, style="k6")
            if ep.method == "GET":
                requests.append(f"  http.get(`${{BASE_URL}}{path}`);")
            elif ep.method == "DELETE":
                requests.append(f"  http.del(`${{BASE_URL}}{path}`);")
            else:
                body = ep.body or {}
                import json
                body_str = json.dumps(body)
                requests.append(
                    f"  http.{ep.method.lower()}(`${{BASE_URL}}{path}`, "
                    f"JSON.stringify({body_str}), params);"
                )

        requests_block = "\n".join(requests)

        return textwrap.dedent(f"""\
            // k6 load test — {scenario.name} scenario
            // {scenario.description}
            // Generated by code-agents load-test generator
            //
            // Run: k6 run load_test_{scenario.name}.js

            import http from 'k6/http';
            import {{ check, sleep }} from 'k6';

            const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

            export const options = {{
              stages: [
                {{ duration: '{ramp_dur}', target: {vus} }},   // ramp up
                {{ duration: '{main_dur}', target: {vus} }},   // hold
                {{ duration: '{ramp_dur}', target: 0 }},       // ramp down
              ],
              thresholds: {{
                http_req_duration: ['p(95)<500'],  // 95% of requests under 500ms
                http_req_failed: ['rate<0.01'],    // <1% failure rate
              }},
            }};

            const params = {{
              headers: {{ 'Content-Type': 'application/json' }},
            }};

            export default function () {{
            {requests_block}

              sleep({scenario.think_time});
            }}
        """)

    # ── Locust formatter ─────────────────────────────────────────────────

    def _format_locust(self, scenario: Scenario) -> str:
        """Generate a Python Locust load test class."""
        tasks: list[str] = []
        for i, ep in enumerate(scenario.endpoints):
            path = self._replace_path_params(ep.path, style="locust")
            func_name = f"task_{ep.method.lower()}_{i}"
            if ep.method == "GET":
                tasks.append(textwrap.dedent(f"""\
                    @task
                    def {func_name}(self):
                        self.client.get("{path}")
                """))
            elif ep.method == "DELETE":
                tasks.append(textwrap.dedent(f"""\
                    @task
                    def {func_name}(self):
                        self.client.delete("{path}")
                """))
            else:
                import json
                body_str = json.dumps(ep.body or {})
                tasks.append(textwrap.dedent(f"""\
                    @task
                    def {func_name}(self):
                        self.client.{ep.method.lower()}("{path}", json={body_str})
                """))

        tasks_block = "\n".join("    " + line for t in tasks for line in t.splitlines())

        return textwrap.dedent(f"""\
            # Locust load test — {scenario.name} scenario
            # {scenario.description}
            # Generated by code-agents load-test generator
            #
            # Run: locust -f load_test_{scenario.name}.py --host http://localhost:8000
            #       --users {scenario.rps} --spawn-rate {max(1, scenario.rps // 10)}

            from locust import HttpUser, task, between


            class LoadTestUser(HttpUser):
                wait_time = between({max(0.1, scenario.think_time - 0.5)}, {scenario.think_time + 0.5})

            {tasks_block}
        """)

    # ── JMeter formatter ─────────────────────────────────────────────────

    def _format_jmeter(self, scenario: Scenario) -> str:
        """Generate a JMeter XML test plan."""
        threads = max(1, scenario.rps // 10)
        # Parse duration to seconds
        duration_secs = self._parse_duration_secs(scenario.duration)
        ramp_secs = self._parse_duration_secs(scenario.ramp_up)

        samplers: list[str] = []
        for i, ep in enumerate(scenario.endpoints):
            path = self._replace_path_params(ep.path, style="jmeter")
            body_xml = ""
            if ep.body:
                import json
                body_str = xml_escape(json.dumps(ep.body))
                body_xml = f"""
              <boolProp name="HTTPSampler.postBodyRaw">true</boolProp>
              <elementProp name="HTTPsampler.Arguments" elementType="Arguments">
                <collectionProp name="Arguments.arguments">
                  <elementProp name="" elementType="HTTPArgument">
                    <stringProp name="Argument.value">{body_str}</stringProp>
                    <stringProp name="Argument.metadata">=</stringProp>
                  </elementProp>
                </collectionProp>
              </elementProp>"""

            samplers.append(f"""\
            <HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy"
                              testname="{ep.method} {xml_escape(ep.path)}" enabled="true">
              <stringProp name="HTTPSampler.domain"></stringProp>
              <stringProp name="HTTPSampler.port"></stringProp>
              <stringProp name="HTTPSampler.path">{xml_escape(path)}</stringProp>
              <stringProp name="HTTPSampler.method">{ep.method}</stringProp>{body_xml}
              <stringProp name="HTTPSampler.connect_timeout">5000</stringProp>
              <stringProp name="HTTPSampler.response_timeout">30000</stringProp>
            </HTTPSamplerProxy>
            <hashTree/>""")

        samplers_block = "\n".join(samplers)

        return textwrap.dedent(f"""\
            <?xml version="1.0" encoding="UTF-8"?>
            <!--
              JMeter load test — {scenario.name} scenario
              {scenario.description}
              Generated by code-agents load-test generator

              Run: jmeter -n -t load_test_{scenario.name}.jmx -l results.jtl
            -->
            <jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6">
              <hashTree>
                <TestPlan guiclass="TestPlanGui" testclass="TestPlan"
                          testname="{scenario.name} Load Test" enabled="true">
                  <stringProp name="TestPlan.comments">{xml_escape(scenario.description)}</stringProp>
                  <elementProp name="TestPlan.user_defined_variables" elementType="Arguments">
                    <collectionProp name="Arguments.arguments">
                      <elementProp name="BASE_URL" elementType="Argument">
                        <stringProp name="Argument.name">BASE_URL</stringProp>
                        <stringProp name="Argument.value">http://localhost:8000</stringProp>
                      </elementProp>
                    </collectionProp>
                  </elementProp>
                </TestPlan>
                <hashTree>
                  <ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup"
                               testname="Thread Group" enabled="true">
                    <intProp name="ThreadGroup.num_threads">{threads}</intProp>
                    <intProp name="ThreadGroup.ramp_time">{ramp_secs}</intProp>
                    <boolProp name="ThreadGroup.scheduler">true</boolProp>
                    <stringProp name="ThreadGroup.duration">{duration_secs}</stringProp>
                    <stringProp name="ThreadGroup.delay">0</stringProp>
                    <elementProp name="ThreadGroup.main_controller" elementType="LoopController">
                      <boolProp name="LoopController.continue_forever">false</boolProp>
                      <intProp name="LoopController.loops">-1</intProp>
                    </elementProp>
                  </ThreadGroup>
                  <hashTree>
                    <HeaderManager guiclass="HeaderPanel" testclass="HeaderManager"
                                   testname="HTTP Headers" enabled="true">
                      <collectionProp name="HeaderManager.headers">
                        <elementProp name="Content-Type" elementType="Header">
                          <stringProp name="Header.name">Content-Type</stringProp>
                          <stringProp name="Header.value">application/json</stringProp>
                        </elementProp>
                      </collectionProp>
                    </HeaderManager>
                    <hashTree/>
            {samplers_block}
                    <ConstantTimer guiclass="ConstantTimerGui" testclass="ConstantTimer"
                                   testname="Think Time" enabled="true">
                      <stringProp name="ConstantTimer.delay">{int(scenario.think_time * 1000)}</stringProp>
                    </ConstantTimer>
                    <hashTree/>
                  </hashTree>
                </hashTree>
              </hashTree>
            </jmeterTestPlan>
        """)

    @staticmethod
    def _parse_duration_secs(duration: str) -> int:
        """Parse duration string like '5m', '1h', '30s' to seconds."""
        match = re.match(r"^(\d+)(s|m|h)$", duration.strip())
        if not match:
            return 60
        val = int(match.group(1))
        unit = match.group(2)
        if unit == "s":
            return val
        elif unit == "m":
            return val * 60
        elif unit == "h":
            return val * 3600
        return 60


# ── Summary formatter ────────────────────────────────────────────────────────


def format_scenario_summary(scenario: Scenario) -> str:
    """Format a human-readable summary of a load test scenario."""
    lines = [
        f"  Scenario:   {scenario.name}",
        f"  Description: {scenario.description}",
        f"  Endpoints:  {len(scenario.endpoints)}",
        f"  Target RPS: {scenario.rps}",
        f"  Duration:   {scenario.duration}",
        f"  Ramp-up:    {scenario.ramp_up}",
        f"  Think time: {scenario.think_time}s",
        "",
        "  Endpoints:",
    ]
    for ep in scenario.endpoints:
        body_hint = " (with body)" if ep.body else ""
        lines.append(f"    {ep.method:6s} {ep.path}{body_hint}")
    return "\n".join(lines)
