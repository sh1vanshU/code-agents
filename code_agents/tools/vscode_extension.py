"""Shared VS Code extension build, .vsix packaging, and install into VS Code.

Used by ``code-agents plugin``, ``code-agents init --extensions``, and ``install.sh``
(``poetry run python -m code_agents.tools.vscode_extension``) so commands stay aligned
with ``extensions/vscode/package.json`` scripts (``build:webview``, ``compile``).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def vscode_extension_dir(repo_root: Path) -> Path:
    """``<repo>/extensions/vscode``."""
    return repo_root / "extensions" / "vscode"


def build_vscode_extension(v_ext: Path, *, capture_output: bool = True) -> None:
    """Run ``npm install``, ``npm run build:webview``, ``npm run compile``.

    Matches ``code-agents plugin build vscode`` and the ``compile`` / ``build:webview``
    scripts in ``extensions/vscode/package.json``.
    """
    kw: dict = {"cwd": str(v_ext), "check": True}
    if capture_output:
        kw["capture_output"] = True
    subprocess.run(["npm", "install", "--silent"], **kw)
    subprocess.run(["npm", "run", "build:webview"], **kw)
    subprocess.run(["npm", "run", "compile"], **kw)


def newest_vsix(v_ext: Path) -> Path | None:
    """Return the most recently modified ``*.vsix`` under ``v_ext``, or ``None``."""
    found = sorted(v_ext.glob("*.vsix"), key=lambda p: p.stat().st_mtime)
    return found[-1] if found else None


def run_vsce_package(v_ext: Path, *, capture_output: bool = False) -> int:
    """Run ``npx @vscode/vsce package --no-dependencies``. Returns the process return code."""
    r = subprocess.run(
        ["npx", "--yes", "@vscode/vsce", "package", "--no-dependencies"],
        cwd=str(v_ext),
        capture_output=capture_output,
        timeout=300,
    )
    return r.returncode


def install_vsix_with_code_cli(vsix: Path, *, timeout: int = 30) -> subprocess.CompletedProcess:
    """``code --install-extension <vsix>`` (raises on failure if check=True)."""
    return subprocess.run(
        ["code", "--install-extension", str(vsix)],
        check=True,
        capture_output=True,
        timeout=timeout,
    )


def main(argv: list[str] | None = None) -> int:
    """CLI for ``install.sh``: ``build`` | ``package`` | ``build-package``."""
    p = argparse.ArgumentParser(description="VS Code extension helpers for install scripts.")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="npm install + build:webview + compile")
    b.add_argument(
        "--root",
        type=Path,
        default=None,
        help="code-agents repo root (default: $CODE_AGENTS_DIR or parent of code_agents package)",
    )

    pk = sub.add_parser("package", help="vsce package (no repository validation)")
    pk.add_argument("--root", type=Path, default=None)

    bp = sub.add_parser("build-package", help="build then vsce package if no .vsix exists")
    bp.add_argument("--root", type=Path, default=None)

    args = p.parse_args(argv)
    root = args.root
    if root is None:
        env_root = os.environ.get("CODE_AGENTS_DIR", "").strip()
        root = Path(env_root) if env_root else Path(__file__).resolve().parent.parent.parent
    root = root.resolve()
    v_ext = vscode_extension_dir(root)
    if not (v_ext / "package.json").is_file():
        print(f"  No VS Code extension at {v_ext}", file=sys.stderr)
        return 1

    if args.cmd == "build":
        build_vscode_extension(v_ext)
        return 0
    if args.cmd == "package":
        return run_vsce_package(v_ext)

    # build-package
    build_vscode_extension(v_ext)
    if newest_vsix(v_ext) is None:
        return run_vsce_package(v_ext)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
