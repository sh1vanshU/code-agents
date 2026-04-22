"""Payment Reconciliation Debugger — compare orders vs settlements, detect mismatches."""

from __future__ import annotations

import csv
import io
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.observability.recon_debug")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ReconRecord:
    """A single reconciliation record (order or settlement)."""

    txn_id: str
    amount: float
    currency: str
    status: str
    date: str
    source: str  # "order" | "settlement"


@dataclass
class ReconMismatch:
    """A mismatch between an order and its corresponding settlement."""

    txn_id: str
    field: str
    our_value: str
    bank_value: str
    mismatch_type: str  # "amount", "status", "missing_in_bank", "missing_in_db", "currency"


@dataclass
class ReconReport:
    """Full reconciliation report."""

    date: str
    total_orders: int
    total_settlements: int
    matched: int
    mismatched: int
    missing_in_bank: int
    missing_in_db: int
    mismatches: list[ReconMismatch]
    amount_variance: float
    common_issues: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Column name normalisation
# ---------------------------------------------------------------------------

_TXN_ID_ALIASES = {"txn_id", "transaction_id", "order_id", "id", "ref", "reference", "txnid"}
_AMOUNT_ALIASES = {"amount", "total", "value", "sum", "amt"}
_STATUS_ALIASES = {"status", "state", "txn_status", "payment_status"}
_CURRENCY_ALIASES = {"currency", "ccy", "curr", "currency_code"}
_DATE_ALIASES = {"date", "created_at", "timestamp", "txn_date", "created", "time"}


def _resolve_column(headers: list[str], aliases: set[str]) -> Optional[str]:
    """Find the first header that matches one of the known aliases (case-insensitive)."""
    lower_map = {h.lower().strip(): h for h in headers}
    for alias in aliases:
        if alias in lower_map:
            return lower_map[alias]
    return None


# ---------------------------------------------------------------------------
# ReconDebugger
# ---------------------------------------------------------------------------

