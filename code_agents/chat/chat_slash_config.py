"""Config switching slash commands: /model, /backend, /theme."""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("code_agents.chat.chat_slash_config")

from .chat_ui import bold, green, yellow, dim, cyan


def _handle_config(command: str, arg: str, state: dict, url: str) -> Optional[str]:
    """Handle configuration-related slash commands."""

    if command == "/model":
        from code_agents.core.config import agent_loader
        _model_shortcuts = {
            "opus": "claude-opus-4-6",
            "sonnet": "claude-sonnet-4-6",
            "haiku": "claude-haiku-4-5-20251001",
        }
        current_agent_cfg = agent_loader.get(state.get("agent", ""))
        if not arg:
            current_model = state.get("_model_override") or (current_agent_cfg.model if current_agent_cfg else "unknown")
            try:
                from .command_panel import show_panel
                from .command_panel_options import get_model_options
                title, subtitle, opts = get_model_options(current_model)
                idx = show_panel(title, subtitle, opts)
                if idx is not None:
                    new_model = opts[idx]["name"]
                    state["_model_override"] = new_model
                    if current_agent_cfg:
                        current_agent_cfg.model = new_model
                    print(f"  {green('✓')} Model switched to: {bold(new_model)}")
                else:
                    print(f"  {dim('Model unchanged.')}")
                print()
            except Exception:
                print(f"  Current model: {bold(current_model)}")
                print(f"  Shortcuts: {dim('opus, sonnet, haiku')}")
                print(f"  Usage: /model <model-name>")
                print()
        else:
            new_model = _model_shortcuts.get(arg.lower(), arg)
            state["_model_override"] = new_model
            if current_agent_cfg:
                current_agent_cfg.model = new_model
            print(f"  {green('✓')} Model switched to: {bold(new_model)}")
            print()

    elif command == "/backend":
        from code_agents.core.config import agent_loader
        _backend_shortcuts = {
            "local": "local",
            "ollama": "local",
            "cursor": "cursor",
            "claude": "claude",
            "claude-cli": "claude-cli",
            "claude-api": "claude",
        }
        current_agent_cfg = agent_loader.get(state.get("agent", ""))
        if not arg:
            current_backend = state.get("_backend_override") or (current_agent_cfg.backend if current_agent_cfg else "unknown")
            try:
                from .command_panel import show_panel
                from .command_panel_options import get_backend_options
                title, subtitle, opts = get_backend_options(current_backend)
                idx = show_panel(title, subtitle, opts)
                if idx is not None:
                    new_backend = opts[idx]["name"]
                    state["_backend_override"] = new_backend
                    if current_agent_cfg:
                        current_agent_cfg.backend = new_backend
                    # Auto-switch model if switching to claude-cli with a cursor model
                    if new_backend == "claude-cli" and current_agent_cfg:
                        cur_model = current_agent_cfg.model or ""
                        cur_lower = cur_model.lower()
                        if "composer" in cur_lower or "cursor" in cur_lower:
                            cli_model = os.getenv("CODE_AGENTS_CLAUDE_CLI_MODEL", "claude-sonnet-4-6")
                            current_agent_cfg.model = cli_model
                            state["_model_override"] = cli_model
                            print(f"  {green('✓')} Backend → {bold(new_backend)}, model → {bold(cli_model)}")
                        else:
                            print(f"  {green('✓')} Backend switched to: {bold(new_backend)}")
                    else:
                        print(f"  {green('✓')} Backend switched to: {bold(new_backend)}")
                else:
                    print(f"  {dim('Backend unchanged.')}")
                print()
            except Exception:
                print(f"  Current backend: {bold(current_backend)}")
                print(f"  Options: {dim('local, cursor, claude, claude-cli')}")
                print(f"  Usage: /backend <name>")
                print()
        else:
            new_backend = _backend_shortcuts.get(arg.lower().strip(), arg.lower().strip())
            state["_backend_override"] = new_backend
            if current_agent_cfg:
                current_agent_cfg.backend = new_backend
            # Auto-switch model if switching to claude-cli with a cursor model
            if new_backend == "claude-cli" and current_agent_cfg:
                cur_model = current_agent_cfg.model or ""
                cur_lower = cur_model.lower()
                if "composer" in cur_lower or "cursor" in cur_lower:
                    cli_model = os.getenv("CODE_AGENTS_CLAUDE_CLI_MODEL", "claude-sonnet-4-6")
                    current_agent_cfg.model = cli_model
                    state["_model_override"] = cli_model
                    print(f"  {green('✓')} Backend → {bold(new_backend)}, model → {bold(cli_model)}")
                else:
                    print(f"  {green('✓')} Backend switched to: {bold(new_backend)}")
            else:
                print(f"  {green('✓')} Backend switched to: {bold(new_backend)}")
            print()

    elif command == "/theme":
        from .chat_theme import (
            get_theme, set_theme, save_theme,
            theme_selector, THEME_DISPLAY_NAMES,
        )
        if arg:
            # Direct set: /theme dark, /theme light, etc.
            result = set_theme(arg)
            if result == arg.strip().lower():
                save_theme(result)
                display = THEME_DISPLAY_NAMES.get(result, result)
                print(f"  {green('\u2713')} Theme set to: {bold(display)}")
            else:
                print(f"  {yellow('Unknown theme:')} {arg}")
                print(f"  {dim('Available: dark, light, dark-colorblind, light-colorblind, dark-ansi, light-ansi')}")
            print()
        else:
            # Interactive selector
            current = get_theme()
            try:
                from .command_panel import show_panel
                from .command_panel_options import get_theme_options
                title, subtitle, opts = get_theme_options(current)
                idx = show_panel(title, subtitle, opts)
                if idx is not None:
                    choice = opts[idx]["name"]
                    set_theme(choice)
                    save_theme(choice)
                    display = THEME_DISPLAY_NAMES.get(choice, choice)
                    print(f"  {green('\u2713')} Theme set to: {bold(display)}")
                else:
                    print(f"  {dim('Theme unchanged.')}")
            except Exception:
                current_display = THEME_DISPLAY_NAMES.get(current, current)
                print(f"  Current theme: {bold(current_display)}")
                print()
                choice = theme_selector()
                if choice:
                    set_theme(choice)
                    save_theme(choice)
                    display = THEME_DISPLAY_NAMES.get(choice, choice)
                    print(f"  {green('\u2713')} Theme set to: {bold(display)}")
                else:
                    print(f"  {dim('Theme unchanged.')}")
            print()

    else:
        return "_not_handled"

    return None
