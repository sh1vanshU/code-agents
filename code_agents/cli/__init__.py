"""CLI subpackage — unified entry point, helpers, completions, and split modules."""

from .cli import *  # noqa: F401,F403
from .cli_helpers import *  # noqa: F401,F403
from .cli_completions import *  # noqa: F401,F403

# Explicit re-exports of _ prefixed names used by tests and other modules
from .cli_helpers import (  # noqa: F401
    _find_code_agents_home, _user_cwd, _load_env, _colors,
    _server_url, _api_get, _api_post, _check_workspace_trust,
)
from .cli_completions import (  # noqa: F401
    _AGENT_NAMES_FOR_COMPLETION, _SUBCOMMANDS,
    _generate_zsh_completion, _generate_bash_completion,
)
from .cli_server import _start_background  # noqa: F401 — backward compat
from .cli_cicd import _print_pipeline_status  # noqa: F401 — backward compat