class ReconDebugger:
    """Reconcile payment orders against bank settlements."""

    def __init__(self, cwd: str = ""):
        self.cwd = cwd or os.getcwd()
        logger.debug("ReconDebugger initialised (cwd=%s)", self.cwd)

    # ----- public API -----

    def reconcile(
        self, orders: list[ReconRecord], settlements: list[ReconRecord]
    ) -> ReconReport:
        """Reconcile two lists of records and return a report."""
        logger.info(
            "Reconciling %d orders against %d settlements",
            len(orders),
            len(settlements),
        )
        return self._match_records(orders, settlements)

    def reconcile_from_files(
        self, orders_file: str, settlement_file: str
    ) -> ReconReport:
        """Parse CSV/TSV files and reconcile."""
        orders_path = self._resolve_path(orders_file)
        settlements_path = self._resolve_path(settlement_file)
        logger.info(
            "Loading files: orders=%s  settlements=%s", orders_path, settlements_path
        )

        orders = self._parse_csv(orders_path, "order")
        settlements = self._parse_csv(settlements_path, "settlement")
        return self.reconcile(orders, settlements)

    # ----- CSV parsing -----

    def _resolve_path(self, path: str) -> str:
        if os.path.isabs(path):
            return path
        return os.path.join(self.cwd, path)

    def _parse_csv(self, path: str, source: str) -> list[ReconRecord]:
        """Auto-detect delimiter and column names, return list of ReconRecord."""
        logger.debug("Parsing %s as source=%s", path, source)
        text = Path(path).read_text(encoding="utf-8")

        # Auto-detect delimiter
        dialect: Optional[csv.Dialect] = None
        try:
            dialect = csv.Sniffer().sniff(text[:4096])
        except csv.Error:
            pass

        delimiter = dialect.delimiter if dialect else ","
        if "\t" in text.split("\n")[0] and delimiter != "\t":
            delimiter = "\t"

        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        if reader.fieldnames is None:
            raise ValueError(f"Could not read headers from {path}")

        headers = list(reader.fieldnames)
        col_txn = _resolve_column(headers, _TXN_ID_ALIASES)
        col_amt = _resolve_column(headers, _AMOUNT_ALIASES)
        col_status = _resolve_column(headers, _STATUS_ALIASES)
        col_ccy = _resolve_column(headers, _CURRENCY_ALIASES)
        col_date = _resolve_column(headers, _DATE_ALIASES)

        if not col_txn:
            raise ValueError(
                f"No transaction ID column found in {path}. "
                f"Headers: {headers}. Expected one of: {_TXN_ID_ALIASES}"
            )
        if not col_amt:
            raise ValueError(
                f"No amount column found in {path}. "
                f"Headers: {headers}. Expected one of: {_AMOUNT_ALIASES}"
            )

        records: list[ReconRecord] = []
        for row in reader:
            txn_id = (row.get(col_txn) or "").strip()
            if not txn_id:
                continue

            try:
                amount = float((row.get(col_amt) or "0").strip().replace(",", ""))
            except ValueError:
                amount = 0.0

            status = (row.get(col_status) or "unknown").strip().lower()
            currency = (row.get(col_ccy) or "INR").strip().upper()
            date = (row.get(col_date) or "").strip()

            records.append(
                ReconRecord(
                    txn_id=txn_id,
                    amount=amount,
                    currency=currency,
                    status=status,
                    date=date,
                    source=source,
                )
            )

        logger.info("Parsed %d records from %s", len(records), path)
        return records

    # ----- Matching engine -----

    def _match_records(
        self, orders: list[ReconRecord], settlements: list[ReconRecord]
    ) -> ReconReport:
        """Build lookup by txn_id, compare fields, produce report."""
        order_map: dict[str, ReconRecord] = {r.txn_id: r for r in orders}
        settle_map: dict[str, ReconRecord] = {r.txn_id: r for r in settlements}

        all_txn_ids = set(order_map.keys()) | set(settle_map.keys())

        mismatches: list[ReconMismatch] = []
        matched = 0
        missing_in_bank = 0
        missing_in_db = 0
        amount_variance = 0.0

        for txn_id in sorted(all_txn_ids):
            order = order_map.get(txn_id)
            settle = settle_map.get(txn_id)

            if order and not settle:
                missing_in_bank += 1
                mismatches.append(
                    ReconMismatch(
                        txn_id=txn_id,
                        field="presence",
                        our_value="exists",
                        bank_value="missing",
                        mismatch_type="missing_in_bank",
                    )
                )
                amount_variance += order.amount
                continue

            if settle and not order:
                missing_in_db += 1
                mismatches.append(
                    ReconMismatch(
                        txn_id=txn_id,
                        field="presence",
                        our_value="missing",
                        bank_value="exists",
                        mismatch_type="missing_in_db",
                    )
                )
                amount_variance += settle.amount
                continue

            # Both exist — compare fields
            assert order is not None and settle is not None
            txn_ok = True

            # Amount check
            if abs(order.amount - settle.amount) > 0.005:
                diff = order.amount - settle.amount
                mismatches.append(
                    ReconMismatch(
                        txn_id=txn_id,
                        field="amount",
                        our_value=f"{order.amount:.2f}",
                        bank_value=f"{settle.amount:.2f}",
                        mismatch_type="amount",
                    )
                )
                amount_variance += abs(diff)
                txn_ok = False

            # Status check
            if order.status != settle.status:
                mismatches.append(
                    ReconMismatch(
                        txn_id=txn_id,
                        field="status",
                        our_value=order.status,
                        bank_value=settle.status,
                        mismatch_type="status",
                    )
                )
                txn_ok = False

            # Currency check
            if order.currency != settle.currency:
                mismatches.append(
                    ReconMismatch(
                        txn_id=txn_id,
                        field="currency",
                        our_value=order.currency,
                        bank_value=settle.currency,
                        mismatch_type="currency",
                    )
                )
                txn_ok = False

            if txn_ok:
                matched += 1

        mismatched_count = len(
            {m.txn_id for m in mismatches if m.mismatch_type not in ("missing_in_bank", "missing_in_db")}
        )

        today = datetime.now().strftime("%Y-%m-%d")

        report = ReconReport(
            date=today,
            total_orders=len(orders),
            total_settlements=len(settlements),
            matched=matched,
            mismatched=mismatched_count,
            missing_in_bank=missing_in_bank,
            missing_in_db=missing_in_db,
            mismatches=mismatches,
            amount_variance=round(amount_variance, 2),
        )
        report.common_issues = self._detect_common_issues(mismatches)

        logger.info(
            "Reconciliation complete: matched=%d mismatched=%d missing_bank=%d missing_db=%d variance=%.2f",
            matched,
            mismatched_count,
            missing_in_bank,
            missing_in_db,
            amount_variance,
        )
        return report

    # ----- Pattern detection -----

    def _detect_common_issues(self, mismatches: list[ReconMismatch]) -> list[str]:
        """Detect common reconciliation issue patterns."""
        issues: list[str] = []

        if not mismatches:
            return issues

        # Count by type
        type_counts: dict[str, int] = {}
        for m in mismatches:
            type_counts[m.mismatch_type] = type_counts.get(m.mismatch_type, 0) + 1

        # Pattern: timeout retries (same txn appears multiple times in bank)
        missing_bank = [m for m in mismatches if m.mismatch_type == "missing_in_bank"]
        if len(missing_bank) > 3:
            issues.append(
                f"Possible timeout retries: {len(missing_bank)} orders missing in bank settlements. "
                "Check for gateway timeout + retry logic creating orphan orders."
            )

        # Pattern: duplicate callbacks (missing in DB means bank has records we don't)
        missing_db = [m for m in mismatches if m.mismatch_type == "missing_in_db"]
        if len(missing_db) > 0:
            issues.append(
                f"Duplicate callbacks or unprocessed webhooks: {len(missing_db)} settlement records "
                "have no matching order. Check callback idempotency handling."
            )

        # Pattern: rounding errors (amount mismatches within 1.0)
        amount_mismatches = [m for m in mismatches if m.mismatch_type == "amount"]
        rounding_errors = 0
        for m in amount_mismatches:
            try:
                diff = abs(float(m.our_value) - float(m.bank_value))
                if diff < 1.0:
                    rounding_errors += 1
            except ValueError:
                pass
        if rounding_errors > 0:
            issues.append(
                f"Rounding errors detected: {rounding_errors} transactions have sub-rupee amount "
                "differences. Check float precision in amount calculations — use Decimal."
            )

        # Pattern: large amount differences (possible partial settlements)
        large_diffs = 0
        for m in amount_mismatches:
            try:
                diff = abs(float(m.our_value) - float(m.bank_value))
                if diff > 100.0:
                    large_diffs += 1
            except ValueError:
                pass
        if large_diffs > 0:
            issues.append(
                f"Large amount discrepancies: {large_diffs} transactions differ by >100. "
                "Check for partial settlements, refund offsets, or fee deductions."
            )

        # Pattern: currency mismatch
        ccy_mismatches = type_counts.get("currency", 0)
        if ccy_mismatches > 0:
            issues.append(
                f"Currency mismatch: {ccy_mismatches} transactions have different currencies. "
                "Check multi-currency handling and FX conversion."
            )

        # Pattern: status mismatch (e.g. success vs pending)
        status_mismatches = [m for m in mismatches if m.mismatch_type == "status"]
        if status_mismatches:
            status_pairs: dict[str, int] = {}
            for m in status_mismatches:
                pair = f"{m.our_value} -> {m.bank_value}"
                status_pairs[pair] = status_pairs.get(pair, 0) + 1
            top_pairs = sorted(status_pairs.items(), key=lambda x: -x[1])[:3]
            pair_strs = [f"{pair} ({count}x)" for pair, count in top_pairs]
            issues.append(
                f"Status mismatches: {', '.join(pair_strs)}. "
                "Check callback processing delays and state machine transitions."
            )

        return issues


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def format_recon_report(report: ReconReport) -> str:
    """Format a ReconReport as a Rich-style terminal table."""
    lines: list[str] = []
    w = 56  # inner width

    lines.append(f"\u256d\u2500 Reconciliation Report ({report.date}) " + "\u2500" * max(0, w - 28 - len(report.date)) + "\u256e")
    lines.append(f"\u2502 Orders: {report.total_orders:,}  Settlements: {report.total_settlements:,}".ljust(w + 1) + "\u2502")
    lines.append(
        f"\u2502 Matched: {report.matched:,}  Mismatched: {report.mismatched:,}".ljust(w + 1) + "\u2502"
    )
    lines.append(
        f"\u2502 Missing in bank: {report.missing_in_bank:,}  Missing in DB: {report.missing_in_db:,}".ljust(w + 1) + "\u2502"
    )
    lines.append(f"\u2502 Amount variance: \u20b9{report.amount_variance:,.2f}".ljust(w + 1) + "\u2502")

    if report.mismatches:
        lines.append("\u251c" + "\u2500" * (w + 1) + "\u2524")
        lines.append("\u2502 Mismatches:".ljust(w + 1) + "\u2502")

        shown = 0
        for m in report.mismatches:
            if shown >= 20:
                remaining = len(report.mismatches) - shown
                lines.append(f"\u2502   ... and {remaining} more".ljust(w + 1) + "\u2502")
                break

            if m.mismatch_type == "missing_in_bank":
                desc = f"  {m.txn_id} \u2014 missing in bank settlements"
            elif m.mismatch_type == "missing_in_db":
                desc = f"  {m.txn_id} \u2014 missing in orders DB"
            elif m.mismatch_type == "amount":
                try:
                    diff = abs(float(m.our_value) - float(m.bank_value))
                    desc = f"  {m.txn_id} \u2014 amount: \u20b9{m.our_value} vs \u20b9{m.bank_value} (\u20b9{diff:.2f} diff)"
                except ValueError:
                    desc = f"  {m.txn_id} \u2014 amount: {m.our_value} vs {m.bank_value}"
            elif m.mismatch_type == "status":
                desc = f"  {m.txn_id} \u2014 status: {m.our_value} vs {m.bank_value}"
            elif m.mismatch_type == "currency":
                desc = f"  {m.txn_id} \u2014 currency: {m.our_value} vs {m.bank_value}"
            else:
                desc = f"  {m.txn_id} \u2014 {m.field}: {m.our_value} vs {m.bank_value}"

            lines.append(f"\u2502 {desc}".ljust(w + 1) + "\u2502")
            shown += 1

    if report.common_issues:
        lines.append("\u251c" + "\u2500" * (w + 1) + "\u2524")
        lines.append("\u2502 Common Issues Detected:".ljust(w + 1) + "\u2502")
        for issue in report.common_issues:
            # Wrap long lines
            words = issue.split()
            line = "  "
            for word in words:
                if len(line) + len(word) + 1 > w - 2:
                    lines.append(f"\u2502 {line}".ljust(w + 1) + "\u2502")
                    line = "    " + word
                else:
                    line = line + " " + word if line.strip() else "  " + word
            if line.strip():
                lines.append(f"\u2502 {line}".ljust(w + 1) + "\u2502")

    lines.append("\u2570" + "\u2500" * (w + 1) + "\u256f")
    return "\n".join(lines)


def format_recon_json(report: ReconReport) -> dict:
    """Convert a ReconReport to a JSON-serialisable dict."""
    return {
        "date": report.date,
        "total_orders": report.total_orders,
        "total_settlements": report.total_settlements,
        "matched": report.matched,
        "mismatched": report.mismatched,
        "missing_in_bank": report.missing_in_bank,
        "missing_in_db": report.missing_in_db,
        "amount_variance": report.amount_variance,
        "mismatches": [
            {
                "txn_id": m.txn_id,
                "field": m.field,
                "our_value": m.our_value,
                "bank_value": m.bank_value,
                "mismatch_type": m.mismatch_type,
            }
            for m in report.mismatches
        ],
        "common_issues": report.common_issues,
    }
