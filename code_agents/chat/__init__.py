"""Chat subpackage — interactive REPL, UI, commands, server communication, history."""

from .chat import *  # noqa: F401,F403
from .chat_ui import *  # noqa: F401,F403
from .chat_commands import *  # noqa: F401,F403
from .chat_server import *  # noqa: F401,F403
from .chat_history import *  # noqa: F401,F403
from .chat_context import *  # noqa: F401,F403
from .chat_slash import *  # noqa: F401,F403
from .chat_streaming import *  # noqa: F401,F403
from .chat_welcome import *  # noqa: F401,F403
from .chat_input import *  # noqa: F401,F403
from .chat_response import *  # noqa: F401,F403
from .chat_complexity import *  # noqa: F401,F403

# Explicit re-exports of _ prefixed names used by tests and other modules
from .chat import (  # noqa: F401
    chat_main, _chat_main_inner,
    _make_completer,
    _parse_inline_delegation,
)
from .chat_context import (  # noqa: F401
    _build_system_context,
    _suggest_skills,
)
from .chat_slash import (  # noqa: F401
    _handle_command,
)
from .chat_welcome import (  # noqa: F401
    AGENT_ROLES, AGENT_WELCOME,
    _print_welcome, _select_agent,
)
from .chat_streaming import (  # noqa: F401
    _format_session_duration,
    _stream_with_spinner,
    _print_session_summary,
)
from .chat_ui import (  # noqa: F401
    _USE_COLOR, _w, _ANSI_STRIP_RE,
    _rl_wrap, _rl_bold, _rl_green,
    _visible_len, _render_markdown, _spinner,
    _ask_yes_no, _tab_selector,
    _print_welcome as _print_welcome_raw,
    AGENT_COLORS, agent_color,
)
from .chat_commands import (  # noqa: F401
    _CODE_BLOCK_RE, _SKILL_TAG_RE,
    _extract_commands, _extract_skill_requests, _resolve_placeholders,
    _offer_run_commands, _run_single_command,
    _save_command_to_rules, _is_command_trusted, _is_safe_command, _log_auto_run,
    _check_agent_autorun, _load_agent_autorun_config,
    _extract_context_from_output, _command_context,
    _is_valid_command, _ENGLISH_STARTERS,
)
from .chat_server import (  # noqa: F401
    _server_url, _check_server, _check_workspace_trust,
    _get_agents, _stream_chat,
)
from .chat_history import (  # noqa: F401
    HISTORY_DIR, create_session, load_session, add_message,
    list_sessions, delete_session, _save, _make_title,
    _ensure_dir, _session_path,
)
