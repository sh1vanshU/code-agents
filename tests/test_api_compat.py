"""Tests for api_compat.py — API compatibility checker."""

from __future__ import annotations

import os
from unittest.mock import patch, MagicMock

import pytest

from code_agents.api.api_compat import (
    APICompatChecker,
    APICompatReport,
    EndpointInfo,
    _DECORATOR_RE,
    _PREFIX_RE,
)


# ---------------------------------------------------------------------------
# EndpointInfo
# ---------------------------------------------------------------------------


class TestEndpointInfo:
    """Test EndpointInfo dataclass."""

    def test_key_format(self):
        ep = EndpointInfo(method="GET", path="/api/v1/users")
        assert ep.key == "GET /api/v1/users"

    def test_equality(self):
        a = EndpointInfo(method="POST", path="/api/v1/pay")
        b = EndpointInfo(method="POST", path="/api/v1/pay")
        assert a == b

    def test_inequality(self):
        a = EndpointInfo(method="GET", path="/api/v1/pay")
        b = EndpointInfo(method="POST", path="/api/v1/pay")
        assert a != b

    def test_hash(self):
        a = EndpointInfo(method="GET", path="/users")
        b = EndpointInfo(method="GET", path="/users")
        assert hash(a) == hash(b)
        assert len({a, b}) == 1


# ---------------------------------------------------------------------------
# Pattern matching
# ---------------------------------------------------------------------------


class TestPatterns:
    """Test regex patterns for endpoint extraction."""

    def test_decorator_get(self):
        match = _DECORATOR_RE.search('@router.get("/branches")')
        assert match
        assert match.group(1) == "get"
        assert match.group(2) == "/branches"

    def test_decorator_post(self):
        match = _DECORATOR_RE.search('@app.post("/v1/chat/completions")')
        assert match
        assert match.group(1) == "post"
        assert match.group(2) == "/v1/chat/completions"

    def test_prefix_extraction(self):
        match = _PREFIX_RE.search('router = APIRouter(prefix="/git", tags=["git"])')
        assert match
        assert match.group(1) == "/git"


# ---------------------------------------------------------------------------
# APICompatChecker — parse_endpoints_from_source
# ---------------------------------------------------------------------------


class TestParseEndpoints:
    """Test endpoint parsing from source code."""

    def test_basic_route(self):
        source = '''
router = APIRouter()

@router.get("/health")
def health():
    return {"ok": True}
'''
        checker = APICompatChecker.__new__(APICompatChecker)
        endpoints = checker._parse_endpoints_from_source(source, "app.py")
        assert len(endpoints) == 1
        assert endpoints[0].method == "GET"
        assert endpoints[0].path == "/health"

    def test_prefix_applied(self):
        source = '''
router = APIRouter(prefix="/git", tags=["git"])

@router.get("/branches")
def branches():
    pass

@router.post("/push")
def push():
    pass
'''
        checker = APICompatChecker.__new__(APICompatChecker)
        endpoints = checker._parse_endpoints_from_source(source, "routers/git_ops.py")
        assert len(endpoints) == 2
        assert endpoints[0].path == "/git/branches"
        assert endpoints[0].method == "GET"
        assert endpoints[1].path == "/git/push"
        assert endpoints[1].method == "POST"

    def test_multiple_methods(self):
        source = '''
router = APIRouter()

@router.get("/items")
def list_items():
    pass

@router.post("/items")
def create_item():
    pass

@router.delete("/items")
def delete_item():
    pass
'''
        checker = APICompatChecker.__new__(APICompatChecker)
        endpoints = checker._parse_endpoints_from_source(source)
        methods = {ep.method for ep in endpoints}
        assert methods == {"GET", "POST", "DELETE"}


# ---------------------------------------------------------------------------
# scan_current_api
# ---------------------------------------------------------------------------


