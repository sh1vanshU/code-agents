"""Slack Bot Bridge — connects Slack to code-agents for conversational queries.

Receives DMs and @mentions from Slack Events API, detects the best agent,
delegates the query to code-agents, and replies in the Slack thread.

Requires:
  CODE_AGENTS_SLACK_BOT_TOKEN   — Slack Bot OAuth token (xoxb-...)
  CODE_AGENTS_SLACK_SIGNING_SECRET — Slack app signing secret
"""

import hashlib
import hmac
import json
import logging
import os
import time
from typing import Optional

logger = logging.getLogger("code_agents.integrations.slack_bot")

# Keyword-to-agent mapping for auto-detection
_AGENT_KEYWORDS: dict[str, list[str]] = {
    "jenkins-cicd": ["build", "deploy", "jenkins", "pipeline", "ci/cd", "cicd"],
    "jira-ops": ["jira", "ticket", "issue", "sprint", "confluence"],
    "code-reviewer": ["review", "pr", "pull request", "code review"],
    "code-tester": ["test", "coverage", "junit", "pytest", "spec"],
    "git-ops": ["git", "branch", "merge", "commit", "checkout", "rebase"],
    "kibana-logs": ["log", "error", "kibana", "exception", "stacktrace"],
    "redash-query": ["query", "sql", "redash", "database", "db"],
}

# Max Slack message length (Slack allows ~4000 chars; leave buffer)
_SLACK_MAX_LENGTH = 3900


