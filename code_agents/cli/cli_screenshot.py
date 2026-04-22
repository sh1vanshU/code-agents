"""CLI screenshot-to-code command — generate UI code from screenshots/mockups."""

from __future__ import annotations

import logging

logger = logging.getLogger("code_agents.cli.cli_screenshot")


def cmd_screenshot():
    """Generate UI code from a screenshot or description.

    Usage:
      code-agents screenshot --image mockup.png
      code-agents screenshot --image login.png --framework react
      code-agents screenshot --description "login form with email and password"
      code-agents screenshot --description "data table" --framework vue --output table.vue
    """
    import sys
    from pathlib import Path

    args = sys.argv[2:]
    image_path = ""
    framework = ""
    description = ""
    output_path = ""

    i = 0
    while i < len(args):
        if args[i] in ("--image", "-i") and i + 1 < len(args):
            image_path = args[i + 1]
            i += 2
        elif args[i] in ("--framework", "-f") and i + 1 < len(args):
            framework = args[i + 1]
            i += 2
        elif args[i] in ("--description", "-d") and i + 1 < len(args):
            description = args[i + 1]
            i += 2
        elif args[i] in ("--output", "-o") and i + 1 < len(args):
            output_path = args[i + 1]
            i += 2
        elif args[i] in ("--help", "-h"):
            print(cmd_screenshot.__doc__)
            return
        else:
            # Treat remaining as description
            description = " ".join(args[i:])
            break

    if not image_path and not description:
        print("Error: provide --image <path> or --description <text>")
        print("Run: code-agents screenshot --help")
        return

    import os
    from code_agents.ui.screenshot_to_code import ScreenshotToCode, format_generated_ui

    cwd = os.environ.get("TARGET_REPO_PATH", os.getcwd())
    generator = ScreenshotToCode(cwd=cwd)
    result = generator.generate(
        image_path=image_path,
        framework=framework,
        description=description,
    )

    if output_path:
        Path(output_path).write_text(result.code)
        print(f"Written to {output_path} ({len(result.code)} bytes)")
    else:
        print(format_generated_ui(result))
