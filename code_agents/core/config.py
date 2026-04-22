from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import logging
import yaml

logger = logging.getLogger("code_agents.core.config")

_SYSTEM_PROMPT_ENV = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _expand_system_prompt_env(s: str) -> str:
    """Replace ${VAR} in YAML system_prompt with env or sensible defaults (after load_dotenv)."""

    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        if key == "CODE_AGENTS_PUBLIC_BASE_URL":
            v = os.getenv(key, "").strip()
            if v:
                return v
            # Fallback: localhost with configured port
            port = os.getenv("PORT", "8000")
            return f"http://127.0.0.1:{port}"
        if key == "ATLASSIAN_CLOUD_SITE_URL":
            v = os.getenv(key, "").strip()
            return v if v else "(set ATLASSIAN_CLOUD_SITE_URL in .env)"
        val = os.getenv(key)
        return val if val is not None and val != "" else m.group(0)

    return _SYSTEM_PROMPT_ENV.sub(repl, s)


def _expand_cwd(raw: str) -> str:
    """Expand ${VAR} in agent cwd field. Falls back to '.' if unresolved."""
    expanded = _expand_system_prompt_env(raw)
    # If still contains ${...}, the env var isn't set — fall back to "."
    if "${" in expanded:
        logger.debug("cwd %r has unresolved vars, falling back to '.'", raw)
        return "."
    return expanded


@dataclass
class AgentConfig:
    name: str
    display_name: str
    backend: str  # "cursor", "claude", "local", "cursor_http", "claude-cli"
    model: str
    system_prompt: str = ""
    permission_mode: str = "default"
    cwd: str = "."
    api_key: Optional[str] = None  # CURSOR_API_KEY or ANTHROPIC_API_KEY; env var fallback
    stream_tool_activity: bool = True
    include_session: bool = True
    extra_args: dict = field(default_factory=dict)
    routing_keywords: list = field(default_factory=list)
    routing_description: str = ""


@dataclass
class Settings:
    host: str = "0.0.0.0"
    port: int = 8000
    agents_dir: str = str(Path(__file__).resolve().parent.parent.parent / "agents")


settings = Settings(
    host=os.getenv("HOST", "0.0.0.0"),
    port=int(os.getenv("PORT", "8000")),
    agents_dir=os.getenv("AGENTS_DIR", str(Path(__file__).resolve().parent.parent.parent / "agents")),
)


class AgentLoader:
    """Reads YAML files from the agents directory and builds a name → config registry."""

    def __init__(self, agents_dir: str | Path):
        self._dir = Path(agents_dir)
        self._agents: dict[str, AgentConfig] = {}

    def _load_file(self, path: Path) -> None:
        logger.debug("Loading agent config from %s", path)
        with open(path) as f:
            data = yaml.safe_load(f)
        if not data or "name" not in data:
            return
        api_key = data.get("api_key")
        if api_key and isinstance(api_key, str) and api_key.startswith("${") and api_key.endswith("}"):
            api_key = os.getenv(api_key[2:-1], None)

        extra_args = data.get("extra_args") or {}
        if isinstance(extra_args, dict):
            expanded = {}
            for k, v in extra_args.items():
                if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
                    expanded[k] = os.getenv(v[2:-1], v)
                else:
                    expanded[k] = v
            extra_args = expanded

        raw_prompt = data.get("system_prompt", "")
        if isinstance(raw_prompt, str) and raw_prompt:
            raw_prompt = _expand_system_prompt_env(raw_prompt)

        # Expand ${VAR} in backend and model fields
        raw_backend = data.get("backend", "${CODE_AGENTS_BACKEND:local}")
        if isinstance(raw_backend, str) and raw_backend.startswith("${") and raw_backend.endswith("}"):
            inner = raw_backend[2:-1]
            if ":" in inner:
                var_name, default = inner.split(":", 1)
            else:
                var_name, default = inner, "local"
            raw_backend = os.getenv(var_name, default)

        raw_model = data.get("model", "${CODE_AGENTS_MODEL:Composer 2 Fast}")
        if isinstance(raw_model, str) and raw_model.startswith("${") and raw_model.endswith("}"):
            inner = raw_model[2:-1]
            if ":" in inner:
                var_name, default = inner.split(":", 1)
            else:
                var_name, default = inner, "Composer 2 Fast"
            raw_model = os.getenv(var_name, default)

        # Per-agent model override: CODE_AGENTS_MODEL_<AGENT_NAME_UPPER>
        agent_model_key = f"CODE_AGENTS_MODEL_{data['name'].upper().replace('-', '_')}"
        per_agent_model = os.getenv(agent_model_key, "").strip()
        if per_agent_model:
            raw_model = per_agent_model

        # Per-agent backend override: CODE_AGENTS_BACKEND_<AGENT_NAME_UPPER>
        agent_backend_key = f"CODE_AGENTS_BACKEND_{data['name'].upper().replace('-', '_')}"
        per_agent_backend = os.getenv(agent_backend_key, "").strip()
        if per_agent_backend:
            raw_backend = per_agent_backend

        raw_cwd = data.get("cwd", ".")
        expanded_cwd = _expand_cwd(raw_cwd)
        logger.debug(
            "Agent %s cwd: raw=%r expanded=%r",
            data["name"], raw_cwd, expanded_cwd,
        )

        # Parse routing keywords from YAML
        routing = data.get("routing", {}) or {}
        routing_keywords = routing.get("keywords", []) if isinstance(routing, dict) else []
        routing_description = routing.get("description", "") if isinstance(routing, dict) else ""

        cfg = AgentConfig(
            name=data["name"],
            display_name=data.get("display_name", data["name"]),
            backend=raw_backend,
            model=raw_model,
            system_prompt=raw_prompt if isinstance(raw_prompt, str) else "",
            permission_mode=data.get("permission_mode", "default"),
            cwd=expanded_cwd,
            api_key=api_key,
            stream_tool_activity=data.get("stream_tool_activity", True),
            include_session=data.get("include_session", True),
            extra_args=extra_args,
            routing_keywords=routing_keywords,
            routing_description=routing_description,
        )
        self._agents[cfg.name] = cfg

    def load(self) -> None:
        self._agents.clear()
        if not self._dir.is_dir():
            logger.error("Agents directory not found: %s", self._dir)
            raise FileNotFoundError(f"Agents directory not found: {self._dir}")
        logger.info("Loading agents from %s", self._dir)
        # Load from flat files: agents/*.yaml
        for path in sorted(self._dir.glob("*.yaml")):
            self._load_file(path)
        for path in sorted(self._dir.glob("*.yml")):
            self._load_file(path)
        # Load from subfolders: agents/<name>/<name>.yaml
        for subdir in sorted(self._dir.iterdir()):
            if subdir.is_dir() and not subdir.name.startswith((".", "_")):
                for path in sorted(subdir.glob("*.yaml")):
                    self._load_file(path)
                for path in sorted(subdir.glob("*.yml")):
                    self._load_file(path)
        logger.info("Loaded %d agents: %s", len(self._agents), list(self._agents.keys()))

    def get(self, name: str) -> Optional[AgentConfig]:
        return self._agents.get(name)

    def list_agents(self) -> list[AgentConfig]:
        return list(self._agents.values())

    @property
    def default(self) -> Optional[AgentConfig]:
        agents = self.list_agents()
        return agents[0] if agents else None


agent_loader = AgentLoader(settings.agents_dir)
