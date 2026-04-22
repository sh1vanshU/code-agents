"""Slack Bot webhook router — Events API, slash commands, interactive messages."""

from __future__ import annotations

import json
import logging
import os
from urllib.parse import parse_qs

from fastapi import APIRouter, Request, Response

logger = logging.getLogger("code_agents.routers.slack_bot")

router = APIRouter(prefix="/slack", tags=["slack-bot"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_bot():
    from code_agents.integrations.slack_bot import SlackBot
    return SlackBot()


def _verify_request(bot, request: Request, body_str: str) -> bool:
    """Verify Slack request signature. Returns True if valid or signing not configured."""
    if not bot.signing_secret:
        return True
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")
    return bot.verify_signature(timestamp, body_str, signature)


# ---------------------------------------------------------------------------
# Events API
# ---------------------------------------------------------------------------

@router.post("/events")
async def slack_events(request: Request):
    """Handle Slack Events API webhooks (URL verification + event callbacks)."""
    body = await request.body()
    body_str = body.decode()
    data = json.loads(body_str)

    # URL verification challenge (Slack sends this when configuring the endpoint)
    if data.get("type") == "url_verification":
        return {"challenge": data.get("challenge", "")}

    bot = _get_bot()
    if not _verify_request(bot, request, body_str):
        logger.warning("Slack signature verification failed")
        return Response(status_code=401)

    # Handle event callbacks
    if data.get("type") == "event_callback":
        event = data.get("event", {})
        event_type = event.get("type", "")

        if event_type in ("message", "app_mention"):
            # Ignore message subtypes (edits, bot messages with subtype, etc.)
            if event.get("subtype"):
                return {"ok": True}

            # Process in background so Slack gets a fast 200
            import asyncio

            asyncio.create_task(_process_event(bot, event))

    return {"ok": True}


async def _process_event(bot, event: dict) -> None:
    """Process a Slack event in a background thread (network I/O)."""
    import asyncio

    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, bot.handle_event, event)
    except Exception as e:
        logger.error("Slack event processing failed: %s", e, exc_info=True)


# ---------------------------------------------------------------------------
# Slack Slash Command
# ---------------------------------------------------------------------------

@router.post("/slash")
async def slack_slash_command(request: Request):
    """Handle Slack slash command ``/code-agents <text>``.

    Slack posts form-encoded data:
      token, command, text, response_url, trigger_id, user_id, channel_id, ...
    """
    body = await request.body()
    body_str = body.decode()

    bot = _get_bot()
    if not _verify_request(bot, request, body_str):
        logger.warning("Slack slash command signature verification failed")
        return Response(status_code=401)

    form = parse_qs(body_str)
    text = form.get("text", [""])[0].strip()
    user_id = form.get("user_id", [""])[0]
    channel_id = form.get("channel_id", [""])[0]
    response_url = form.get("response_url", [""])[0]

    if not text:
        return {
            "response_type": "ephemeral",
            "text": (
                "*Usage:* `/code-agents <query>`\n"
                "Examples:\n"
                "• `/code-agents review my latest PR`\n"
                "• `/code-agents run tests on auth module`\n"
                "• `/code-agents deploy status`"
            ),
        }

    # Detect agent and process in background
    import asyncio
    asyncio.create_task(
        _process_slash(bot, text, user_id, channel_id, response_url)
    )

    # Immediate ack — Slack requires response within 3s
    agent = bot.detect_agent(text)
    return {
        "response_type": "in_channel",
        "text": f"⏳ Processing with `{agent}`...",
    }


async def _process_slash(
    bot, text: str, user_id: str, channel_id: str, response_url: str
) -> None:
    """Process slash command in background, post result via response_url."""
    import asyncio

    agent = bot.detect_agent(text)

    try:
        response = await asyncio.get_event_loop().run_in_executor(
            None, bot.delegate_to_agent, text, agent
        )
    except Exception as e:
        logger.error("Slash command delegation failed: %s", e, exc_info=True)
        response = f"❌ Error: {e}"

    # Truncate for Slack
    if len(response) > 3900:
        response = response[:3900] + "\n\n... (truncated)"

    # Post to response_url (delayed response) — validate it's a Slack URL to prevent SSRF
    _SLACK_RESPONSE_URL_PREFIXES = (
        "https://hooks.slack.com/",
        "https://slack.com/",
    )
    if response_url and response_url.startswith(_SLACK_RESPONSE_URL_PREFIXES):
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(response_url, json={
                    "response_type": "in_channel",
                    "text": f"*Agent `{agent}`* (asked by <@{user_id}>):\n{response}",
                    "replace_original": False,
                })
        except Exception as e:
            logger.error("Failed to post slash response: %s", e)
    elif response_url:
        logger.warning("Rejected non-Slack response_url: %s", response_url[:80])
    else:
        # Fallback: post to channel directly
        bot.send_message(channel_id, response)


# ---------------------------------------------------------------------------
# Interactive Messages (Block Kit callbacks)
# ---------------------------------------------------------------------------

@router.post("/interactive")
async def slack_interactive(request: Request):
    """Handle Slack interactive message callbacks (buttons, dropdowns).

    Slack posts form-encoded ``payload=<JSON>`` for interactive components.
    """
    body = await request.body()
    body_str = body.decode()

    bot = _get_bot()
    if not _verify_request(bot, request, body_str):
        logger.warning("Slack interactive signature verification failed")
        return Response(status_code=401)

    form = parse_qs(body_str)
    payload_str = form.get("payload", ["{}"])[0]
    payload = json.loads(payload_str)

    action_type = payload.get("type", "")
    user = payload.get("user", {})
    user_id = user.get("id", "")
    channel = payload.get("channel", {})
    channel_id = channel.get("id", "")
    response_url = payload.get("response_url", "")

    actions = payload.get("actions", [])
    if not actions:
        return {"ok": True}

    action = actions[0]
    action_id = action.get("action_id", "")
    action_value = action.get("value", "")

    # Handle select menu
    if action.get("type") == "static_select":
        selected = action.get("selected_option", {})
        action_value = selected.get("value", "")

    logger.info(
        "Slack interactive: action=%s value=%s user=%s channel=%s",
        action_id, action_value, user_id, channel_id,
    )

    # --- Agent selection ---
    if action_id == "select_agent":
        import asyncio
        # Get original query from the message blocks
        original_text = _extract_query_from_blocks(payload.get("message", {}))
        asyncio.create_task(
            _process_interactive_agent(bot, action_value, original_text, user_id, response_url)
        )
        return {
            "text": f"⏳ Delegating to `{action_value}`...",
            "replace_original": True,
        }

    if action_id == "auto_detect_agent":
        original_text = _extract_query_from_blocks(payload.get("message", {}))
        agent = bot.detect_agent(original_text)
        import asyncio
        asyncio.create_task(
            _process_interactive_agent(bot, agent, original_text, user_id, response_url)
        )
        return {
            "text": f"⏳ Auto-detected `{agent}`, processing...",
            "replace_original": True,
        }

    # --- Approval flow ---
    if action_id == "approve_action":
        return {
            "text": f"✅ Approved by <@{user_id}> (ref: {action_value})",
            "replace_original": True,
        }

    if action_id == "reject_action":
        return {
            "text": f"❌ Rejected by <@{user_id}> (ref: {action_value})",
            "replace_original": True,
        }

    return {"ok": True}


def _extract_query_from_blocks(message: dict) -> str:
    """Extract original query text from Block Kit message blocks."""
    for block in message.get("blocks", []):
        text_obj = block.get("text", {})
        text = text_obj.get("text", "")
        if text.startswith("*Query:*"):
            # Strip markdown formatting
            query = text.replace("*Query:*", "").strip().lstrip(">").strip()
            return query
    return ""


async def _process_interactive_agent(
    bot, agent: str, query: str, user_id: str, response_url: str
) -> None:
    """Delegate to agent from interactive selection and post result."""
    import asyncio

    try:
        response = await asyncio.get_event_loop().run_in_executor(
            None, bot.delegate_to_agent, query, agent
        )
    except Exception as e:
        logger.error("Interactive agent delegation failed: %s", e, exc_info=True)
        response = f"❌ Error: {e}"

    if len(response) > 3900:
        response = response[:3900] + "\n\n... (truncated)"

    if response_url:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(response_url, json={
                    "response_type": "in_channel",
                    "text": f"*Agent `{agent}`* (asked by <@{user_id}>):\n{response}",
                    "replace_original": False,
                })
        except Exception as e:
            logger.error("Failed to post interactive response: %s", e)


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

@router.get("/status")
async def slack_status():
    """Check Slack bot configuration status."""
    bot_token = bool(os.getenv("CODE_AGENTS_SLACK_BOT_TOKEN", ""))
    signing_secret = bool(os.getenv("CODE_AGENTS_SLACK_SIGNING_SECRET", ""))
    webhook_url = bool(os.getenv("CODE_AGENTS_SLACK_WEBHOOK_URL", ""))
    channel_map = os.getenv("CODE_AGENTS_SLACK_CHANNEL_MAP", "")
    return {
        "configured": bot_token and signing_secret,
        "bot_token_set": bot_token,
        "signing_secret_set": signing_secret,
        "webhook_url_set": webhook_url,
        "channel_map": channel_map if channel_map else None,
        "endpoints": {
            "events": "/slack/events",
            "slash_command": "/slack/slash",
            "interactive": "/slack/interactive",
            "status": "/slack/status",
        },
    }
