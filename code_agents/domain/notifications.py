"""
Notification system — send alerts for build/deploy/test/agent/audit status.

Supports: Slack webhooks (plain text + Block Kit). Future: email, Teams, Discord.
Config: CODE_AGENTS_SLACK_WEBHOOK_URL env var.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger("code_agents.domain.notifications")


# ---------------------------------------------------------------------------
# Core send helpers
# ---------------------------------------------------------------------------

async def send_slack(message: str, webhook_url: str = "") -> bool:
    """Send a Slack notification via webhook (plain text)."""
    url = webhook_url or os.getenv("CODE_AGENTS_SLACK_WEBHOOK_URL", "")
    if not url:
        logger.debug("Slack webhook not configured, skipping notification")
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, json={"text": message})
            return r.status_code == 200
    except Exception as e:
        logger.warning("Slack notification failed: %s", e)
        return False


async def send_slack_blocks(
    blocks: list[dict[str, Any]],
    text: str = "",
    webhook_url: str = "",
) -> bool:
    """Send a Slack Block Kit message via webhook."""
    url = webhook_url or os.getenv("CODE_AGENTS_SLACK_WEBHOOK_URL", "")
    if not url:
        logger.debug("Slack webhook not configured, skipping notification")
        return False
    payload: dict[str, Any] = {"blocks": blocks}
    if text:
        payload["text"] = text  # fallback for notifications
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, json=payload)
            return r.status_code == 200
    except Exception as e:
        logger.warning("Slack Block Kit notification failed: %s", e)
        return False


# ---------------------------------------------------------------------------
# Block Kit builders
# ---------------------------------------------------------------------------

def block_section(text: str, accessory: dict | None = None) -> dict:
    """Build a Block Kit section block with mrkdwn text."""
    blk: dict[str, Any] = {
        "type": "section",
        "text": {"type": "mrkdwn", "text": text},
    }
    if accessory:
        blk["accessory"] = accessory
    return blk


def block_divider() -> dict:
    return {"type": "divider"}


def block_header(text: str) -> dict:
    return {"type": "header", "text": {"type": "plain_text", "text": text}}


def block_actions(elements: list[dict]) -> dict:
    return {"type": "actions", "elements": elements}


def block_context(texts: list[str]) -> dict:
    return {
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": t} for t in texts],
    }


def button(text: str, action_id: str, value: str = "", style: str = "") -> dict:
    """Build a Block Kit button element."""
    btn: dict[str, Any] = {
        "type": "button",
        "text": {"type": "plain_text", "text": text},
        "action_id": action_id,
    }
    if value:
        btn["value"] = value
    if style in ("primary", "danger"):
        btn["style"] = style
    return btn


def static_select(
    placeholder: str,
    action_id: str,
    options: list[tuple[str, str]],
) -> dict:
    """Build a Block Kit static_select element. options = [(text, value), ...]."""
    return {
        "type": "static_select",
        "placeholder": {"type": "plain_text", "text": placeholder},
        "action_id": action_id,
        "options": [
            {
                "text": {"type": "plain_text", "text": t},
                "value": v,
            }
            for t, v in options
        ],
    }


# ---------------------------------------------------------------------------
# Formatters — plain text (original)
# ---------------------------------------------------------------------------

def notify_build_status(job: str, status: str, build_number: int = 0, url: str = "") -> str:
    """Format build status notification."""
    emoji = "✅" if status == "SUCCESS" else "❌" if status == "FAILURE" else "⏳"
    msg = f"{emoji} *Build {status}*: `{job}` #{build_number}"
    if url:
        msg += f"\n<{url}|View build>"
    return msg


def notify_deploy_status(app: str, env: str, status: str, version: str = "") -> str:
    """Format deploy status notification."""
    emoji = "🚀" if status == "Healthy" else "🔴" if status in ("Degraded", "Unknown") else "⏳"
    msg = f"{emoji} *Deploy {status}*: `{app}` → `{env}`"
    if version:
        msg += f" (v{version})"
    return msg


def notify_test_status(passed: int, failed: int, total: int, branch: str = "") -> str:
    """Format test status notification."""
    emoji = "✅" if failed == 0 else "❌"
    msg = f"{emoji} *Tests*: {passed}/{total} passed, {failed} failed"
    if branch:
        msg += f" (`{branch}`)"
    return msg


# ---------------------------------------------------------------------------
# Formatters — new (agent, error, PR review, audit, daily digest)
# ---------------------------------------------------------------------------

def notify_agent_completion(
    agent: str, query: str, status: str = "success", elapsed: float = 0.0
) -> str:
    """Format agent completion notification."""
    emoji = "✅" if status == "success" else "❌" if status == "error" else "⏳"
    query_preview = (query[:60] + "...") if len(query) > 60 else query
    msg = f"{emoji} *Agent `{agent}`*: {status}"
    msg += f"\n> {query_preview}"
    if elapsed > 0:
        msg += f"\n⏱️ {elapsed:.1f}s"
    return msg


def notify_error(
    source: str, error: str, severity: str = "error", traceback: str = ""
) -> str:
    """Format error alert notification."""
    emoji = "🔴" if severity == "error" else "🟡" if severity == "warning" else "ℹ️"
    msg = f"{emoji} *{severity.upper()}* in `{source}`\n```{error}```"
    if traceback:
        tb_preview = traceback[-500:] if len(traceback) > 500 else traceback
        msg += f"\n```{tb_preview}```"
    return msg


def notify_pr_review(
    pr_title: str,
    pr_number: int,
    verdict: str,
    issues: int = 0,
    url: str = "",
) -> str:
    """Format PR review summary notification."""
    emoji = "✅" if verdict == "approved" else "⚠️" if verdict == "changes_requested" else "💬"
    msg = f"{emoji} *PR Review*: #{pr_number} {pr_title}"
    msg += f"\nVerdict: *{verdict}*"
    if issues > 0:
        msg += f" | {issues} issue(s) found"
    if url:
        msg += f"\n<{url}|View PR>"
    return msg


def notify_audit_result(
    score: int,
    total_rules: int,
    passed: int,
    failed: int,
    repo: str = "",
) -> str:
    """Format audit result notification."""
    emoji = "✅" if failed == 0 else "⚠️" if failed <= 3 else "❌"
    msg = f"{emoji} *Audit Result*: {score}/100"
    msg += f"\n{passed}/{total_rules} rules passed, {failed} failed"
    if repo:
        msg += f"\nRepo: `{repo}`"
    return msg


def notify_daily_digest(
    agents_used: int = 0,
    queries_handled: int = 0,
    errors: int = 0,
    top_agent: str = "",
) -> str:
    """Format daily digest notification."""
    msg = "📊 *Daily Digest*"
    msg += f"\n• Queries handled: *{queries_handled}*"
    msg += f"\n• Agents used: *{agents_used}*"
    msg += f"\n• Errors: *{errors}*"
    if top_agent:
        msg += f"\n• Top agent: `{top_agent}`"
    return msg


# ---------------------------------------------------------------------------
# Block Kit formatters (rich messages)
# ---------------------------------------------------------------------------

def notify_agent_completion_blocks(
    agent: str, query: str, status: str = "success", elapsed: float = 0.0
) -> list[dict]:
    """Build Block Kit blocks for agent completion."""
    emoji = "✅" if status == "success" else "❌" if status == "error" else "⏳"
    query_preview = (query[:120] + "...") if len(query) > 120 else query
    blocks = [
        block_header(f"{emoji} Agent Completion"),
        block_section(f"*Agent:* `{agent}` | *Status:* {status}"),
        block_section(f"*Query:*\n>{query_preview}"),
    ]
    if elapsed > 0:
        blocks.append(block_context([f"⏱️ {elapsed:.1f}s"]))
    blocks.append(block_divider())
    return blocks


def notify_agent_selection_blocks(query: str, agents: list[str]) -> list[dict]:
    """Build Block Kit blocks with agent selection dropdown."""
    query_preview = (query[:120] + "...") if len(query) > 120 else query
    options = [(a, a) for a in agents]
    blocks = [
        block_header("🤖 Select Agent"),
        block_section(f"*Query:*\n>{query_preview}"),
        block_actions([
            static_select("Choose an agent", "select_agent", options),
            button("Auto-detect", "auto_detect_agent", style="primary"),
        ]),
    ]
    return blocks


def notify_approval_blocks(
    action: str, detail: str, request_id: str = ""
) -> list[dict]:
    """Build Block Kit blocks for an approval flow."""
    blocks = [
        block_header("⚡ Approval Required"),
        block_section(f"*Action:* {action}\n*Details:*\n>{detail}"),
        block_actions([
            button("Approve", "approve_action", value=request_id, style="primary"),
            button("Reject", "reject_action", value=request_id, style="danger"),
        ]),
    ]
    return blocks