class TestScanCurrentApi:
    """Test scanning endpoints from current working tree."""

    def test_discovers_endpoints(self, tmp_path):
        """scan_current_api finds endpoints in router files."""
        routers_dir = tmp_path / "routers"
        routers_dir.mkdir()
        (routers_dir / "users.py").write_text('''
from fastapi import APIRouter
router = APIRouter(prefix="/users", tags=["users"])

@router.get("/")
def list_users():
    pass

@router.post("/")
def create_user():
    pass
''')
        checker = APICompatChecker(cwd=str(tmp_path))
        endpoints = checker.scan_current_api()
        assert len(endpoints) == 2
        keys = {ep.key for ep in endpoints}
        assert "GET /users/" in keys
        assert "POST /users/" in keys


# ---------------------------------------------------------------------------
# compare
# ---------------------------------------------------------------------------


class TestCompare:
    """Test endpoint comparison logic."""

    def test_detects_added_endpoints(self):
        """New endpoints in HEAD are added (non-breaking)."""
        checker = APICompatChecker.__new__(APICompatChecker)
        checker.cwd = "/tmp"
        checker.base_ref = "v1.0.0"

        base = [
            EndpointInfo(method="GET", path="/api/v1/users"),
        ]
        head = [
            EndpointInfo(method="GET", path="/api/v1/users"),
            EndpointInfo(method="POST", path="/api/v1/refund"),
        ]

        with patch.object(checker, "scan_current_api", return_value=head), \
             patch.object(checker, "scan_base_api", return_value=base):
            report = checker.compare()

        assert len(report.added_endpoints) == 1
        assert report.added_endpoints[0].path == "/api/v1/refund"
        assert report.breaking_count == 0
        assert report.non_breaking_count == 1

    def test_detects_removed_endpoints_breaking(self):
        """Removed endpoints are breaking changes."""
        checker = APICompatChecker.__new__(APICompatChecker)
        checker.cwd = "/tmp"
        checker.base_ref = "v1.0.0"

        base = [
            EndpointInfo(method="GET", path="/api/v1/users"),
            EndpointInfo(method="DELETE", path="/api/v1/legacy/payment"),
        ]
        head = [
            EndpointInfo(method="GET", path="/api/v1/users"),
        ]

        with patch.object(checker, "scan_current_api", return_value=head), \
             patch.object(checker, "scan_base_api", return_value=base):
            report = checker.compare()

        assert len(report.removed_endpoints) == 1
        assert report.removed_endpoints[0].path == "/api/v1/legacy/payment"
        assert report.breaking_count == 1

    def test_detects_changed_method_breaking(self):
        """Changing HTTP method on same path is breaking."""
        checker = APICompatChecker.__new__(APICompatChecker)
        checker.cwd = "/tmp"
        checker.base_ref = "v1.0.0"

        base = [
            EndpointInfo(method="GET", path="/api/v1/data"),
        ]
        head = [
            EndpointInfo(method="POST", path="/api/v1/data"),
        ]

        with patch.object(checker, "scan_current_api", return_value=head), \
             patch.object(checker, "scan_base_api", return_value=base):
            report = checker.compare()

        # GET /api/v1/data removed, POST /api/v1/data added, method change detected
        assert report.breaking_count >= 1

    def test_parameter_added_required_breaking(self):
        """Adding a required parameter is breaking."""
        checker = APICompatChecker.__new__(APICompatChecker)
        checker.cwd = "/tmp"
        checker.base_ref = "v1.0.0"

        base = [
            EndpointInfo(method="POST", path="/api/v1/pay", params=[]),
        ]
        head = [
            EndpointInfo(method="POST", path="/api/v1/pay", params=["merchantId"]),
        ]

        with patch.object(checker, "scan_current_api", return_value=head), \
             patch.object(checker, "scan_base_api", return_value=base):
            report = checker.compare()

        assert len(report.parameter_changes) == 1
        assert report.parameter_changes[0]["breaking"] is True
        assert report.parameter_changes[0]["param"] == "merchantId"

    def test_parameter_added_optional_non_breaking(self):
        """Adding an optional parameter is non-breaking."""
        checker = APICompatChecker.__new__(APICompatChecker)
        checker.cwd = "/tmp"
        checker.base_ref = "v1.0.0"

        base = [
            EndpointInfo(method="GET", path="/api/v1/items", params=[]),
        ]
        head = [
            EndpointInfo(method="GET", path="/api/v1/items", params=["status?"]),
        ]

        with patch.object(checker, "scan_current_api", return_value=head), \
             patch.object(checker, "scan_base_api", return_value=base):
            report = checker.compare()

        assert len(report.parameter_changes) == 1
        assert report.parameter_changes[0]["breaking"] is False
        assert report.breaking_count == 0
        assert report.non_breaking_count == 1


