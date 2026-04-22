"""Validate `repository` fields in extension package.json files (VS Code / webview)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

# (path relative to repo root, expected monorepo `repository.directory`)
EXTENSION_PACKAGES: tuple[tuple[str, str], ...] = (
    ("extensions/vscode/package.json", "extensions/vscode"),
    ("extensions/vscode/webview-ui/package.json", "extensions/vscode/webview-ui"),
)

DEFAULT_REPO_HTTPS = "https://github.com/code-agents-org/code-agents.git"


def _git_remote_https(repo_root: Path) -> str | None:
    """Return normalized https URL from `git remote get-url origin`, or None."""
    try:
        raw = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None
    if not raw:
        return None
    return _normalize_git_url_to_https(raw)


def _normalize_git_url_to_https(url: str) -> str:
    u = url.strip()
    if u.startswith("git@"):
        # git@host:org/repo.git -> https://host/org/repo
        rest = u[4:]
        if ":" in rest:
            host, path = rest.split(":", 1)
            path = path.removesuffix(".git")
            return f"https://{host}/{path}.git"
    if u.endswith(".git"):
        return u
    return u + ".git" if "://" in u else u


def _parse_repository(pkg: dict[str, Any]) -> tuple[bool, str]:
    """Return (ok, error_message). Empty error means OK."""
    repo = pkg.get("repository")
    if repo is None:
        return False, "missing top-level `repository` field"
    if isinstance(repo, str):
        s = repo.strip()
        if s.startswith("https://") or s.startswith("git+https://") or s.startswith("git@"):
            return True, ""
        return False, "`repository` string must be a valid git URL"
    if isinstance(repo, dict):
        url = (repo.get("url") or "").strip()
        if not url:
            return False, "`repository.url` is missing or empty"
        return True, ""
    return False, "`repository` must be a string URL or an object with at least `url`"


def _directory_matches(repo: Any, expected_dir: str) -> tuple[bool, str]:
    if not isinstance(repo, dict):
        return True, ""
    got = (repo.get("directory") or "").strip().replace("\\", "/")
    if not got:
        return False, (
            f'`repository.directory` is missing (required for this monorepo). '
            f'Set it to: "{expected_dir}"'
        )
    if got.rstrip("/") != expected_dir.rstrip("/"):
        return False, (
            f'`repository.directory` is "{got}" but should be "{expected_dir}" '
            "for this package inside the code-agents monorepo"
        )
    return True, ""


def validate_extension_repositories(repo_root: Path) -> tuple[bool, list[str]]:
    """
    Validate repository metadata for all extension package.json files.

    Returns (all_ok, error_lines) where each error line includes the file path.
    """
    errors: list[str] = []
    for rel, expected_dir in EXTENSION_PACKAGES:
        path = repo_root / rel
        if not path.is_file():
            errors.append(f"{rel}: file not found")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"{rel}: invalid JSON ({e})")
            continue
        ok, msg = _parse_repository(data)
        if not ok:
            errors.append(f"{rel}: {msg}")
            continue
        repo = data.get("repository")
        ok_d, msg_d = _directory_matches(repo, expected_dir)
        if not ok_d:
            errors.append(f"{rel}: {msg_d}")
    return (len(errors) == 0, errors)


def repository_snippet(directory: str, git_url: str | None = None) -> str:
    """JSON snippet for package.json (pretty-printed)."""
    url = git_url or DEFAULT_REPO_HTTPS
    obj = {"type": "git", "url": url, "directory": directory}
    return json.dumps({"repository": obj}, indent=2)


def apply_default_repositories(repo_root: Path, *, dry_run: bool = False) -> tuple[bool, list[str]]:
    """
    Insert or fix `repository` fields using `git remote get-url origin` when possible.

    Returns (all_ok, messages). On dry_run, does not write files.
    """
    url = _git_remote_https(repo_root) or DEFAULT_REPO_HTTPS
    messages: list[str] = []
    for rel, expected_dir in EXTENSION_PACKAGES:
        path = repo_root / rel
        if not path.is_file():
            messages.append(f"{rel}: skip (file missing)")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            messages.append(f"{rel}: invalid JSON ({e})")
            continue
        data["repository"] = {"type": "git", "url": url, "directory": expected_dir}
        if dry_run:
            messages.append(f"{rel}: would write repository.url={url!r} directory={expected_dir!r}")
            continue
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        messages.append(f"{rel}: updated repository → {url} ({expected_dir})")
    if dry_run:
        return True, messages
    ok, errs = validate_extension_repositories(repo_root)
    if not ok:
        return False, messages + errs
    return True, messages


def validate_or_exit(repo_root: Path) -> None:
    """Print formatted errors and exit with code 1 if validation fails."""
    import sys

    ok, errs = validate_extension_repositories(repo_root)
    if ok:
        return
    print(format_validation_failure(repo_root, errs), file=sys.stderr)
    sys.exit(1)


def format_validation_failure(repo_root: Path, errors: list[str]) -> str:
    """Human-readable instructions when validation fails."""
    suggest_url = _git_remote_https(repo_root) or DEFAULT_REPO_HTTPS
    lines = [
        "",
        "  Extension package.json is missing or has an invalid `repository` field.",
        "  @vscode/vsce requires this for packaging (non-interactive runs abort otherwise).",
        "",
    ]
    for e in errors:
        lines.append(f"  • {e}")
    lines.extend(
        [
            "",
            "  Add a `repository` object to each file listed above. Example for the VS Code extension:",
            "",
            '  "repository": {',
            '    "type": "git",',
            f'    "url": "{suggest_url}",',
            '    "directory": "extensions/vscode"',
            "  }",
            "",
            "  Use `directory` matching the package path inside the monorepo (see EXTENSION_PACKAGES in",
            "  code_agents/tools/extension_repositories.py).",
            "",
            f"  If this checkout uses a different remote, set `url` to that remote (detected: {suggest_url}).",
            "",
        ]
    )
    return "\n".join(lines)
