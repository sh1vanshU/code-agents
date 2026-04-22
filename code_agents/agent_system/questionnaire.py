"""
Interactive Questionnaire — structured Q&A for agent clarification.

Uses questionary (prompt_toolkit-based) for interactive selectors and
rich for styled display. Falls back to plain input() when TTY unavailable.

When agents need user input, they present numbered questions with
multiple-choice options. Q&A pairs saved to session to avoid re-asking.
"""
from __future__ import annotations

import logging
import sys
from typing import Optional

logger = logging.getLogger("code_agents.agent_system.questionnaire")

# Lazy imports — questionary and rich are optional at import time
_HAS_QUESTIONARY = False
_HAS_RICH = False

try:
    import questionary
    from questionary import Style as QStyle, Choice
    _HAS_QUESTIONARY = True
except ImportError:
    pass

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich import box
    _HAS_RICH = True
except ImportError:
    pass


# ──────────────────────────────────────────────
# Styles
# ──────────────────────────────────────────────

_Q_STYLE = None
if _HAS_QUESTIONARY:
    _Q_STYLE = QStyle([
        ("qmark", "fg:cyan bold"),
        ("question", "fg:white bold"),
        ("answer", "fg:green bold"),
        ("pointer", "fg:cyan bold"),
        ("highlighted", "fg:cyan bold"),
        ("selected", "fg:green"),
        ("separator", "fg:#6c6c6c"),
        ("instruction", "fg:#6c6c6c"),
        ("text", "fg:white"),
    ])

_console = Console(stderr=True) if _HAS_RICH else None


def _safe_ask(question):
    """Run a questionary question safely, even inside a running asyncio event loop.

    prompt_toolkit's Application.run() detects a running loop and tries
    run_async(), creating unawaited coroutines. We avoid this by running
    in a thread when an event loop is active.
    """
    import asyncio
    try:
        asyncio.get_running_loop()
        # Running loop exists — run in a separate thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(question.unsafe_ask).result()
    except RuntimeError:
        # No running loop — safe to call directly
        return question.unsafe_ask()


# ──────────────────────────────────────────────
# Core selectors
# ──────────────────────────────────────────────

def _question_selector(prompt_text: str, options: list[str], default: int = 0) -> int:
    """Arrow-key selector for questionnaire prompts.

    Returns 0..N-1 index of selected option, or *default* on error/cancel.
    """
    if sys.stdout.isatty():
        try:
            from code_agents.chat.command_panel import show_panel
            panel_options = [{"name": opt, "description": "", "active": False} for opt in options]
            idx = show_panel(prompt_text or "Select", "", panel_options, default)
            return idx if idx is not None else default
        except (KeyboardInterrupt, EOFError):
            return default
        except Exception as e:
            logger.debug("command_panel selector failed (%s), using fallback", e)

    # Fallback: plain text
    try:
        for i, opt in enumerate(options):
            letter = chr(ord('a') + i)
            marker = " *" if i == default else ""
            print(f"     {letter}) {opt}{marker}")
        raw = input(f"  Choose [{chr(ord('a') + default)}]: ").strip().lower()
        if len(raw) == 1 and 'a' <= raw <= chr(ord('a') + len(options) - 1):
            return ord(raw) - ord('a')
    except (EOFError, KeyboardInterrupt):
        pass
    return default


