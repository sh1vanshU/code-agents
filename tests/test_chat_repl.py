"""Tests for code_agents.chat.chat_repl — agentic follow-up loop."""

from __future__ import annotations

from unittest.mock import patch

import pytest

# _extract_commands, _offer_run_commands, _stream_with_spinner are imported at
# module-level in chat_repl, so we patch them on the module.
# is_edit_mode and check_cost_guard are imported inside the function body, so
# we patch them at their origin modules.
MOD = "code_agents.chat.chat_repl"
EDIT_MODE = "code_agents.chat.chat_input.is_edit_mode"
COST_GUARD = "code_agents.core.token_tracker.check_cost_guard"


def _kw(**overrides):
    """Return minimal kwargs for run_agentic_followup_loop."""
    defaults = dict(
        full_response=["some response text"],
        cwd="/tmp/repo",
        url="http://localhost:8000",
        state={"repo_path": "/tmp/repo", "session_id": "s1"},
        current_agent="coder",
        system_context="You are an assistant.",
        superpower=False,
    )
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# 1. No commands in response → returns immediately
# ---------------------------------------------------------------------------
@patch(EDIT_MODE, return_value=False)
@patch(COST_GUARD, return_value=True)
@patch(f"{MOD}._extract_commands", return_value=[])
def test_no_commands_returns_immediately(mock_extract, mock_guard, mock_edit):
    from code_agents.chat.chat_repl import run_agentic_followup_loop

    resp, count = run_agentic_followup_loop(**_kw())
    assert count == 0
    assert resp == ["some response text"]
    mock_extract.assert_called_once()


# ---------------------------------------------------------------------------
# 2. Commands found → full loop iteration
# ---------------------------------------------------------------------------
@patch(EDIT_MODE, return_value=False)
@patch(COST_GUARD, return_value=True)
@patch(f"{MOD}._extract_commands", side_effect=[["echo hello"], []])
@patch(
    f"{MOD}._offer_run_commands",
    return_value=[{"command": "echo hello", "output": "hello"}],
)
@patch(f"{MOD}._stream_with_spinner", return_value=["follow-up text"])
def test_commands_found_runs_loop(mock_stream, mock_offer, mock_extract, mock_guard, mock_edit):
    from code_agents.chat.chat_repl import run_agentic_followup_loop

    resp, count = run_agentic_followup_loop(**_kw())
    assert count == 1
    mock_offer.assert_called_once()
    mock_stream.assert_called_once()
    assert resp == ["follow-up text"]


# ---------------------------------------------------------------------------
# 3. Multiple loop iterations
# ---------------------------------------------------------------------------
@patch(EDIT_MODE, return_value=False)
@patch(COST_GUARD, return_value=True)
@patch(f"{MOD}._extract_commands", side_effect=[["cmd1"], ["cmd2"], []])
@patch(
    f"{MOD}._offer_run_commands",
    side_effect=[
        [{"command": "cmd1", "output": "out1"}],
        [{"command": "cmd2", "output": "out2"}],
    ],
)
@patch(f"{MOD}._stream_with_spinner", side_effect=[["resp2"], ["resp3"]])
def test_multiple_loop_iterations(mock_stream, mock_offer, mock_extract, mock_guard, mock_edit):
    from code_agents.chat.chat_repl import run_agentic_followup_loop

    resp, count = run_agentic_followup_loop(**_kw())
    assert count == 2
    assert mock_stream.call_count == 2
    assert resp == ["resp3"]


# ---------------------------------------------------------------------------
# 4. Cost guard exceeded → breaks loop
# ---------------------------------------------------------------------------
@patch(EDIT_MODE, return_value=False)
@patch(COST_GUARD, return_value=False)
@patch(f"{MOD}._extract_commands")
def test_cost_guard_exceeded_breaks(mock_extract, mock_guard, mock_edit):
    from code_agents.chat.chat_repl import run_agentic_followup_loop

    resp, count = run_agentic_followup_loop(**_kw())
    assert count == 0
    mock_extract.assert_not_called()


# ---------------------------------------------------------------------------
# 5. KeyboardInterrupt in _offer_run_commands → breaks
# ---------------------------------------------------------------------------
@patch(EDIT_MODE, return_value=False)
@patch(COST_GUARD, return_value=True)
@patch(f"{MOD}._extract_commands", return_value=["ls"])
@patch(f"{MOD}._offer_run_commands", side_effect=KeyboardInterrupt)
def test_keyboard_interrupt_breaks(mock_offer, mock_extract, mock_guard, mock_edit):
    from code_agents.chat.chat_repl import run_agentic_followup_loop

    resp, count = run_agentic_followup_loop(**_kw())
    assert count == 0


