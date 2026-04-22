"""CLI translate command — translate code between programming languages."""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_translate")


def cmd_translate():
    """Translate a source file to another programming language.

    Usage:
      code-agents translate <file> --to <lang>
      code-agents translate <file> --to <lang> --output <path>

    Examples:
      code-agents translate src/utils.py --to javascript
      code-agents translate lib/helper.js --to python
      code-agents translate app.py --to go --output app.go
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]  # everything after 'translate'

    if not args or "--help" in args or "-h" in args:
        print(cmd_translate.__doc__)
        return

    source_file = args[0]
    target_lang = ""
    output_path = ""

    i = 1
    while i < len(args):
        if args[i] == "--to" and i + 1 < len(args):
            target_lang = args[i + 1]
            i += 1
        elif args[i] == "--output" and i + 1 < len(args):
            output_path = args[i + 1]
            i += 1
        i += 1

    if not target_lang:
        print(red("  Missing --to <lang>. Specify a target language."))
        print(dim("  Supported: python, javascript, typescript, java, go"))
        return

    repo = os.environ.get("TARGET_REPO_PATH", os.getcwd())

    from code_agents.knowledge.code_translator import CodeTranslator, format_translation

    translator = CodeTranslator(cwd=repo)
    result = translator.translate_file(source_file, target_lang)

    if output_path:
        from pathlib import Path
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(result.code, encoding="utf-8")
        print(green(f"  Written to {out}"))
    else:
        print(format_translation(result))