def _multi_selector(prompt_text: str, options: list[str], statuses: list[str] | None = None) -> list[int]:
    """Arrow-key multi-select with Space to toggle, Enter to confirm.

    Returns list of 0-based indices of selected options.
    """
    if _HAS_QUESTIONARY and sys.stdout.isatty():
        try:
            choices = []
            for i, opt in enumerate(options):
                label = f"{opt} {statuses[i]}" if statuses else opt
                choices.append(Choice(label, value=i, checked=False))

            result = _safe_ask(questionary.checkbox(
                prompt_text or "Select items:",
                choices=choices,
                style=_Q_STYLE,
                instruction="(↑↓ navigate · space = check/uncheck · enter = done — pick at least one)",
                pointer="\u203a",
            ))
            if result is None:
                return []
            return result
        except (KeyboardInterrupt, EOFError):
            return []
        except Exception as e:
            logger.debug("questionary checkbox failed (%s), using fallback", e)

    # Fallback: comma-separated numbers
    try:
        for i, opt in enumerate(options):
            status = f" {statuses[i]}" if statuses else ""
            print(f"  {i + 1}. {opt}{status}")
        raw = input(f"  {prompt_text} (comma-separated numbers, e.g. 1,3,5): ").strip()
        indices = []
        for n in raw.split(","):
            n = n.strip()
            if n.isdigit() and 1 <= int(n) <= len(options):
                indices.append(int(n) - 1)
        return indices
    except (EOFError, KeyboardInterrupt):
        return []


def prompt_indices_numeric(
    title: str,
    options: list[str],
    statuses: list[str] | None = None,
) -> list[int]:
    """Pick one or more items by 1-based index (comma-separated).

    Reliable in Cursor, SSH, and CI — avoids questionary checkbox quirks where
    Space/Enter can submit an empty selection on some terminals.
    """
    statuses = statuses or ["·"] * len(options)
    print()
    print(f"  {title}")
    for i, opt in enumerate(options):
        st = f"  {statuses[i]}" if i < len(statuses) else ""
        print(f"    {i + 1}. {opt}{st}")
    print()
    while True:
        try:
            raw = input(
                "  Which sections? Type numbers separated by commas (e.g. 1 or 1,3,5) — q to abort: ",
            ).strip()
        except (EOFError, KeyboardInterrupt):
            return []
        if raw.lower() in ("q", "quit", "exit"):
            return []
        indices: list[int] = []
        for part in raw.replace(" ", "").split(","):
            if not part:
                continue
            if part.isdigit():
                n = int(part)
                if 1 <= n <= len(options):
                    indices.append(n - 1)
        if indices:
            return sorted(set(indices))
        print(
            "  \033[33mNo valid selection.\033[0m "
            "Use numbers from the list (e.g. 1 for the first line).",
        )


# ──────────────────────────────────────────────
# Question asking
# ──────────────────────────────────────────────

def ask_question(
    question: str,
    options: list[str],
    allow_other: bool = True,
    default: int = 0,
    **kwargs,
) -> dict:
    """
    Present a question with interactive selector.

    Returns: {"question": str, "answer": str, "option_idx": int, "is_other": bool}
    """
    logger.info("Asking question: %s (%d options)", question, len(options))

    all_options = list(options)
    if allow_other:
        all_options.append("Other \u2014 describe in detail")

    # Question header — always use stdout (not Rich stderr) for alignment
    # with command_panel selector which writes to stdout
    print()
    print(f"  \033[1;33m\u2753 {question}\033[0m")
    print()

    idx = _question_selector("", all_options, default=default)

    is_other = allow_other and idx == len(all_options) - 1

    if is_other:
        try:
            if _HAS_QUESTIONARY and sys.stdout.isatty():
                detail = _safe_ask(questionary.text(
                    "Describe in detail:",
                    style=_Q_STYLE,
                )) or ""
            else:
                detail = input("  Describe in detail: ").strip()
        except (EOFError, KeyboardInterrupt):
            detail = ""
        return {"question": question, "answer": detail or "No details provided", "option_idx": idx, "is_other": True}

    logger.debug("Answer received: option %d ('%s')", idx, all_options[idx])
    return {"question": question, "answer": all_options[idx], "option_idx": idx, "is_other": False}


def ask_multiple(questions: list[dict]) -> list[dict]:
    """
    Ask multiple questions in sequence.

    Each question dict: {"question": str, "options": list[str], "default": 0}
    Returns list of answer dicts.
    """
    answers = []
    for q in questions:
        answer = ask_question(
            question=q["question"],
            options=q["options"],
            allow_other=q.get("allow_other", True),
            default=q.get("default", 0),
        )
        answers.append(answer)
    return answers


