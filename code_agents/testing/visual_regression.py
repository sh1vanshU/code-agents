"""Visual Regression Testing — capture and compare page screenshots.

Captures webpage screenshots as HTML snapshots and performs byte-level diff
comparisons to detect visual regressions. Baselines are stored in
``.code-agents/visual-baselines/``.

Usage::

    from code_agents.testing.visual_regression import VisualRegressionTester

    tester = VisualRegressionTester("/path/to/repo")
    path = tester.capture("http://localhost:3000", name="homepage")
    diff = tester.compare("http://localhost:3000", name="homepage")
    print(diff.diff_percentage, diff.passed)
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen, Request

logger = logging.getLogger("code_agents.testing.visual_regression")

# Default threshold: <1% difference passes
DEFAULT_THRESHOLD = 1.0


# ---------------------------------------------------------------------------
# VisualDiff result
# ---------------------------------------------------------------------------

@dataclass
class VisualDiff:
    """Result of comparing a page against its baseline."""

    name: str
    baseline_path: str
    current_path: str
    diff_percentage: float
    passed: bool

    def summary(self) -> str:
        """Human-readable summary."""
        status = "PASS" if self.passed else "FAIL"
        return (
            f"[{status}] {self.name}: {self.diff_percentage:.2f}% different\n"
            f"  Baseline: {self.baseline_path}\n"
            f"  Current:  {self.current_path}"
        )


# ---------------------------------------------------------------------------
# VisualRegressionTester
# ---------------------------------------------------------------------------

class VisualRegressionTester:
    """Capture and compare page snapshots for visual regression testing."""

    def __init__(self, cwd: str, threshold: float = DEFAULT_THRESHOLD) -> None:
        self.cwd = cwd
        self.threshold = threshold
        self.baselines_dir = os.path.join(cwd, ".code-agents", "visual-baselines")
        os.makedirs(self.baselines_dir, exist_ok=True)
        logger.debug("VisualRegressionTester initialized: baselines=%s", self.baselines_dir)

    def capture(self, url: str, name: str = "") -> str:
        """Capture a baseline snapshot of a URL.

        Args:
            url: The URL to capture.
            name: Optional name for the snapshot. Auto-generated from URL if empty.

        Returns:
            Path to the saved baseline file.
        """
        if not name:
            name = self._url_to_name(url)

        logger.info("Capturing baseline for '%s' from %s", name, url)
        html = self._fetch_page(url)
        normalized = self._normalize_html(html)

        baseline_path = os.path.join(self.baselines_dir, f"{name}.baseline.html")
        Path(baseline_path).write_text(normalized, encoding="utf-8")

        # Also store metadata
        meta_path = os.path.join(self.baselines_dir, f"{name}.meta")
        meta = f"url={url}\ncaptured_at={time.strftime('%Y-%m-%dT%H:%M:%S')}\nsize={len(normalized)}\n"
        Path(meta_path).write_text(meta, encoding="utf-8")

        logger.info("Baseline saved: %s (%d bytes)", baseline_path, len(normalized))
        return baseline_path

    def compare(self, url: str, name: str = "") -> VisualDiff:
        """Compare current page against baseline.

        Args:
            url: The URL to capture and compare.
            name: Name matching the baseline. Auto-generated from URL if empty.

        Returns:
            VisualDiff with comparison results.
        """
        if not name:
            name = self._url_to_name(url)

        baseline_path = os.path.join(self.baselines_dir, f"{name}.baseline.html")
        if not os.path.isfile(baseline_path):
            logger.warning("No baseline found for '%s'. Run capture first.", name)
            return VisualDiff(
                name=name,
                baseline_path=baseline_path,
                current_path="",
                diff_percentage=100.0,
                passed=False,
            )

        logger.info("Comparing '%s' against baseline", name)
        html = self._fetch_page(url)
        normalized = self._normalize_html(html)

        current_path = os.path.join(self.baselines_dir, f"{name}.current.html")
        Path(current_path).write_text(normalized, encoding="utf-8")

        baseline_content = Path(baseline_path).read_text(encoding="utf-8")
        diff_pct = self._pixel_diff(baseline_path, current_path)

        passed = diff_pct <= self.threshold
        result = VisualDiff(
            name=name,
            baseline_path=baseline_path,
            current_path=current_path,
            diff_percentage=diff_pct,
            passed=passed,
        )

        logger.info("Comparison result: %s (%.2f%% diff, threshold=%.1f%%)",
                     "PASS" if passed else "FAIL", diff_pct, self.threshold)
        return result

    def list_baselines(self) -> list[dict[str, str]]:
        """List all stored baselines with metadata."""
        baselines: list[dict[str, str]] = []
        if not os.path.isdir(self.baselines_dir):
            return baselines

        for f in sorted(os.listdir(self.baselines_dir)):
            if f.endswith(".baseline.html"):
                name = f.replace(".baseline.html", "")
                path = os.path.join(self.baselines_dir, f)
                meta_path = os.path.join(self.baselines_dir, f"{name}.meta")
                meta: dict[str, str] = {"name": name, "path": path}
                if os.path.isfile(meta_path):
                    for line in Path(meta_path).read_text().splitlines():
                        if "=" in line:
                            k, v = line.split("=", 1)
                            meta[k.strip()] = v.strip()
                baselines.append(meta)
        return baselines

    def update_baseline(self, url: str, name: str = "") -> str:
        """Update a baseline (re-capture)."""
        return self.capture(url, name)

    def delete_baseline(self, name: str) -> bool:
        """Delete a baseline by name."""
        deleted = False
        for suffix in (".baseline.html", ".current.html", ".meta"):
            p = os.path.join(self.baselines_dir, f"{name}{suffix}")
            if os.path.isfile(p):
                os.remove(p)
                deleted = True
        if deleted:
            logger.info("Deleted baseline: %s", name)
        return deleted

    def _pixel_diff(self, img_a_path: str, img_b_path: str) -> float:
        """Simple byte-level comparison between two files.

        Returns percentage of bytes that differ (0.0 = identical, 100.0 = completely different).
        """
        try:
            content_a = Path(img_a_path).read_bytes()
            content_b = Path(img_b_path).read_bytes()
        except OSError as e:
            logger.error("Failed to read files for diff: %s", e)
            return 100.0

        if content_a == content_b:
            return 0.0

        # Compare byte by byte up to the longer length
        max_len = max(len(content_a), len(content_b))
        if max_len == 0:
            return 0.0

        # Pad shorter to match
        a_padded = content_a.ljust(max_len, b"\x00")
        b_padded = content_b.ljust(max_len, b"\x00")

        diff_count = sum(1 for x, y in zip(a_padded, b_padded) if x != y)
        return (diff_count / max_len) * 100.0

    def _fetch_page(self, url: str) -> str:
        """Fetch page HTML via urllib."""
        try:
            req = Request(url, headers={"User-Agent": "code-agents-visual-regression/1.0"})
            with urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (URLError, OSError) as e:
            logger.error("Failed to fetch %s: %s", url, e)
            return f"<!-- fetch failed: {e} -->"

    def _normalize_html(self, html: str) -> str:
        """Normalize HTML for stable comparison.

        Strips volatile content: timestamps, nonces, session IDs, etc.
        """
        # Remove <script> tags (may contain hashes/nonces)
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        # Remove inline styles that might be dynamic
        html = re.sub(r'style="[^"]*"', 'style=""', html)
        # Normalize whitespace
        html = re.sub(r"\s+", " ", html)
        # Remove CSRF tokens
        html = re.sub(r'name="csrf[^"]*"\s+value="[^"]*"', 'name="csrf" value="REDACTED"', html)
        # Remove timestamps (ISO format)
        html = re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", "TIMESTAMP", html)
        return html.strip()

    def _url_to_name(self, url: str) -> str:
        """Convert URL to a safe baseline name."""
        # Remove protocol
        name = re.sub(r"^https?://", "", url)
        # Replace non-alphanumeric with dashes
        name = re.sub(r"[^a-zA-Z0-9]+", "-", name)
        name = name.strip("-")
        return name[:80] or "default"
