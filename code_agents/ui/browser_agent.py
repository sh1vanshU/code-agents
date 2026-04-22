"""Browser Interaction Agent — fetch pages, extract text, scrape API docs.

Lightweight browser agent that uses ``urllib.request`` to navigate pages,
extract readable text, discover links, and parse API documentation.

Usage::

    from code_agents.ui.browser_agent import BrowserAgent

    agent = BrowserAgent()
    result = agent.navigate("https://docs.example.com")
    print(result["title"], result["status"])
    api_docs = agent.extract_api_docs("https://docs.example.com/api")
"""

from __future__ import annotations

import logging
import re
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

logger = logging.getLogger("code_agents.ui.browser_agent")

# Max content size to prevent memory issues (5 MB)
_MAX_CONTENT_SIZE = 5 * 1024 * 1024
_USER_AGENT = "code-agents-browser/1.0"
_TIMEOUT = 30


# ---------------------------------------------------------------------------
# Simple HTML text extractor
# ---------------------------------------------------------------------------

class _TextExtractor(HTMLParser):
    """Extracts visible text from HTML, stripping tags."""

    def __init__(self) -> None:
        super().__init__()
        self._text: list[str] = []
        self._skip = False
        self._skip_tags = {"script", "style", "noscript", "svg", "head"}
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self._skip_tags:
            self._skip = True
        if tag.lower() == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._skip_tags:
            self._skip = False
        if tag.lower() == "title":
            self._in_title = False
        if tag.lower() in ("p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"):
            self._text.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data.strip()
        if not self._skip:
            cleaned = data.strip()
            if cleaned:
                self._text.append(cleaned)

    def get_text(self) -> str:
        raw = " ".join(self._text)
        # Collapse whitespace
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


# ---------------------------------------------------------------------------
# Link extractor
# ---------------------------------------------------------------------------