def ask_multiple_tabbed(questions: list[dict]) -> list[dict] | None:
    """Present multiple questions as a sequential wizard with step indicators.

    Each question: ``{"question": str, "options": list[str], "default": 0}``

    Returns answer dicts or None if cancelled.
    """
    if not questions:
        return None

    n = len(questions)

    # Show step progress header with rich
    if _HAS_RICH and sys.stdout.isatty():
        _console.print()
        _console.print(Panel(
            f"[bold cyan]{n} questions to answer[/bold cyan]",
            border_style="cyan",
            box=box.ROUNDED,
            padding=(0, 2),
        ))

    answers = []
    for i, q in enumerate(questions):
        step_label = f"[{i + 1}/{n}]"

        # Print step label to stdout (same stream as command_panel selector)
        # Using print() instead of _console.print() to avoid stderr/stdout misalignment
        print(f"  \033[2m{step_label}\033[0m")

        answer = ask_question(
            question=q["question"],
            options=q["options"],
            allow_other=q.get("allow_other", True),
            default=q.get("default", 0),
        )

        # User cancelled (Ctrl+C during questionary returns default, but we check)
        if answer is None:
            return None

        answers.append(answer)

    # Show summary table
    _show_answers_summary(answers)

    # Submit on Enter (Ctrl+C to cancel)
    if sys.stdout.isatty():
        try:
            if _HAS_RICH:
                _console.print("  [dim]Press[/dim] [bold cyan]Enter[/bold cyan] [dim]to submit · Ctrl+C to cancel[/dim]")
            else:
                print("  Press Enter to submit · Ctrl+C to cancel")
            input()
        except (KeyboardInterrupt, EOFError):
            return None

    return answers


def _show_answers_summary(answers: list[dict]) -> None:
    """Display a rich summary table of collected answers."""
    if not answers:
        return

    if _HAS_RICH and sys.stdout.isatty():
        table = Table(
            title="Your Answers",
            box=box.ROUNDED,
            border_style="cyan",
            title_style="bold cyan",
            padding=(0, 1),
        )
        table.add_column("Question", style="white", max_width=50)
        table.add_column("Answer", style="green bold")

        for qa in answers:
            q_text = qa["question"]
            if len(q_text) > 50:
                q_text = q_text[:47] + "..."
            a_text = qa["answer"]
            if qa.get("is_other"):
                a_text += " [dim](custom)[/dim]"
            table.add_row(q_text, a_text)

        _console.print()
        _console.print(table)
        _console.print()
    else:
        print()
        print("  --- Your Answers ---")
        for qa in answers:
            other_tag = " (custom)" if qa.get("is_other") else ""
            print(f"  Q: {qa['question']}")
            print(f"  A: {qa['answer']}{other_tag}")
            print()


# ──────────────────────────────────────────────
# Formatting for agent context
# ──────────────────────────────────────────────

def format_qa_for_prompt(qa_pairs: list[dict]) -> str:
    """Format Q&A pairs for injection into agent context."""
    if not qa_pairs:
        return ""
    lines = ["User clarifications:"]
    for qa in qa_pairs:
        other_tag = " (custom answer)" if qa.get("is_other") else ""
        lines.append(f"  Q: {qa['question']}")
        lines.append(f"  A: {qa['answer']}{other_tag}")
        lines.append("")
    return "\n".join(lines)


# ──────────────────────────────────────────────
# Suggestion engine
# ──────────────────────────────────────────────

def suggest_questions(user_input: str, agent_name: str) -> list[str]:
    """Suggest relevant question templates based on user input and agent context.

    Returns list of template keys that might be relevant.
    """
    input_lower = user_input.lower()
    suggestions = []

    keyword_map = {
        "environment": ["deploy", "env", "staging", "dev", "prod", "uat"],
        "database": ["db", "database", "migration", "sql", "schema"],
        "deploy_strategy": ["deploy", "rollout", "canary", "blue-green"],
        "deploy_environment_class": ["deploy", "dev", "qa", "environment"],
        "branch": ["branch", "checkout", "merge", "release"],
        "test_scope": ["test", "regression", "coverage", "qa"],
        "build_location": ["build", "compile", "mvn", "gradle", "make"],
        "review_depth": ["review", "pr", "pull request", "code review"],
        "jira_type": ["jira", "ticket", "issue", "create ticket"],
        "rollback_confirm": ["rollback", "revert", "undo deploy"],
        "jenkins_folder": ["jenkins", "folder", "pipeline", "cicd"],
        "deploy_action": ["build", "deploy", "jenkins", "cicd"],
    }

    for template_key, keywords in keyword_map.items():
        if any(kw in input_lower for kw in keywords):
            suggestions.append(template_key)

    return suggestions


