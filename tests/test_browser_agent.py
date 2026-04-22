"""Tests for the browser interaction agent."""

from __future__ import annotations

from unittest.mock import patch, MagicMock
from urllib.error import HTTPError, URLError

import pytest

from code_agents.ui.browser_agent import (
    BrowserAgent,
    _TextExtractor,
    _LinkExtractor,
    _ApiDocExtractor,
)


class TestTextExtractor:
    """Test HTML text extraction."""

    def test_basic_text(self):
        parser = _TextExtractor()
        parser.feed("<html><body><p>Hello World</p></body></html>")
        assert "Hello World" in parser.get_text()

    def test_strips_scripts(self):
        parser = _TextExtractor()
        parser.feed("<html><body><script>var x=1;</script><p>Visible</p></body></html>")
        text = parser.get_text()
        assert "Visible" in text
        assert "var x" not in text

    def test_strips_styles(self):
        parser = _TextExtractor()
        parser.feed("<html><head><style>body{color:red}</style></head><body>Text</body></html>")
        text = parser.get_text()
        assert "Text" in text
        assert "color" not in text

    def test_extracts_title(self):
        parser = _TextExtractor()
        parser.feed("<html><head><title>My Page</title></head><body></body></html>")
        assert parser.title == "My Page"


class TestLinkExtractor:
    """Test link extraction."""

    def test_extracts_links(self):
        parser = _LinkExtractor()
        parser.feed('<a href="/about">About</a><a href="https://example.com">Ext</a>')
        assert "/about" in parser.links
        assert "https://example.com" in parser.links

    def test_empty_html(self):
        parser = _LinkExtractor()
        parser.feed("<html><body>No links</body></html>")
        assert len(parser.links) == 0


class TestApiDocExtractor:
    """Test API documentation extraction."""

    def test_extracts_endpoint_from_code(self):
        parser = _ApiDocExtractor()
        parser.feed("<code>GET /api/v1/users</code>")
        assert len(parser.entries) == 1
        assert parser.entries[0]["method"] == "GET"
        assert parser.entries[0]["path"] == "/api/v1/users"

    def test_extracts_post_endpoint(self):
        parser = _ApiDocExtractor()
        parser.feed("<pre>POST /api/v1/orders</pre>")
        assert len(parser.entries) == 1
        assert parser.entries[0]["method"] == "POST"

    def test_no_endpoints(self):
        parser = _ApiDocExtractor()
        parser.feed("<p>Just some text</p>")
        assert len(parser.entries) == 0


class TestBrowserAgentNavigate:
    """Test BrowserAgent.navigate."""

    def test_navigate_success(self):
        agent = BrowserAgent()
        mock_html = "<html><head><title>Test</title></head><body><p>Content</p><a href='/link'>Link</a></body></html>"
        with patch.object(agent, "_fetch_page_with_status", return_value=(mock_html, 200)):
            result = agent.navigate("http://example.com")
        assert result["status"] == 200
        assert result["title"] == "Test"
        assert "Content" in result["text"]
        assert len(result["links"]) >= 1

    def test_navigate_error(self):
        agent = BrowserAgent()
        with patch.object(agent, "_fetch_page_with_status", return_value=("<!-- error -->", 0)):
            result = agent.navigate("http://invalid.test")
        assert result["status"] == 0


class TestBrowserAgentExtractApi:
    """Test BrowserAgent.extract_api_docs."""

    def test_extract_api_docs(self):
        agent = BrowserAgent()
        mock_html = """
        <html><body>
        <code>GET /api/users</code>
        <code>POST /api/orders</code>
        <p>DELETE /api/items/{id}</p>
        </body></html>
        """
        with patch.object(agent, "_fetch_page_with_status", return_value=(mock_html, 200)):
            docs = agent.extract_api_docs("http://example.com/api")
        methods = {d["method"] for d in docs}
        assert "GET" in methods
        assert "POST" in methods
        assert "DELETE" in methods

    def test_extract_empty_page(self):
        agent = BrowserAgent()
        with patch.object(agent, "_fetch_page_with_status", return_value=("<html></html>", 200)):
            docs = agent.extract_api_docs("http://example.com")
        assert len(docs) == 0


class TestExtractLinks:
    """Test link extraction with base URL resolution."""

    def test_resolves_relative_links(self):
        agent = BrowserAgent()
        html = '<a href="/about">About</a><a href="page.html">Page</a>'
        links = agent._extract_links(html, "http://example.com/docs/")
        assert "http://example.com/about" in links
        assert "http://example.com/docs/page.html" in links

    def test_skips_javascript_links(self):
        agent = BrowserAgent()
        html = '<a href="javascript:void(0)">JS</a><a href="/real">Real</a>'
        links = agent._extract_links(html, "http://example.com")
        assert len(links) == 1
        assert "real" in links[0]