# ---------------------------------------------------------------------------
# Git tag detection
# ---------------------------------------------------------------------------


class TestGitTagDetection:
    """Test git tag detection."""

    def test_detects_last_tag(self, tmp_path):
        """_detect_last_tag returns the last git tag."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="v8.0.0\n", stderr=""
            )
            checker = APICompatChecker(cwd=str(tmp_path))
            assert checker.base_ref == "v8.0.0"

    def test_fallback_when_no_tags(self, tmp_path):
        """Falls back to HEAD~10 when no tags exist."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=128, stdout="", stderr="fatal: No names found"
            )
            checker = APICompatChecker(cwd=str(tmp_path))
            assert checker.base_ref == "HEAD~10"

    def test_explicit_base_ref(self, tmp_path):
        """Explicit base_ref skips tag detection."""
        checker = APICompatChecker(cwd=str(tmp_path), base_ref="v5.0.0")
        assert checker.base_ref == "v5.0.0"


# ---------------------------------------------------------------------------
# format_report
# ---------------------------------------------------------------------------


class TestFormatReport:
    """Test report formatting."""

    def test_format_with_breaking_changes(self):
        report = APICompatReport(
            base_ref="v1.0.0",
            head_ref="HEAD",
            base_endpoints=[EndpointInfo("GET", "/a"), EndpointInfo("DELETE", "/b")],
            head_endpoints=[EndpointInfo("GET", "/a"), EndpointInfo("POST", "/c")],
            added_endpoints=[EndpointInfo("POST", "/c")],
            removed_endpoints=[EndpointInfo("DELETE", "/b")],
        )
        checker = APICompatChecker.__new__(APICompatChecker)
        output = checker.format_report(report)
        assert "BREAKING" in output
        assert "v1.0.0" in output
        assert "+ POST /c" in output
        assert "- DELETE /b" in output

    def test_format_no_breaking_changes(self):
        report = APICompatReport(
            base_ref="v2.0.0",
            head_ref="HEAD",
            base_endpoints=[EndpointInfo("GET", "/a")],
            head_endpoints=[EndpointInfo("GET", "/a"), EndpointInfo("GET", "/b")],
            added_endpoints=[EndpointInfo("GET", "/b")],
        )
        checker = APICompatChecker.__new__(APICompatChecker)
        output = checker.format_report(report)
        assert "COMPATIBLE" in output
        assert "BREAKING" not in output

    def test_format_no_changes(self):
        report = APICompatReport(
            base_ref="v3.0.0",
            head_ref="HEAD",
            base_endpoints=[EndpointInfo("GET", "/a")],
            head_endpoints=[EndpointInfo("GET", "/a")],
        )
        checker = APICompatChecker.__new__(APICompatChecker)
        output = checker.format_report(report)
        assert "No API changes detected" in output
        assert "COMPATIBLE" in output

    def test_format_summary_counts(self):
        report = APICompatReport(
            base_ref="v1.0.0",
            head_ref="HEAD",
            base_endpoints=[EndpointInfo("GET", "/a")],
            head_endpoints=[EndpointInfo("GET", "/a"), EndpointInfo("GET", "/b"), EndpointInfo("POST", "/c")],
            added_endpoints=[EndpointInfo("GET", "/b"), EndpointInfo("POST", "/c")],
        )
        checker = APICompatChecker.__new__(APICompatChecker)
        output = checker.format_report(report)
        assert "Total endpoints: 3 (was 1)" in output
        assert "Added: 2" in output
        assert "Removed: 0" in output


# ---------------------------------------------------------------------------
# scan_current_api OSError (lines 180-181)
# ---------------------------------------------------------------------------


