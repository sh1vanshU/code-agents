"""Settlement file parser & validator for payment reconciliation.

Parses Visa TC33, Mastercard IPM, UPI NPCI, and generic CSV settlement files.
Validates records, detects discrepancies, and generates adjustment entries.

No card data stored — only txn_ids, amounts, and metadata.
"""

from __future__ import annotations

import csv
import io
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.domain.settlement_parser")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SettlementRecord:
    """A single settlement transaction record."""
    txn_id: str
    amount: float
    currency: str
    status: str
    settlement_date: str
    acquirer_ref: str = ""
    merchant_id: str = ""


@dataclass
class Discrepancy:
    """A single discrepancy found during validation or comparison."""
    txn_id: str
    field: str
    expected: str
    actual: str
    discrepancy_type: str  # "amount", "status", "missing", "currency", "duplicate"


@dataclass
class SettlementReport:
    """Aggregated settlement validation report."""
    total_records: int
    valid_records: int
    invalid_records: int
    discrepancies: list[Discrepancy]
    total_amount: float
    currency_breakdown: dict[str, float]


# ---------------------------------------------------------------------------
# Column header aliases — maps normalized names to possible CSV headers
# ---------------------------------------------------------------------------

_HEADER_ALIASES: dict[str, list[str]] = {
    "txn_id": [
        "txn_id", "transaction_id", "txnid", "trans_id", "id",
        "reference", "ref", "rrn", "utr",
    ],
    "amount": [
        "amount", "txn_amount", "transaction_amount", "settled_amount",
        "settlement_amount", "net_amount",
    ],
    "currency": [
        "currency", "currency_code", "ccy", "cur",
    ],
    "status": [
        "status", "txn_status", "transaction_status", "state",
    ],
    "settlement_date": [
        "settlement_date", "settle_date", "date", "txn_date",
        "transaction_date", "value_date",
    ],
    "acquirer_ref": [
        "acquirer_ref", "acquirer_reference", "acq_ref", "auth_code",
        "approval_code",
    ],
    "merchant_id": [
        "merchant_id", "mid", "merchant", "merchant_code",
    ],
}


def _normalize_header(h: str) -> str:
    """Lowercase, strip, replace spaces/hyphens with underscores."""
    return h.strip().lower().replace(" ", "_").replace("-", "_")