class _LinkExtractor(HTMLParser):
    """Extracts all <a href> links from HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            for name, value in attrs:
                if name.lower() == "href" and value:
                    self.links.append(value)


# ---------------------------------------------------------------------------
# API documentation extractor
# ---------------------------------------------------------------------------

class _ApiDocExtractor(HTMLParser):
    """Extracts API documentation patterns: methods, endpoints, descriptions."""

    def __init__(self) -> None:
        super().__init__()
        self.entries: list[dict[str, str]] = []
        self._current_text = ""
        self._in_code = False
        self._in_heading = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in ("code", "pre"):
            self._in_code = True
        if tag.lower() in ("h1", "h2", "h3", "h4"):
            self._in_heading = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in ("code", "pre"):
            self._in_code = False
            text = self._current_text.strip()
            if text:
                self._try_parse_endpoint(text)
            self._current_text = ""
        if tag.lower() in ("h1", "h2", "h3", "h4"):
            self._in_heading = False

    def handle_data(self, data: str) -> None:
        if self._in_code:
            self._current_text += data

    def _try_parse_endpoint(self, text: str) -> None:
        """Try to parse API endpoint from code block text."""
        methods = ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS")
        for method in methods:
            pattern = rf"^({method})\s+(/\S+)"
            m = re.match(pattern, text.strip(), re.IGNORECASE)
            if m:
                self.entries.append({
                    "method": m.group(1).upper(),
                    "path": m.group(2),
                    "raw": text.strip()[:200],
                })
                return

        # Also catch curl commands
        curl_match = re.search(r"curl\s+.*?-X\s*(\w+)\s+.*?(https?://\S+|/\S+)", text)
        if curl_match:
            self.entries.append({
                "method": curl_match.group(1).upper(),
                "path": curl_match.group(2),
                "raw": text.strip()[:200],
            })


# ---------------------------------------------------------------------------
# BrowserAgent
# ---------------------------------------------------------------------------

class BrowserAgent:
    """Lightweight browser agent for fetching and parsing web pages."""

    def __init__(self, timeout: int = _TIMEOUT) -> None:
        self.timeout = timeout
        logger.debug("BrowserAgent initialized (timeout=%ds)", timeout)

    def navigate(self, url: str) -> dict[str, Any]:
        """Fetch a page and return structured result.

        Args:
            url: The URL to navigate to.

        Returns:
            Dict with keys: title, text, links, status, url, content_length.
        """
        logger.info("Navigating to %s", url)
        html, status = self._fetch_page_with_status(url)

        text = self._extract_text(html)
        links = self._extract_links(html, url)
        title = self._extract_title(html)

        result = {
            "url": url,
            "status": status,
            "title": title,
            "text": text[:10000],  # Cap text length
            "links": links[:100],  # Cap link count
            "content_length": len(html),
        }

        logger.info("Fetched %s: status=%d, title='%s', %d links",
                     url, status, title[:50], len(links))
        return result

    def extract_api_docs(self, url: str) -> list[dict[str, str]]:
        """Scrape API documentation from a URL.

        Looks for HTTP method + path patterns in code blocks, headings,
        and curl commands.

        Args:
            url: URL of the API documentation page.

        Returns:
            List of dicts with 'method', 'path', and 'raw' keys.
        """
        logger.info("Extracting API docs from %s", url)
        html, _ = self._fetch_page_with_status(url)

        # Use dedicated parser
        parser = _ApiDocExtractor()
        try:
            parser.feed(html)
        except Exception as e:
            logger.warning("HTML parsing error: %s", e)

        # Also regex scan the full HTML for common patterns
        api_patterns = re.findall(
            r"(GET|POST|PUT|DELETE|PATCH)\s+(/[a-zA-Z0-9_/{}:.-]+)",
            html,
            re.IGNORECASE,
        )
        seen = {(e["method"], e["path"]) for e in parser.entries}
        for method, path in api_patterns:
            key = (method.upper(), path)
            if key not in seen:
                parser.entries.append({
                    "method": method.upper(),
                    "path": path,
                    "raw": f"{method.upper()} {path}",
                })
                seen.add(key)

        logger.info("Found %d API endpoints from %s", len(parser.entries), url)
        return parser.entries

    def _fetch_page(self, url: str) -> str:
        """Fetch a page and return raw HTML."""
        html, _ = self._fetch_page_with_status(url)
        return html

    def _fetch_page_with_status(self, url: str) -> tuple[str, int]:
        """Fetch a page, return (html, status_code)."""
        try:
            req = Request(url, headers={"User-Agent": _USER_AGENT})
            with urlopen(req, timeout=self.timeout) as resp:
                data = resp.read(_MAX_CONTENT_SIZE)
                status = resp.getcode() or 200
                return data.decode("utf-8", errors="replace"), status
        except HTTPError as e:
            logger.error("HTTP error fetching %s: %d", url, e.code)
            body = ""
            try:
                body = e.read(_MAX_CONTENT_SIZE).decode("utf-8", errors="replace")
            except Exception:
                pass
            return body, e.code
        except (URLError, OSError) as e:
            logger.error("Failed to fetch %s: %s", url, e)
            return f"<!-- fetch failed: {e} -->", 0

    def _extract_text(self, html: str) -> str:
        """Extract visible text from HTML."""
        parser = _TextExtractor()
        try:
            parser.feed(html)
        except Exception as e:
            logger.warning("Text extraction error: %s", e)
            return ""
        return parser.get_text()

    def _extract_title(self, html: str) -> str:
        """Extract page title."""
        parser = _TextExtractor()
        try:
            parser.feed(html)
        except Exception:
            pass
        return parser.title or ""

    def _extract_links(self, html: str, base_url: str) -> list[str]:
        """Extract and resolve all links from HTML."""
        parser = _LinkExtractor()
        try:
            parser.feed(html)
        except Exception as e:
            logger.warning("Link extraction error: %s", e)
            return []

        resolved: list[str] = []
        for link in parser.links:
            # Skip javascript:, mailto:, #anchors
            if link.startswith(("javascript:", "mailto:", "#", "data:")):
                continue
            try:
                full_url = urljoin(base_url, link)
                resolved.append(full_url)
            except Exception:
                continue
        return resolved