class TestScanCurrentApiOSError:
    def test_scan_current_api_unreadable_file(self, tmp_path):
        """OSError reading a router file is silently skipped (lines 180-181)."""
        checker = APICompatChecker(cwd=str(tmp_path), base_ref="main")
        # Create a router file that can't be read
        router_dir = tmp_path / "code_agents" / "routers"
        router_dir.mkdir(parents=True)
        (router_dir / "broken_router.py").write_text("# placeholder")

        with patch.object(checker, "_find_router_files", return_value=["code_agents/routers/broken_router.py"]), \
             patch("builtins.open", side_effect=OSError("permission denied")):
            endpoints = checker.scan_current_api()
        assert endpoints == []


# ---------------------------------------------------------------------------
# scan_base_api (lines 187-201)
# ---------------------------------------------------------------------------


class TestScanBaseApi:
    def test_scan_base_api_with_custom_ref(self, tmp_path):
        """scan_base_api uses provided ref (lines 187-189)."""
        checker = APICompatChecker(cwd=str(tmp_path), base_ref="main")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = """
from fastapi import APIRouter
router = APIRouter()

@router.get("/api/test")
def test_endpoint():
    pass
"""
        with patch.object(checker, "_find_router_files", return_value=["router.py"]), \
             patch("subprocess.run", return_value=mock_result):
            endpoints = checker.scan_base_api("v2.0.0")
        assert len(endpoints) >= 1

    def test_scan_base_api_git_show_fails(self, tmp_path):
        """git show returns non-zero (lines 197-199)."""
        checker = APICompatChecker(cwd=str(tmp_path), base_ref="main")
        mock_result = MagicMock()
        mock_result.returncode = 128  # fatal

        with patch.object(checker, "_find_router_files", return_value=["router.py"]), \
             patch("subprocess.run", return_value=mock_result):
            endpoints = checker.scan_base_api()
        assert endpoints == []

    def test_scan_base_api_timeout(self, tmp_path):
        """git show times out (line 200-201)."""
        import subprocess
        checker = APICompatChecker(cwd=str(tmp_path), base_ref="main")
        with patch.object(checker, "_find_router_files", return_value=["router.py"]), \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 10)):
            endpoints = checker.scan_base_api()
        assert endpoints == []


# ---------------------------------------------------------------------------
# format_report with breaking changes (lines 260, 281, 297, 310)
# ---------------------------------------------------------------------------


class TestFormatReportBreaking:
    def test_format_removed_params(self):
        """Removed parameter shows as breaking (line 260)."""
        report = APICompatReport(
            base_ref="v1", head_ref="HEAD",
            base_endpoints=[EndpointInfo("POST", "/api/users", params=["name", "email"])],
            head_endpoints=[EndpointInfo("POST", "/api/users", params=["name"])],
            parameter_changes=[{
                "endpoint": "POST /api/users",
                "param": "email",
                "change": "removed",
                "breaking": True,
            }],
        )
        checker = APICompatChecker.__new__(APICompatChecker)
        output = checker.format_report(report)
        assert "Breaking" in output
        assert "removed" in output
        assert "email" in output

    def test_format_non_breaking_param(self):
        """Added optional parameter shows as non-breaking (line 297)."""
        report = APICompatReport(
            base_ref="v1", head_ref="HEAD",
            base_endpoints=[EndpointInfo("POST", "/api/users", params=["name"])],
            head_endpoints=[EndpointInfo("POST", "/api/users", params=["name", "email?"])],
            parameter_changes=[{
                "endpoint": "POST /api/users",
                "param": "email",
                "change": "added optional",
                "breaking": False,
            }],
        )
        checker = APICompatChecker.__new__(APICompatChecker)
        output = checker.format_report(report)
        assert "Non-Breaking" in output
        assert "added optional" in output

    def test_format_method_changed(self):
        """Changed HTTP method shows as breaking (line 310)."""
        report = APICompatReport(
            base_ref="v1", head_ref="HEAD",
            base_endpoints=[EndpointInfo("GET", "/api/data")],
            head_endpoints=[EndpointInfo("POST", "/api/data")],
            changed_endpoints=[{
                "path": "/api/data",
                "old_method": "GET",
                "new_method": "POST",
            }],
        )
        checker = APICompatChecker.__new__(APICompatChecker)
        output = checker.format_report(report)
        assert "Breaking" in output
        assert "method changed" in output