# ---------------------------------------------------------------------------
# 6. EOFError in _offer_run_commands → breaks
# ---------------------------------------------------------------------------
@patch(EDIT_MODE, return_value=False)
@patch(COST_GUARD, return_value=True)
@patch(f"{MOD}._extract_commands", return_value=["ls"])
@patch(f"{MOD}._offer_run_commands", side_effect=EOFError)
def test_eof_error_breaks(mock_offer, mock_extract, mock_guard, mock_edit):
    from code_agents.chat.chat_repl import run_agentic_followup_loop

    resp, count = run_agentic_followup_loop(**_kw())
    assert count == 0


# ---------------------------------------------------------------------------
# 7. Exception in _offer_run_commands → breaks with error print
# ---------------------------------------------------------------------------
@patch(EDIT_MODE, return_value=False)
@patch(COST_GUARD, return_value=True)
@patch(f"{MOD}._extract_commands", return_value=["ls"])
@patch(f"{MOD}._offer_run_commands", side_effect=RuntimeError("boom"))
def test_generic_exception_breaks(mock_offer, mock_extract, mock_guard, mock_edit):
    from code_agents.chat.chat_repl import run_agentic_followup_loop

    resp, count = run_agentic_followup_loop(**_kw())
    assert count == 0


# ---------------------------------------------------------------------------
# 8. Empty exec_results → breaks
# ---------------------------------------------------------------------------
@patch(EDIT_MODE, return_value=False)
@patch(COST_GUARD, return_value=True)
@patch(f"{MOD}._extract_commands", return_value=["echo hi"])
@patch(f"{MOD}._offer_run_commands", return_value=[])
def test_empty_exec_results_breaks(mock_offer, mock_extract, mock_guard, mock_edit):
    from code_agents.chat.chat_repl import run_agentic_followup_loop

    resp, count = run_agentic_followup_loop(**_kw())
    assert count == 0


# ---------------------------------------------------------------------------
# 9. superpower=True sets _loop_auto_run from start
# ---------------------------------------------------------------------------
@patch(EDIT_MODE, return_value=False)
@patch(COST_GUARD, return_value=True)
@patch(f"{MOD}._extract_commands", side_effect=[["echo x"], []])
@patch(f"{MOD}._offer_run_commands", return_value=[{"command": "echo x", "output": "x"}])
@patch(f"{MOD}._stream_with_spinner", return_value=["done"])
def test_superpower_sets_auto_run(mock_stream, mock_offer, mock_extract, mock_guard, mock_edit):
    from code_agents.chat.chat_repl import run_agentic_followup_loop

    resp, count = run_agentic_followup_loop(**_kw(superpower=True))
    assert count == 1
    call_kwargs = mock_offer.call_args
    assert call_kwargs[1]["auto_run"] is True
    assert call_kwargs[1]["superpower"] is True


# ---------------------------------------------------------------------------
# 10. edit mode sets _loop_auto_run and _effective_superpower
# ---------------------------------------------------------------------------
@patch(EDIT_MODE, return_value=True)
@patch(COST_GUARD, return_value=True)
@patch(f"{MOD}._extract_commands", side_effect=[["echo x"], []])
@patch(f"{MOD}._offer_run_commands", return_value=[{"command": "echo x", "output": "x"}])
@patch(f"{MOD}._stream_with_spinner", return_value=["done"])
def test_edit_mode_sets_auto_run_and_superpower(mock_stream, mock_offer, mock_extract, mock_guard, mock_edit):
    from code_agents.chat.chat_repl import run_agentic_followup_loop

    resp, count = run_agentic_followup_loop(**_kw())
    assert count == 1
    call_kwargs = mock_offer.call_args
    assert call_kwargs[1]["auto_run"] is True
    assert call_kwargs[1]["superpower"] is True


# ---------------------------------------------------------------------------
# 11. CODE_AGENTS_MAX_LOOPS env var respected
# ---------------------------------------------------------------------------
@patch(EDIT_MODE, return_value=False)
@patch(COST_GUARD, return_value=True)
@patch(f"{MOD}._extract_commands", return_value=["echo loop"])
@patch(
    f"{MOD}._offer_run_commands",
    return_value=[{"command": "echo loop", "output": "loop"}],
)
@patch(f"{MOD}._stream_with_spinner", return_value=["resp"])
def test_max_loops_env_var(mock_stream, mock_offer, mock_extract, mock_guard, mock_edit, monkeypatch):
    from code_agents.chat.chat_repl import run_agentic_followup_loop

    monkeypatch.setenv("CODE_AGENTS_MAX_LOOPS", "2")
    resp, count = run_agentic_followup_loop(**_kw())
    assert count == 2
    assert mock_stream.call_count == 2


# ---------------------------------------------------------------------------
# 12. Empty full_response → returns immediately
# ---------------------------------------------------------------------------
@patch(EDIT_MODE, return_value=False)
def test_empty_response_returns_immediately(mock_edit):
    from code_agents.chat.chat_repl import run_agentic_followup_loop

    resp, count = run_agentic_followup_loop(**_kw(full_response=[]))
    assert count == 0
    assert resp == []


