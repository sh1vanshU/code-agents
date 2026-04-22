"""CLI Slack commands — test, send, status, channels."""

from __future__ import annotations

import asyncio
import logging
import os

from .cli_helpers import _colors, _load_env, _server_url, _api_get

logger = logging.getLogger("code_agents.cli.cli_slack")


def cmd_slack(args: list[str] | None = None):
    """Manage Slack integration — test, send, status, channels."""
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    if not args:
        _slack_help(bold, green, yellow, dim, cyan)
        return

    sub = args[0].lower()

    if sub == "status":
        _slack_status(bold, green, yellow, red, dim)
    elif sub == "test":
        _slack_test(args[1:], bold, green, yellow, red, dim)
    elif sub == "send":
        msg = " ".join(args[1:]) if len(args) > 1 else ""
        _slack_send(msg, bold, green, yellow, red, dim)
    elif sub == "channels":
        _slack_channels(bold, green, yellow, dim, cyan)
    elif sub == "help":
        _slack_help(bold, green, yellow, dim, cyan)
    else:
        print(red(f"  Unknown subcommand: {sub}"))
        print(dim("  Run: code-agents slack help"))
        print()


def _slack_help(bold, green, yellow, dim, cyan):
    print()
    print(bold("  Slack Integration"))
    print()
    print(f"  {cyan('code-agents slack status')}     {dim('Show Slack configuration status')}")
    print(f"  {cyan('code-agents slack test')}       {dim('Send a test webhook message')}")
    print(f"  {cyan('code-agents slack test <url>')} {dim('Test a specific webhook URL')}")
    print(f"  {cyan('code-agents slack send <msg>')} {dim('Send a message via webhook')}")
    print(f"  {cyan('code-agents slack channels')}   {dim('Show channel-to-agent mappings')}")
    print()


def _slack_status(bold, green, yellow, red, dim):
    print()
    print(bold("  Slack Configuration"))
    print()

    bot_token = bool(os.getenv("CODE_AGENTS_SLACK_BOT_TOKEN", ""))
    signing_secret = bool(os.getenv("CODE_AGENTS_SLACK_SIGNING_SECRET", ""))
    webhook_url = os.getenv("CODE_AGENTS_SLACK_WEBHOOK_URL", "")
    channel_map = os.getenv("CODE_AGENTS_SLACK_CHANNEL_MAP", "")

    _status_line = lambda label, ok: print(
        f"  {green('✓') if ok else red('✗')} {label}: {green('configured') if ok else yellow('not set')}"
    )

    _status_line("Bot Token (CODE_AGENTS_SLACK_BOT_TOKEN)", bot_token)
    _status_line("Signing Secret (CODE_AGENTS_SLACK_SIGNING_SECRET)", signing_secret)
    _status_line("Webhook URL (CODE_AGENTS_SLACK_WEBHOOK_URL)", bool(webhook_url))
    _status_line("Channel Map (CODE_AGENTS_SLACK_CHANNEL_MAP)", bool(channel_map))

    print()

    # Check server status
    data = _api_get("/slack/status")
    if data:
        print(f"  Server endpoint: {green('reachable')}")
    else:
        print(f"  Server endpoint: {dim('not running / unreachable')}")
    print()

    if not bot_token and not webhook_url:
        print(dim("  Run: code-agents init --slack"))
        print()


def _slack_test(args: list[str], bold, green, yellow, red, dim):
    webhook_url = args[0] if args else os.getenv("CODE_AGENTS_SLACK_WEBHOOK_URL", "")
    if not webhook_url:
        print(red("  No webhook URL. Set CODE_AGENTS_SLACK_WEBHOOK_URL or pass URL as argument."))
        print(dim("  Usage: code-agents slack test [webhook-url]"))
        print()
        return

    print(dim("  Sending test message..."))

    from code_agents.domain.notifications import send_slack

    success = asyncio.run(
        send_slack("🧪 *Code Agents* — Slack webhook test successful!", webhook_url=webhook_url)
    )
    if success:
        print(f"  {green('✓ Test message sent successfully!')}")
    else:
        print(f"  {red('✗ Failed to send test message.')}")
        print(dim("  Check the webhook URL and try again."))
    print()


def _slack_send(message: str, bold, green, yellow, red, dim):
    if not message:
        print(yellow("  Usage: code-agents slack send <message>"))
        print(dim("  Example: code-agents slack send 'Deploy v2.1.0 complete'"))
        print()
        return

    webhook_url = os.getenv("CODE_AGENTS_SLACK_WEBHOOK_URL", "")
    if not webhook_url:
        print(red("  No webhook URL configured. Set CODE_AGENTS_SLACK_WEBHOOK_URL."))
        print()
        return

    from code_agents.domain.notifications import send_slack

    success = asyncio.run(send_slack(message, webhook_url=webhook_url))
    if success:
        print(f"  {green('✓ Message sent.')}")
    else:
        print(f"  {red('✗ Failed to send message.')}")
    print()


def _slack_channels(bold, green, yellow, dim, cyan):
    print()
    print(bold("  Channel-to-Agent Mappings"))
    print()

    channel_map = os.getenv("CODE_AGENTS_SLACK_CHANNEL_MAP", "")
    if not channel_map:
        print(dim("  No channel mappings configured."))
        print()
        print(dim("  Set CODE_AGENTS_SLACK_CHANNEL_MAP to map channels to agents:"))
        print(f"  {cyan('CODE_AGENTS_SLACK_CHANNEL_MAP=C0123=jenkins-cicd,C0456=code-reviewer')}")
        print()
        print(dim("  Format: channel_id=agent_name,channel_id=agent_name"))
        print(dim("  Channel IDs or names (without #) both work."))
        print()
        return

    from code_agents.integrations.slack_bot import SlackBot
    bot = SlackBot()

    for ch, agent in bot._channel_map.items():
        print(f"  {cyan(ch)} → {green(agent)}")

    print()
    print(dim(f"  {len(bot._channel_map)} mapping(s) configured"))
    print()