class SlackBot:
    """Handles Slack events and delegates to code-agents."""

    def __init__(self):
        self.bot_token: str = os.getenv("CODE_AGENTS_SLACK_BOT_TOKEN", "")
        self.signing_secret: str = os.getenv("CODE_AGENTS_SLACK_SIGNING_SECRET", "")
        self.server_url: str = os.getenv(
            "CODE_AGENTS_PUBLIC_BASE_URL", "http://127.0.0.1:8000"
        )
        self._bot_user_id: str = ""
        self._channel_map: dict[str, str] = self._parse_channel_map()

    @staticmethod
    def _parse_channel_map() -> dict[str, str]:
        """Parse CODE_AGENTS_SLACK_CHANNEL_MAP env var.

        Format: ``channel1=agent1,channel2=agent2``
        Channel IDs (C0...) or names (#deployments) both work.
        """
        raw = os.getenv("CODE_AGENTS_SLACK_CHANNEL_MAP", "")
        if not raw:
            return {}
        mapping: dict[str, str] = {}
        for pair in raw.split(","):
            pair = pair.strip()
            if "=" not in pair:
                continue
            ch, agent = pair.split("=", 1)
            mapping[ch.strip().lstrip("#")] = agent.strip()
        return mapping

    def get_channel_agent(self, channel: str) -> str:
        """Return the mapped agent for a channel, or empty string if unmapped."""
        # Try exact channel ID match first, then name match
        if channel in self._channel_map:
            return self._channel_map[channel]
        return ""

    # ------------------------------------------------------------------
    # Security
    # ------------------------------------------------------------------

    def verify_signature(self, timestamp: str, body: str, signature: str) -> bool:
        """Verify Slack request signature (HMAC-SHA256, timing-safe)."""
        if not self.signing_secret:
            return False
        try:
            ts = float(timestamp)
        except (ValueError, TypeError):
            return False
        if abs(time.time() - ts) > 60 * 5:
            return False  # reject replays older than 5 minutes
        sig_basestring = f"v0:{timestamp}:{body}"
        my_sig = "v0=" + hmac.new(
            self.signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(my_sig, signature)

    # ------------------------------------------------------------------
    # Slack API helpers
    # ------------------------------------------------------------------

    def get_bot_user_id(self) -> str:
        """Get bot's own user ID via auth.test (cached after first call)."""
        if self._bot_user_id:
            return self._bot_user_id
        if not self.bot_token:
            return ""
        import urllib.request

        req = urllib.request.Request(
            "https://slack.com/api/auth.test",
            headers={"Authorization": f"Bearer {self.bot_token}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                if data.get("ok"):
                    self._bot_user_id = data.get("user_id", "")
                    logger.info("Slack bot user ID: %s", self._bot_user_id)
                else:
                    logger.warning("auth.test failed: %s", data.get("error"))
                return self._bot_user_id
        except Exception as e:
            logger.error("auth.test request failed: %s", e)
            return ""

    def send_message(
        self, channel: str, text: str, thread_ts: Optional[str] = None
    ) -> bool:
        """Send a message to a Slack channel or thread."""
        import urllib.request

        payload = json.dumps(
            {
                "channel": channel,
                "text": text,
                **({"thread_ts": thread_ts} if thread_ts else {}),
            }
        ).encode()
        req = urllib.request.Request(
            "https://slack.com/api/chat.postMessage",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.bot_token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                if not data.get("ok"):
                    logger.warning("chat.postMessage error: %s", data.get("error"))
                return data.get("ok", False)
        except Exception as e:
            logger.error("Slack send failed: %s", e)
            return False

    # ------------------------------------------------------------------
    # Agent delegation
    # ------------------------------------------------------------------

    def detect_agent(self, text: str) -> str:
        """Detect which agent to use based on scored keyword matching."""
        text_lower = text.lower()
        scores = {}
        for agent, keywords in _AGENT_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[agent] = score
        if not scores:
            return "auto-pilot"
        best = max(scores, key=scores.get)
        # Confidence threshold: need at least 2 keyword hits for strong match
        if scores[best] < 2 and len(scores) > 1:
            return "auto-pilot"
        return best

    def delegate_to_agent(self, text: str, agent: str = "auto-pilot") -> str:
        """Send the user's question to a code-agents endpoint and return the response."""
        import urllib.request

        payload = json.dumps(
            {
                "model": agent,
                "messages": [{"role": "user", "content": text}],
                "stream": False,
            }
        ).encode()

        for attempt in range(2):
            try:
                req = urllib.request.Request(
                    f"{self.server_url}/v1/agents/{agent}/chat/completions",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=120) as resp:
                    data = json.loads(resp.read())
                    choices = data.get("choices", [])
                    if choices:
                        return choices[0].get("message", {}).get("content", "No response")
                    return "No response from agent"
            except Exception as e:
                if attempt == 0:
                    logger.warning("Agent delegation attempt 1 failed, retrying: %s", e)
                    time.sleep(3)
                else:
                    logger.error("Agent delegation failed after retry: %s", e)
                    return f"Error: Agent timed out after retry — {e}"
        return "Error: unexpected delegation failure"

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def handle_event(self, event: dict) -> Optional[str]:
        """Handle a Slack event (message or app_mention).

        Returns the response text on success, or None if the event was ignored.
        """
        text = event.get("text", "").strip()
        channel = event.get("channel", "")
        thread_ts = event.get("thread_ts") or event.get("ts")
        user = event.get("user", "")

        # Ignore bot's own messages
        bot_id = self.get_bot_user_id()
        if bot_id and user == bot_id:
            return None

        # Strip bot mention from text
        if bot_id:
            text = text.replace(f"<@{bot_id}>", "").strip()

        if not text:
            return None

        # Channel-specific routing takes priority, then keyword detection
        agent = self.get_channel_agent(channel) or self.detect_agent(text)
        logger.info(
            "Slack event: user=%s channel=%s agent=%s text=%s",
            user,
            channel,
            agent,
            text[:80],
        )

        # Typing indicator
        self.send_message(channel, f"Delegating to `{agent}`...", thread_ts)

        # Get response from agent
        response = self.delegate_to_agent(text, agent)

        # Truncate for Slack limit
        if len(response) > _SLACK_MAX_LENGTH:
            response = response[:_SLACK_MAX_LENGTH] + "\n\n... (truncated)"

        # Reply in thread
        self.send_message(channel, response, thread_ts)
        return response
