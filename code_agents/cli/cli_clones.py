"""CLI clones command — detect code clones in the target repo."""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_clones")


def cmd_clones():
    """Detect code clones (duplicated code blocks) in the codebase.

    Usage:
      code-agents clones                          # scan with defaults
      code-agents clones --threshold 0.8          # set similarity threshold
      code-agents clones --min-tokens 50          # minimum token count
      code-agents clones --json                   # output as JSON
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]
    threshold = 0.8
    min_tokens = 50
    as_json = False

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--threshold" and i + 1 < len(args):
            threshold = float(args[i + 1])
            i += 2
        elif a == "--min-tokens" and i + 1 < len(args):
            min_tokens = int(args[i + 1])
            i += 2
        elif a == "--json":
            as_json = True
            i += 1
        elif a in ("--help", "-h"):
            print(cmd_clones.__doc__)
            return
        else:
            i += 1

    from code_agents.reviews.clone_detector import CloneDetector, format_clone_report

    repo_path = os.environ.get("TARGET_REPO_PATH", os.getcwd())
    print(dim(f"  Scanning {repo_path} for code clones..."))

    detector = CloneDetector(cwd=repo_path)
    groups = detector.detect(threshold=threshold, min_tokens=min_tokens)

    if as_json:
        import json
        data = [
            {
                "similarity": g.similarity,
                "token_count": g.token_count,
                "blocks": [
                    {
                        "file": b["file"],
                        "start_line": b["start_line"],
                        "end_line": b["end_line"],
                    }
                    for b in g.blocks
                ],
            }
            for g in groups
        ]
        print(json.dumps(data, indent=2))
    else:
        print(format_clone_report(groups))
