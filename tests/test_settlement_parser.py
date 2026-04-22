"""Tests for the settlement file parser & validator."""

from __future__ import annotations

import csv
import io
import os
import tempfile

import pytest

from code_agents.domain.settlement_parser import (
    SettlementParser,
    SettlementRecord,
    SettlementValidator,
    SettlementReport,
    Discrepancy,
    format_settlement_report,
    _map_headers,
    _normalize_header,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_csv(rows: list[list[str]], suffix: str = ".csv") -> str:
    """Write rows to a temp CSV file and return the path."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for row in rows:
            writer.writerow(row)
    return path


def _make_record(
    txn_id: str = "TXN001",
    amount: float = 100.0,
    currency: str = "INR",
    status: str = "settled",
    settlement_date: str = "2026-04-01",
    acquirer_ref: str = "ACQ001",
    merchant_id: str = "MID001",
) -> SettlementRecord:
    return SettlementRecord(
        txn_id=txn_id,
        amount=amount,
        currency=currency,
        status=status,
        settlement_date=settlement_date,
        acquirer_ref=acquirer_ref,
        merchant_id=merchant_id,
    )


# ---------------------------------------------------------------------------
# TestGenericCsv — parse various column formats
# ---------------------------------------------------------------------------

class TestGenericCsv:
    """Test parsing of generic CSV files with different column names."""

    def test_standard_headers(self):
        path = _write_csv([
            ["txn_id", "amount", "currency", "status", "settlement_date"],
            ["T001", "100.50", "INR", "settled", "2026-04-01"],
            ["T002", "200.00", "INR", "pending", "2026-04-01"],
        ])
        parser = SettlementParser()
        records = parser.parse(path, format="csv")
        assert len(records) == 2
        assert records[0].txn_id == "T001"
        assert records[0].amount == 100.50
        assert records[1].status == "pending"
        os.unlink(path)

    def test_alternative_headers(self):
        path = _write_csv([
            ["transaction_id", "txn_amount", "currency_code", "txn_status", "date"],
            ["T001", "50.25", "USD", "success", "2026-04-01"],
        ])
        parser = SettlementParser()
        records = parser.parse(path, format="csv")
        assert len(records) == 1
        assert records[0].txn_id == "T001"
        assert records[0].amount == 50.25
        assert records[0].currency == "USD"
        os.unlink(path)

    def test_tsv_file(self):
        fd, path = tempfile.mkstemp(suffix=".tsv")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("txn_id\tamount\tcurrency\tstatus\tsettlement_date\n")
            f.write("T001\t100.00\tINR\tsettled\t2026-04-01\n")
        parser = SettlementParser()
        records = parser.parse(path, format="csv")
        assert len(records) == 1
        assert records[0].txn_id == "T001"
        os.unlink(path)

    def test_amount_with_commas(self):
        path = _write_csv([
            ["txn_id", "amount", "currency", "status", "settlement_date"],
            ["T001", "1,000.50", "INR", "settled", "2026-04-01"],
        ])
        parser = SettlementParser()
        records = parser.parse(path, format="csv")
        assert records[0].amount == 1000.50
        os.unlink(path)

    def test_empty_amount(self):
        path = _write_csv([
            ["txn_id", "amount", "currency", "status", "settlement_date"],
            ["T001", "", "INR", "settled", "2026-04-01"],
        ])
        parser = SettlementParser()
        records = parser.parse(path, format="csv")
        assert records[0].amount == 0.0
        os.unlink(path)

    def test_skips_empty_txn_id(self):
        path = _write_csv([
            ["txn_id", "amount", "currency", "status", "settlement_date"],
            ["T001", "100.00", "INR", "settled", "2026-04-01"],
            ["", "50.00", "INR", "settled", "2026-04-01"],
        ])
        parser = SettlementParser()
        records = parser.parse(path, format="csv")
        assert len(records) == 1
        os.unlink(path)

    def test_missing_txn_column_raises(self):
        path = _write_csv([
            ["foo", "bar", "baz"],
            ["1", "2", "3"],
        ])
        parser = SettlementParser()
        with pytest.raises(ValueError, match="Cannot find transaction ID column"):
            parser.parse(path, format="csv")
        os.unlink(path)

    def test_empty_file(self):
        fd, path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("")
        parser = SettlementParser()
        records = parser.parse(path, format="csv")
        assert records == []
        os.unlink(path)

    def test_file_not_found(self):
        parser = SettlementParser()
        with pytest.raises(FileNotFoundError):
            parser.parse("/nonexistent/file.csv")

    def test_merchant_and_acquirer_fields(self):
        path = _write_csv([
            ["txn_id", "amount", "currency", "status", "settlement_date", "merchant_id", "acquirer_ref"],
            ["T001", "100.00", "INR", "settled", "2026-04-01", "MID001", "ACQ001"],
        ])
        parser = SettlementParser()
        records = parser.parse(path, format="csv")
        assert records[0].merchant_id == "MID001"
        assert records[0].acquirer_ref == "ACQ001"
        os.unlink(path)


# ---------------------------------------------------------------------------
# TestFormatDetection — auto-detect from headers/filename
# ---------------------------------------------------------------------------

class TestFormatDetection:
    """Test auto-format detection from filenames and headers."""

    def setup_method(self):
        self.parser = SettlementParser()

    def test_visa_filename(self):
        fd, path = tempfile.mkstemp(prefix="visa_tc33_", suffix=".csv")
        with os.fdopen(fd, "w") as f:
            f.write("txn_id,amount\n")
        assert self.parser._detect_format(path) == "visa"
        os.unlink(path)

    def test_mastercard_filename(self):
        fd, path = tempfile.mkstemp(prefix="mastercard_ipm_", suffix=".csv")
        with os.fdopen(fd, "w") as f:
            f.write("txn_id,amount\n")
        assert self.parser._detect_format(path) == "mastercard"
        os.unlink(path)

    def test_upi_filename(self):
        fd, path = tempfile.mkstemp(prefix="npci_upi_", suffix=".csv")
        with os.fdopen(fd, "w") as f:
            f.write("txn_id,amount\n")
        assert self.parser._detect_format(path) == "upi"
        os.unlink(path)

    def test_upi_header_detection(self):
        fd, path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w") as f:
            f.write("utr,amount,status\nUTR001,100,settled\n")
        assert self.parser._detect_format(path) == "upi"
        os.unlink(path)

    def test_generic_fallback(self):
        fd, path = tempfile.mkstemp(prefix="data_", suffix=".csv")
        with os.fdopen(fd, "w") as f:
            f.write("txn_id,amount,status\n")
        assert self.parser._detect_format(path) == "csv"
        os.unlink(path)

    def test_auto_format_in_parse(self):
        path = _write_csv([
            ["txn_id", "amount", "currency", "status", "settlement_date"],
            ["T001", "100.00", "INR", "settled", "2026-04-01"],
        ])
        records = self.parser.parse(path, format="auto")
        assert len(records) == 1
        os.unlink(path)


# ---------------------------------------------------------------------------
# TestValidation — duplicates, missing fields, invalid amounts
# ---------------------------------------------------------------------------

class TestValidation:
    """Test settlement record validation."""

    def setup_method(self):
        self.validator = SettlementValidator()

    def test_valid_records(self):
        records = [
            _make_record(txn_id="T001", amount=100.0),
            _make_record(txn_id="T002", amount=200.0),
        ]
        report = self.validator.validate(records)
        assert report.total_records == 2
        assert report.valid_records == 2
        assert report.invalid_records == 0
        assert report.discrepancies == []
        assert report.total_amount == 300.0

    def test_duplicate_txn_ids(self):
        records = [
            _make_record(txn_id="T001"),
            _make_record(txn_id="T001"),
        ]
        report = self.validator.validate(records)
        assert report.invalid_records >= 1
        types = [d.discrepancy_type for d in report.discrepancies]
        assert "duplicate" in types

    def test_negative_amount(self):
        records = [_make_record(txn_id="T001", amount=-50.0)]
        report = self.validator.validate(records)
        assert report.invalid_records == 1
        types = [d.discrepancy_type for d in report.discrepancies]
        assert "amount" in types

    def test_missing_settlement_date(self):
        records = [_make_record(txn_id="T001", settlement_date="")]
        report = self.validator.validate(records)
        assert report.invalid_records == 1
        types = [d.discrepancy_type for d in report.discrepancies]
        assert "missing" in types

    def test_missing_currency(self):
        records = [_make_record(txn_id="T001", currency="")]
        report = self.validator.validate(records)
        assert report.invalid_records == 1
        types = [d.discrepancy_type for d in report.discrepancies]
        assert "currency" in types

    def test_invalid_status(self):
        records = [_make_record(txn_id="T001", status="bogus")]
        report = self.validator.validate(records)
        assert report.invalid_records == 1
        types = [d.discrepancy_type for d in report.discrepancies]
        assert "status" in types

    def test_currency_breakdown(self):
        records = [
            _make_record(txn_id="T001", amount=100.0, currency="INR"),
            _make_record(txn_id="T002", amount=200.0, currency="USD"),
            _make_record(txn_id="T003", amount=50.0, currency="INR"),
        ]
        report = self.validator.validate(records)
        assert report.currency_breakdown["INR"] == 150.0
        assert report.currency_breakdown["USD"] == 200.0

    def test_multiple_issues_same_record(self):
        records = [_make_record(txn_id="T001", amount=-10.0, settlement_date="", status="bogus")]
        report = self.validator.validate(records)
        assert report.invalid_records == 1
        assert len(report.discrepancies) >= 3


# ---------------------------------------------------------------------------
# TestComparison — match/mismatch/missing records
# ---------------------------------------------------------------------------

class TestComparison:
    """Test comparison between our records and bank records."""

    def setup_method(self):
        self.validator = SettlementValidator()

    def test_perfect_match(self):
        our = [_make_record(txn_id="T001", amount=100.0)]
        bank = [_make_record(txn_id="T001", amount=100.0)]
        disc = self.validator.compare(our, bank)
        assert disc == []

    def test_amount_mismatch(self):
        our = [_make_record(txn_id="T001", amount=100.0)]
        bank = [_make_record(txn_id="T001", amount=99.0)]
        disc = self.validator.compare(our, bank)
        assert len(disc) == 1
        assert disc[0].discrepancy_type == "amount"

    def test_status_mismatch(self):
        our = [_make_record(txn_id="T001", status="settled")]
        bank = [_make_record(txn_id="T001", status="pending")]
        disc = self.validator.compare(our, bank)
        assert len(disc) == 1
        assert disc[0].discrepancy_type == "status"

    def test_currency_mismatch(self):
        our = [_make_record(txn_id="T001", currency="INR")]
        bank = [_make_record(txn_id="T001", currency="USD")]
        disc = self.validator.compare(our, bank)
        assert len(disc) == 1
        assert disc[0].discrepancy_type == "currency"

    def test_missing_in_bank(self):
        our = [_make_record(txn_id="T001"), _make_record(txn_id="T002")]
        bank = [_make_record(txn_id="T001")]
        disc = self.validator.compare(our, bank)
        missing = [d for d in disc if d.discrepancy_type == "missing"]
        assert len(missing) == 1
        assert missing[0].txn_id == "T002"

    def test_missing_in_our(self):
        our = [_make_record(txn_id="T001")]
        bank = [_make_record(txn_id="T001"), _make_record(txn_id="T003")]
        disc = self.validator.compare(our, bank)
        missing = [d for d in disc if d.discrepancy_type == "missing"]
        assert len(missing) == 1
        assert missing[0].txn_id == "T003"

    def test_multiple_mismatches(self):
        our = [
            _make_record(txn_id="T001", amount=100.0, status="settled"),
            _make_record(txn_id="T002", amount=200.0),
        ]
        bank = [
            _make_record(txn_id="T001", amount=105.0, status="pending"),
            _make_record(txn_id="T002", amount=200.0),
        ]
        disc = self.validator.compare(our, bank)
        assert len(disc) == 2  # amount + status mismatch for T001

    def test_amount_within_tolerance(self):
        our = [_make_record(txn_id="T001", amount=100.00)]
        bank = [_make_record(txn_id="T001", amount=100.004)]
        disc = self.validator.compare(our, bank)
        assert disc == []


# ---------------------------------------------------------------------------
# TestAdjustments — generate adjustment entries
# ---------------------------------------------------------------------------

class TestAdjustments:
    """Test adjustment CSV generation."""

    def setup_method(self):
        self.validator = SettlementValidator()

    def test_empty_discrepancies(self):
        result = self.validator.generate_adjustments([])
        lines = result.strip().split("\n")
        assert len(lines) == 1  # header only

    def test_amount_adjustment(self):
        disc = [Discrepancy(
            txn_id="T001", field="amount",
            expected="100.0", actual="99.0",
            discrepancy_type="amount",
        )]
        result = self.validator.generate_adjustments(disc)
        assert "T001" in result
        # expected > actual (string compare) => credit_adjustment or debit_adjustment
        assert "adjustment" in result

    def test_amount_credit_adjustment(self):
        disc = [Discrepancy(
            txn_id="T001", field="amount",
            expected="99.0", actual="100.0",
            discrepancy_type="amount",
        )]
        result = self.validator.generate_adjustments(disc)
        assert "T001" in result
        assert "adjustment" in result

    def test_missing_adjustment(self):
        disc = [Discrepancy(
            txn_id="T002", field="record",
            expected="present in bank file", actual="missing",
            discrepancy_type="missing",
        )]
        result = self.validator.generate_adjustments(disc)
        assert "investigate" in result

    def test_status_adjustment(self):
        disc = [Discrepancy(
            txn_id="T003", field="status",
            expected="settled", actual="pending",
            discrepancy_type="status",
        )]
        result = self.validator.generate_adjustments(disc)
        assert "status_correction" in result

    def test_duplicate_adjustment(self):
        disc = [Discrepancy(
            txn_id="T004", field="txn_id",
            expected="unique", actual="duplicate (first at row 1)",
            discrepancy_type="duplicate",
        )]
        result = self.validator.generate_adjustments(disc)
        assert "deduplicate" in result

    def test_csv_is_parseable(self):
        disc = [
            Discrepancy("T001", "amount", "100", "99", "amount"),
            Discrepancy("T002", "record", "present", "missing", "missing"),
        ]
        result = self.validator.generate_adjustments(disc)
        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["txn_id"] == "T001"
        assert rows[1]["action"] == "investigate"


# ---------------------------------------------------------------------------
# TestFormatReport — report formatting
# ---------------------------------------------------------------------------

class TestFormatReport:
    """Test report formatting."""

    def test_report_with_discrepancies(self):
        report = SettlementReport(
            total_records=10,
            valid_records=8,
            invalid_records=2,
            discrepancies=[
                Discrepancy("T001", "amount", "100", "99", "amount"),
            ],
            total_amount=1000.0,
            currency_breakdown={"INR": 800.0, "USD": 200.0},
        )
        text = format_settlement_report(report)
        assert "Total records:   10" in text
        assert "Valid records:   8" in text
        assert "INR" in text
        assert "USD" in text
        assert "T001" in text

    def test_report_no_discrepancies(self):
        report = SettlementReport(
            total_records=5,
            valid_records=5,
            invalid_records=0,
            discrepancies=[],
            total_amount=500.0,
            currency_breakdown={"INR": 500.0},
        )
        text = format_settlement_report(report)
        assert "No discrepancies found" in text


# ---------------------------------------------------------------------------
# TestHeaderMapping — internal utilities
# ---------------------------------------------------------------------------

class TestHeaderMapping:
    """Test header normalization and mapping."""

    def test_normalize_header(self):
        assert _normalize_header("Transaction ID") == "transaction_id"
        assert _normalize_header("  Amount  ") == "amount"
        assert _normalize_header("currency-code") == "currency_code"

    def test_map_standard_headers(self):
        headers = ["txn_id", "amount", "currency", "status", "settlement_date"]
        mapping = _map_headers(headers)
        assert mapping["txn_id"] == "txn_id"
        assert mapping["amount"] == "amount"

    def test_map_alternative_headers(self):
        headers = ["reference", "net_amount", "ccy", "state", "value_date"]
        mapping = _map_headers(headers)
        assert mapping["txn_id"] == "reference"
        assert mapping["amount"] == "net_amount"
        assert mapping["currency"] == "ccy"
        assert mapping["status"] == "state"
        assert mapping["settlement_date"] == "value_date"

    def test_unmapped_headers(self):
        headers = ["foo", "bar"]
        mapping = _map_headers(headers)
        assert mapping["txn_id"] is None
        assert mapping["amount"] is None
