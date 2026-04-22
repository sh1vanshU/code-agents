"""CLI settlement command — parse and validate settlement files."""

from __future__ import annotations

import json
import logging
import sys

logger = logging.getLogger("code_agents.cli.cli_settlement")


def cmd_settlement():
    """Parse and validate settlement files, optionally compare against a bank file.

    Usage:
      code-agents settlement --file settlements.csv
      code-agents settlement --file visa_tc33.csv --format visa
      code-agents settlement --file our.csv --compare bank.csv
      code-agents settlement --file our.csv --compare bank.csv --output adjustments.csv
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]
    file_path = None
    compare_file = None
    fmt = "auto"
    output_path = None

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--file" and i + 1 < len(args):
            file_path = args[i + 1]
            i += 1
        elif a == "--format" and i + 1 < len(args):
            fmt = args[i + 1].lower()
            i += 1
        elif a == "--compare" and i + 1 < len(args):
            compare_file = args[i + 1]
            i += 1
        elif a == "--output" and i + 1 < len(args):
            output_path = args[i + 1]
            i += 1
        elif a in ("--help", "-h"):
            print(cmd_settlement.__doc__)
            return
        i += 1

    if not file_path:
        print(red("  Missing required flag: --file"))
        print(dim("  Usage: code-agents settlement --file settlements.csv [--format visa|mastercard|upi|auto] [--compare bank.csv] [--output adjustments.csv]"))
        return

    if fmt not in ("auto", "visa", "mastercard", "upi", "csv"):
        print(red(f"  Unknown format: {fmt}"))
        print(dim("  Supported: auto, visa, mastercard, upi, csv"))
        return

    from code_agents.domain.settlement_parser import (
        SettlementParser, SettlementValidator, format_settlement_report,
    )

    parser = SettlementParser()
    validator = SettlementValidator()

    # Parse primary file
    print(dim(f"  Parsing: {file_path} (format={fmt})"))
    try:
        records = parser.parse(file_path, format=fmt)
    except (FileNotFoundError, ValueError) as exc:
        print(red(f"  Error: {exc}"))
        return

    print(green(f"  Parsed {len(records)} records"))
    print()

    # Validate
    report = validator.validate(records)
    print(format_settlement_report(report))

    # Compare if requested
    if compare_file:
        print()
        print(dim(f"  Comparing against: {compare_file}"))
        try:
            bank_records = parser.parse(compare_file, format=fmt)
        except (FileNotFoundError, ValueError) as exc:
            print(red(f"  Error loading comparison file: {exc}"))
            return

        discrepancies = validator.compare(records, bank_records)
        if discrepancies:
            print(yellow(f"  Found {len(discrepancies)} discrepancies"))
            for d in discrepancies[:20]:
                print(f"    [{d.discrepancy_type.upper():10s}] {d.txn_id}: {d.field}")
            if len(discrepancies) > 20:
                print(dim(f"    ... and {len(discrepancies) - 20} more"))

            # Generate adjustments
            if output_path:
                adj_csv = validator.generate_adjustments(discrepancies)
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(adj_csv)
                print(green(f"  Adjustments written to: {output_path}"))
        else:
            print(green("  No discrepancies — files match!"))