# ---------------------------------------------------------------------------
# 13. Output truncation to 2000 chars in feedback
# ---------------------------------------------------------------------------
@patch(EDIT_MODE, return_value=False)
@patch(COST_GUARD, return_value=True)
@patch(f"{MOD}._extract_commands", side_effect=[["cat bigfile"], []])
@patch(
    f"{MOD}._offer_run_commands",
    return_value=[{"command": "cat bigfile", "output": "A" * 5000}],
)
@patch(f"{MOD}._stream_with_spinner", return_value=["ok"])
def test_output_truncated_in_feedback(mock_stream, mock_offer, mock_extract, mock_guard, mock_edit):
    from code_agents.chat.chat_repl import run_agentic_followup_loop

    run_agentic_followup_loop(**_kw())
    call_args = mock_stream.call_args
    messages = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get("messages")
    user_msg = messages[1]["content"]
    assert "A" * 2000 in user_msg
    assert "A" * 2001 not in user_msg


# ---------------------------------------------------------------------------
# 14. None output in exec_results → "(no output)"
# ---------------------------------------------------------------------------
@patch(EDIT_MODE, return_value=False)
@patch(COST_GUARD, return_value=True)
@patch(f"{MOD}._extract_commands", side_effect=[["true"], []])
@patch(
    f"{MOD}._offer_run_commands",
    return_value=[{"command": "true", "output": None}],
)
@patch(f"{MOD}._stream_with_spinner", return_value=["ok"])
def test_none_output_becomes_no_output(mock_stream, mock_offer, mock_extract, mock_guard, mock_edit):
    from code_agents.chat.chat_repl import run_agentic_followup_loop

    run_agentic_followup_loop(**_kw())
    call_args = mock_stream.call_args
    messages = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get("messages")
    user_msg = messages[1]["content"]
    assert "(no output)" in user_msg


# ---------------------------------------------------------------------------
# 15. _stream_with_spinner receives correct parameters
# ---------------------------------------------------------------------------
@patch(EDIT_MODE, return_value=False)
@patch(COST_GUARD, return_value=True)
@patch(f"{MOD}._extract_commands", side_effect=[["echo x"], []])
@patch(
    f"{MOD}._offer_run_commands",
    return_value=[{"command": "echo x", "output": "x"}],
)
@patch(f"{MOD}._stream_with_spinner", return_value=["done"])
def test_stream_with_spinner_params(mock_stream, mock_offer, mock_extract, mock_guard, mock_edit):
    from code_agents.chat.chat_repl import run_agentic_followup_loop

    kwargs = _kw()
    run_agentic_followup_loop(**kwargs)

    call_args, call_kwargs = mock_stream.call_args
    assert call_args[0] == "http://localhost:8000"
    assert call_args[1] == "coder"
    assert call_kwargs.get("session_id", call_args[3]) == "s1"
    assert call_kwargs.get("label") == "Analyzing results..." or (len(call_args) > 6 and call_args[6] == "Analyzing results...")


# ---------------------------------------------------------------------------
# 16. auto_run becomes True after first loop
# ---------------------------------------------------------------------------
@patch(EDIT_MODE, return_value=False)
@patch(COST_GUARD, return_value=True)
@patch(f"{MOD}._extract_commands", side_effect=[["cmd1"], ["cmd2"], []])
@patch(
    f"{MOD}._offer_run_commands",
    side_effect=[
        [{"command": "cmd1", "output": "o1"}],
        [{"command": "cmd2", "output": "o2"}],
    ],
)
@patch(f"{MOD}._stream_with_spinner", side_effect=[["r2"], ["r3"]])
def test_auto_run_true_after_first_loop(mock_stream, mock_offer, mock_extract, mock_guard, mock_edit):
    from code_agents.chat.chat_repl import run_agentic_followup_loop

    run_agentic_followup_loop(**_kw())
    first_call = mock_offer.call_args_list[0]
    assert first_call[1]["auto_run"] is False
    second_call = mock_offer.call_args_list[1]
    assert second_call[1]["auto_run"] is True


# ---------------------------------------------------------------------------
# 17. feedback message structure
# ---------------------------------------------------------------------------
@patch(EDIT_MODE, return_value=False)
@patch(COST_GUARD, return_value=True)
@patch(f"{MOD}._extract_commands", side_effect=[["echo a"], []])
@patch(
    f"{MOD}._offer_run_commands",
    return_value=[
        {"command": "echo a", "output": "aaa"},
        {"command": "echo b", "output": "bbb"},
    ],
)
@patch(f"{MOD}._stream_with_spinner", return_value=["ok"])
def test_feedback_structure_multiple_results(mock_stream, mock_offer, mock_extract, mock_guard, mock_edit):
    from code_agents.chat.chat_repl import run_agentic_followup_loop

    run_agentic_followup_loop(**_kw())
    messages = mock_stream.call_args[0][2]
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    body = messages[1]["content"]
    assert "Command: echo a" in body
    assert "Output:\naaa" in body
    assert "---" in body
    assert "Command: echo b" in body
    assert "I ran the following commands" in body