def _map_headers(raw_headers: list[str]) -> dict[str, Optional[str]]:
    """Map raw CSV headers to SettlementRecord field names.

    Returns a dict of {field_name: raw_header_name} for fields that were matched.
    """
    normalized = {_normalize_header(h): h for h in raw_headers}
    mapping: dict[str, Optional[str]] = {}
    for field_name, aliases in _HEADER_ALIASES.items():
        matched = None
        for alias in aliases:
            if alias in normalized:
                matched = normalized[alias]
                break
        mapping[field_name] = matched
    return mapping


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class SettlementParser:
    """Parses settlement files from various acquirer formats."""

    def __init__(self) -> None:
        logger.debug("SettlementParser initialized")

    def parse(self, file_path: str, format: str = "auto") -> list[SettlementRecord]:
        """Parse a settlement file and return records.

        Args:
            file_path: Path to the settlement file (CSV/TSV).
            format: One of "visa", "mastercard", "upi", "auto", or "csv".
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Settlement file not found: {file_path}")

        if format == "auto":
            format = self._detect_format(file_path)
            logger.info("Auto-detected format: %s for %s", format, file_path)

        parser_map = {
            "visa": self._parse_visa,
            "mastercard": self._parse_mastercard,
            "upi": self._parse_upi,
            "csv": self._parse_generic_csv,
        }
        parser_fn = parser_map.get(format, self._parse_generic_csv)
        records = parser_fn(file_path)
        logger.info("Parsed %d records from %s (format=%s)", len(records), file_path, format)
        return records

    # -- format detection -----------------------------------------------------

    def _detect_format(self, path: str) -> str:
        """Auto-detect settlement format from file headers and filename."""
        filename = os.path.basename(path).lower()

        # Filename heuristics
        if "visa" in filename or "tc33" in filename:
            return "visa"
        if "mastercard" in filename or "ipm" in filename or "mc_" in filename:
            return "mastercard"
        if "upi" in filename or "npci" in filename:
            return "upi"

        # Header heuristics
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                first_line = f.readline().strip().lower()
        except OSError:
            return "csv"

        if "tc33" in first_line or "visa" in first_line:
            return "visa"
        if "ipm" in first_line or "mastercard" in first_line:
            return "mastercard"
        if "upi" in first_line or "npci" in first_line or "utr" in first_line:
            return "upi"

        return "csv"

    # -- Visa TC33 ------------------------------------------------------------

    def _parse_visa(self, path: str) -> list[SettlementRecord]:
        """Parse Visa TC33 style settlement file (CSV with Visa-specific columns)."""
        return self._parse_with_defaults(path, default_currency="USD", format_label="visa")

    # -- Mastercard IPM -------------------------------------------------------

    def _parse_mastercard(self, path: str) -> list[SettlementRecord]:
        """Parse Mastercard IPM style settlement file."""
        return self._parse_with_defaults(path, default_currency="USD", format_label="mastercard")

    # -- UPI / NPCI -----------------------------------------------------------

    def _parse_upi(self, path: str) -> list[SettlementRecord]:
        """Parse NPCI UPI settlement file."""
        return self._parse_with_defaults(path, default_currency="INR", format_label="upi")

    # -- Generic CSV ----------------------------------------------------------

    def _parse_generic_csv(self, path: str) -> list[SettlementRecord]:
        """Parse a generic CSV/TSV by auto-mapping headers."""
        return self._parse_with_defaults(path, default_currency="INR", format_label="csv")

    # -- shared parsing logic -------------------------------------------------

    def _parse_with_defaults(
        self,
        path: str,
        default_currency: str = "INR",
        format_label: str = "csv",
    ) -> list[SettlementRecord]:
        """Shared CSV/TSV parsing with header auto-mapping."""
        content = Path(path).read_text(encoding="utf-8", errors="replace")
        dialect = self._sniff_dialect(content)
        reader = csv.DictReader(io.StringIO(content), dialect=dialect)

        if not reader.fieldnames:
            logger.warning("No headers found in %s", path)
            return []

        mapping = _map_headers(list(reader.fieldnames))
        txn_col = mapping.get("txn_id")
        amt_col = mapping.get("amount")
        cur_col = mapping.get("currency")
        status_col = mapping.get("status")
        date_col = mapping.get("settlement_date")
        acq_col = mapping.get("acquirer_ref")
        mid_col = mapping.get("merchant_id")

        if not txn_col:
            raise ValueError(
                f"Cannot find transaction ID column in {path}. "
                f"Headers: {reader.fieldnames}"
            )

        records: list[SettlementRecord] = []
        for row_num, row in enumerate(reader, start=2):
            txn_id = (row.get(txn_col) or "").strip()
            if not txn_id:
                logger.debug("Skipping row %d: empty txn_id", row_num)
                continue

            amount = self._parse_amount(row.get(amt_col, "0"))
            currency = (row.get(cur_col) or default_currency).strip().upper()
            status = (row.get(status_col) or "unknown").strip().lower()
            settlement_date = (row.get(date_col) or "").strip()
            acquirer_ref = (row.get(acq_col) or "").strip()
            merchant_id = (row.get(mid_col) or "").strip()

            records.append(SettlementRecord(
                txn_id=txn_id,
                amount=amount,
                currency=currency,
                status=status,
                settlement_date=settlement_date,
                acquirer_ref=acquirer_ref,
                merchant_id=merchant_id,
            ))

        return records

    @staticmethod
    def _parse_amount(raw: str) -> float:
        """Safely parse amount string to float."""
        raw = (raw or "").strip().replace(",", "")
        if not raw:
            return 0.0
        try:
            return round(float(raw), 2)
        except ValueError:
            return 0.0

    @staticmethod
    def _sniff_dialect(content: str) -> csv.Dialect:
        """Detect CSV dialect (comma vs tab vs pipe)."""
        try:
            sample = content[:4096]
            return csv.Sniffer().sniff(sample, delimiters=",\t|;")
        except csv.Error:
            return csv.excel


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class SettlementValidator:
    """Validates settlement records and compares against bank files."""

    VALID_STATUSES = {"settled", "pending", "rejected", "reversed", "failed", "success", "unknown"}

    def __init__(self) -> None:
        logger.debug("SettlementValidator initialized")

    def validate(self, records: list[SettlementRecord]) -> SettlementReport:
        """Validate a set of settlement records.

        Checks: duplicate txn_ids, invalid amounts, missing required fields,
        currency consistency, and invalid statuses.
        """
        discrepancies: list[Discrepancy] = []
        valid_count = 0
        invalid_count = 0
        total_amount = 0.0
        currency_breakdown: dict[str, float] = {}
        seen_txns: dict[str, int] = {}

        for rec in records:
            is_valid = True

            # Duplicate check
            if rec.txn_id in seen_txns:
                discrepancies.append(Discrepancy(
                    txn_id=rec.txn_id,
                    field="txn_id",
                    expected="unique",
                    actual=f"duplicate (first at row {seen_txns[rec.txn_id]})",
                    discrepancy_type="duplicate",
                ))
                is_valid = False
            seen_txns[rec.txn_id] = len(seen_txns) + 1

            # Amount validation
            if rec.amount < 0:
                discrepancies.append(Discrepancy(
                    txn_id=rec.txn_id,
                    field="amount",
                    expected=">= 0",
                    actual=str(rec.amount),
                    discrepancy_type="amount",
                ))
                is_valid = False

            # Missing required fields
            if not rec.settlement_date:
                discrepancies.append(Discrepancy(
                    txn_id=rec.txn_id,
                    field="settlement_date",
                    expected="non-empty",
                    actual="(empty)",
                    discrepancy_type="missing",
                ))
                is_valid = False

            if not rec.currency:
                discrepancies.append(Discrepancy(
                    txn_id=rec.txn_id,
                    field="currency",
                    expected="non-empty",
                    actual="(empty)",
                    discrepancy_type="currency",
                ))
                is_valid = False

            # Status validation
            if rec.status not in self.VALID_STATUSES:
                discrepancies.append(Discrepancy(
                    txn_id=rec.txn_id,
                    field="status",
                    expected=f"one of {sorted(self.VALID_STATUSES)}",
                    actual=rec.status,
                    discrepancy_type="status",
                ))
                is_valid = False

            if is_valid:
                valid_count += 1
            else:
                invalid_count += 1

            total_amount += rec.amount
            currency_breakdown[rec.currency] = (
                currency_breakdown.get(rec.currency, 0.0) + rec.amount
            )

        return SettlementReport(
            total_records=len(records),
            valid_records=valid_count,
            invalid_records=invalid_count,
            discrepancies=discrepancies,
            total_amount=round(total_amount, 2),
            currency_breakdown={k: round(v, 2) for k, v in currency_breakdown.items()},
        )

    def compare(
        self,
        our_records: list[SettlementRecord],
        bank_records: list[SettlementRecord],
    ) -> list[Discrepancy]:
        """Compare our records against bank settlement records.

        Matches by txn_id, then compares amount, status, and currency.
        Reports missing records in either direction.
        """
        our_map = {r.txn_id: r for r in our_records}
        bank_map = {r.txn_id: r for r in bank_records}
        discrepancies: list[Discrepancy] = []

        # Records in our set but missing from bank
        for txn_id in our_map:
            if txn_id not in bank_map:
                discrepancies.append(Discrepancy(
                    txn_id=txn_id,
                    field="record",
                    expected="present in bank file",
                    actual="missing",
                    discrepancy_type="missing",
                ))

        # Records in bank but missing from our set
        for txn_id in bank_map:
            if txn_id not in our_map:
                discrepancies.append(Discrepancy(
                    txn_id=txn_id,
                    field="record",
                    expected="present in our file",
                    actual="missing",
                    discrepancy_type="missing",
                ))

        # Compare matching records
        for txn_id in our_map:
            if txn_id not in bank_map:
                continue
            ours = our_map[txn_id]
            theirs = bank_map[txn_id]

            if abs(ours.amount - theirs.amount) > 0.005:
                discrepancies.append(Discrepancy(
                    txn_id=txn_id,
                    field="amount",
                    expected=str(ours.amount),
                    actual=str(theirs.amount),
                    discrepancy_type="amount",
                ))

            if ours.status != theirs.status:
                discrepancies.append(Discrepancy(
                    txn_id=txn_id,
                    field="status",
                    expected=ours.status,
                    actual=theirs.status,
                    discrepancy_type="status",
                ))

            if ours.currency != theirs.currency:
                discrepancies.append(Discrepancy(
                    txn_id=txn_id,
                    field="currency",
                    expected=ours.currency,
                    actual=theirs.currency,
                    discrepancy_type="currency",
                ))

        logger.info(
            "Comparison complete: %d our records, %d bank records, %d discrepancies",
            len(our_records), len(bank_records), len(discrepancies),
        )
        return discrepancies

    def generate_adjustments(self, discrepancies: list[Discrepancy]) -> str:
        """Generate a CSV string of adjustment entries from discrepancies.

        Returns a CSV with columns: txn_id, adjustment_type, field, expected, actual, action.
        """
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["txn_id", "adjustment_type", "field", "expected", "actual", "action"])

        for d in discrepancies:
            if d.discrepancy_type == "amount":
                action = "credit_adjustment" if d.expected > d.actual else "debit_adjustment"
            elif d.discrepancy_type == "missing":
                action = "investigate"
            elif d.discrepancy_type == "status":
                action = "status_correction"
            elif d.discrepancy_type == "currency":
                action = "currency_correction"
            elif d.discrepancy_type == "duplicate":
                action = "deduplicate"
            else:
                action = "review"

            writer.writerow([
                d.txn_id,
                d.discrepancy_type,
                d.field,
                d.expected,
                d.actual,
                action,
            ])

        return output.getvalue()


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def format_settlement_report(report: SettlementReport) -> str:
    """Format a SettlementReport as a human-readable string."""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("  SETTLEMENT VALIDATION REPORT")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"  Total records:   {report.total_records}")
    lines.append(f"  Valid records:   {report.valid_records}")
    lines.append(f"  Invalid records: {report.invalid_records}")
    lines.append(f"  Total amount:    {report.total_amount:,.2f}")
    lines.append("")

    if report.currency_breakdown:
        lines.append("  Currency Breakdown:")
        for cur, amt in sorted(report.currency_breakdown.items()):
            lines.append(f"    {cur}: {amt:,.2f}")
        lines.append("")

    if report.discrepancies:
        lines.append(f"  Discrepancies ({len(report.discrepancies)}):")
        lines.append(f"  {'-' * 56}")
        for d in report.discrepancies[:50]:  # cap display at 50
            lines.append(
                f"    [{d.discrepancy_type.upper():10s}] {d.txn_id}: "
                f"{d.field} — expected={d.expected}, actual={d.actual}"
            )
        if len(report.discrepancies) > 50:
            lines.append(f"    ... and {len(report.discrepancies) - 50} more")
        lines.append("")
    else:
        lines.append("  No discrepancies found.")
        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)