# ──────────────────────────────────────────────
# Session helpers
# ──────────────────────────────────────────────

def get_session_answers(state: dict) -> list[dict]:
    """Get all Q&A pairs from current session."""
    return state.get("_qa_pairs", [])


def has_been_answered(state: dict, question: str) -> bool:
    """Check if a question has already been answered in this session."""
    for qa in state.get("_qa_pairs", []):
        if qa["question"] == question:
            return True
    return False


# ──────────────────────────────────────────────
# Pre-built question templates
# ──────────────────────────────────────────────

TEMPLATES = {
    "environment": {
        "question": "Which environment should this target?",
        "options": ["dev", "dev-stable", "staging", "qa", "uat"],
    },
    "database": {
        "question": "Which database should this target?",
        "options": ["PostgreSQL (primary)", "MySQL (legacy)", "Redis (cache)", "MongoDB"],
    },
    "deploy_strategy": {
        "question": "What deployment strategy?",
        "options": ["Rolling update", "Blue-green", "Canary (gradual)", "Recreate (downtime OK)"],
    },
    "branch": {
        "question": "Which branch to use?",
        "options": ["release", "main", "develop", "Current branch"],
    },
    "test_scope": {
        "question": "What test scope?",
        "options": ["Unit tests only", "Unit + integration", "Full regression", "Smoke tests only"],
    },
    "review_depth": {
        "question": "How thorough should the review be?",
        "options": ["Quick scan (5 min)", "Standard review", "Deep review (security + perf)", "Architecture review"],
    },
    "build_location": {
        "question": "Where should I build/test?",
        "options": ["Local (run commands here)", "Jenkins (trigger remote build)"],
    },
    "jira_type": {
        "question": "What type of Jira ticket?",
        "options": ["Bug", "Task", "Story", "Sub-task", "Epic"],
    },
    "deploy_environment_class": {
        "question": "Which environment class to deploy?",
        "options": ["Dev", "QA"],
        "follow_up": {
            "key": "deploy_environment",
            "question": "Which specific environment? (e.g. dev, dev2, qa-stable)",
            "type": "text",  # free-text input — supports any env name
        },
    },
    "jenkins_folder": {
        "question": "Which Jenkins folder contains the job?",
        "options": ["pg2", "DB", "mgv", "rtdd"],
    },
    "deploy_action": {
        "question": "What do you want to do?",
        "options": ["Build only", "Build + Deploy", "Deploy only (have image tag)"],
    },
    "deploy_confirm": {
        "question": "Proceed with deployment?",
        "options": ["Yes \u2014 deploy now", "No \u2014 cancel"],
    },
    "rollback_confirm": {
        "question": "Rollback to previous version?",
        "options": ["Yes \u2014 rollback now", "No \u2014 investigate further"],
    },
    "cicd_action": {
        "question": "What CI/CD action do you need?",
        "options": [
            "Build only",
            "Build + Deploy",
            "Deploy only (I have an image tag)",
            "Check build status",
            "View build logs",
            "Troubleshoot a failed build",
        ],
    },
    "cicd_branch": {
        "question": "Which branch to build from?",
        "options": ["Current branch (auto-detect)", "main", "release", "develop"],
    },
    "cicd_java_version": {
        "question": "Which Java version?",
        "options": ["java21", "java17", "java11"],
    },
    "cicd_sub_env": {
        "question": "Which sub-environment?",
        "options": ["dev", "qa4", "qa5", "qa6", "staging"],
    },
}
