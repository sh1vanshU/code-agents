"""Tests for code_agents.recon_debug — Payment Reconciliation Debugger."""

from __future__ import annotations

import json
import os
import tempfile
from unittest import TestCase

from code_agents.observability.recon_debug import (
    ReconDebugger,
    ReconMismatch,
    ReconRecord,
    ReconReport,
    format_recon_json,
    format_recon_report,
)


def _write_csv(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


class TestParseCsv(TestCase):
    """Test CSV parsing with various column name formats."""

    def setUp(self):
        self.debugger = ReconDebugger()
        self.tmpdir = tempfile.mkdtemp()

    def test_standard_column_names(self):
        path = os.path.join(self.tmpdir, "orders.csv")
        _write_csv(path, "txn_id,amount,status,currency,date\nTXN001,500.00,success,INR,2026-04-09\n")
        records = self.debugger._parse_csv(path, "order")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].txn_id, "TXN001")
        self.assertEqual(records[0].amount, 500.0)
        self.assertEqual(records[0].status, "success")
        self.assertEqual(records[0].currency, "INR")
        self.assertEqual(records[0].source, "order")

    def test_alternative_column_names(self):
        path = os.path.join(self.tmpdir, "orders.csv")
        _write_csv(path, "order_id,total,payment_status,ccy,created_at\nTXN002,750.50,pending,USD,2026-04-09\n")
        records = self.debugger._parse_csv(path, "order")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].txn_id, "TXN002")
        self.assertEqual(records[0].amount, 750.50)
        self.assertEqual(records[0].status, "pending")
        self.assertEqual(records[0].currency, "USD")

    def test_transaction_id_column(self):
        path = os.path.join(self.tmpdir, "settle.csv")
        _write_csv(path, "transaction_id,amount,status\nTXN003,100.00,success\n")
        records = self.debugger._parse_csv(path, "settlement")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].txn_id, "TXN003")
        self.assertEqual(records[0].source, "settlement")

    def test_tsv_format(self):
        path = os.path.join(self.tmpdir, "data.tsv")
        _write_csv(path, "txn_id\tamount\tstatus\tcurrency\tdate\nTXN004\t200.00\tsuccess\tINR\t2026-04-09\n")
        records = self.debugger._parse_csv(path, "order")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].txn_id, "TXN004")
        self.assertEqual(records[0].amount, 200.0)

    def test_missing_txn_id_column_raises(self):
        path = os.path.join(self.tmpdir, "bad.csv")
        _write_csv(path, "foo,bar,baz\n1,2,3\n")
        with self.assertRaises(ValueError) as ctx:
            self.debugger._parse_csv(path, "order")
        self.assertIn("No transaction ID column", str(ctx.exception))

    def test_missing_amount_column_raises(self):
        path = os.path.join(self.tmpdir, "bad2.csv")
        _write_csv(path, "txn_id,foo\nTXN001,bar\n")
        with self.assertRaises(ValueError) as ctx:
            self.debugger._parse_csv(path, "order")
        self.assertIn("No amount column", str(ctx.exception))

    def test_default_currency(self):
        path = os.path.join(self.tmpdir, "noccy.csv")
        _write_csv(path, "txn_id,amount,status\nTXN005,300.00,success\n")
        records = self.debugger._parse_csv(path, "order")
        self.assertEqual(records[0].currency, "INR")

    def test_comma_in_amount(self):
        path = os.path.join(self.tmpdir, "comma.csv")
        _write_csv(path, 'txn_id,amount,status\nTXN006,"1,500.00",success\n')
        records = self.debugger._parse_csv(path, "order")
        self.assertEqual(records[0].amount, 1500.0)

    def test_skips_empty_txn_id(self):
        path = os.path.join(self.tmpdir, "empty.csv")
        _write_csv(path, "txn_id,amount,status\nTXN007,100,success\n,200,failed\n")
        records = self.debugger._parse_csv(path, "order")
        self.assertEqual(len(records), 1)


class TestMatching(TestCase):
    """Test the record matching engine."""

    def setUp(self):
        self.debugger = ReconDebugger()

    def _order(self, txn_id, amount=100.0, status="success", currency="INR"):
        return ReconRecord(txn_id=txn_id, amount=amount, currency=currency, status=status, date="2026-04-09", source="order")

    def _settle(self, txn_id, amount=100.0, status="success", currency="INR"):
        return ReconRecord(txn_id=txn_id, amount=amount, currency=currency, status=status, date="2026-04-09", source="settlement")

    def test_exact_match(self):
        orders = [self._order("TXN001"), self._order("TXN002")]
        settlements = [self._settle("TXN001"), self._settle("TXN002")]
        report = self.debugger.reconcile(orders, settlements)
        self.assertEqual(report.matched, 2)
        self.assertEqual(report.mismatched, 0)
        self.assertEqual(report.missing_in_bank, 0)
        self.assertEqual(report.missing_in_db, 0)
        self.assertEqual(len(report.mismatches), 0)

    def test_amount_mismatch(self):
        orders = [self._order("TXN001", amount=500.0)]
        settlements = [self._settle("TXN001", amount=450.0)]
        report = self.debugger.reconcile(orders, settlements)
        self.assertEqual(report.matched, 0)
        self.assertEqual(report.mismatched, 1)
        self.assertEqual(len(report.mismatches), 1)
        self.assertEqual(report.mismatches[0].mismatch_type, "amount")
        self.assertAlmostEqual(report.amount_variance, 50.0, places=2)

    def test_status_mismatch(self):
        orders = [self._order("TXN001", status="success")]
        settlements = [self._settle("TXN001", status="pending")]
        report = self.debugger.reconcile(orders, settlements)
        self.assertEqual(report.mismatched, 1)
        self.assertEqual(report.mismatches[0].mismatch_type, "status")
        self.assertEqual(report.mismatches[0].our_value, "success")
        self.assertEqual(report.mismatches[0].bank_value, "pending")

    def test_currency_mismatch(self):
        orders = [self._order("TXN001", currency="INR")]
        settlements = [self._settle("TXN001", currency="USD")]
        report = self.debugger.reconcile(orders, settlements)
        self.assertEqual(report.mismatched, 1)
        mm = [m for m in report.mismatches if m.mismatch_type == "currency"]
        self.assertEqual(len(mm), 1)

    def test_missing_in_bank(self):
        orders = [self._order("TXN001"), self._order("TXN002")]
        settlements = [self._settle("TXN001")]
        report = self.debugger.reconcile(orders, settlements)
        self.assertEqual(report.matched, 1)
        self.assertEqual(report.missing_in_bank, 1)
        missing = [m for m in report.mismatches if m.mismatch_type == "missing_in_bank"]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0].txn_id, "TXN002")

    def test_missing_in_db(self):
        orders = [self._order("TXN001")]
        settlements = [self._settle("TXN001"), self._settle("TXN002")]
        report = self.debugger.reconcile(orders, settlements)
        self.assertEqual(report.matched, 1)
        self.assertEqual(report.missing_in_db, 1)

    def test_multiple_mismatch_types(self):
        orders = [
            self._order("TXN001", amount=500.0, status="success"),
            self._order("TXN002"),
            self._order("TXN003", currency="INR"),
        ]
        settlements = [
            self._settle("TXN001", amount=450.0, status="failed"),
            self._settle("TXN003", currency="USD"),
            self._settle("TXN004"),
        ]
        report = self.debugger.reconcile(orders, settlements)
        self.assertEqual(report.missing_in_bank, 1)  # TXN002
        self.assertEqual(report.missing_in_db, 1)    # TXN004
        self.assertTrue(report.mismatched >= 2)       # TXN001 and TXN003

    def test_empty_inputs(self):
        report = self.debugger.reconcile([], [])
        self.assertEqual(report.matched, 0)
        self.assertEqual(report.mismatched, 0)
        self.assertEqual(len(report.mismatches), 0)

    def test_amount_variance_accumulates(self):
        orders = [self._order("TXN001", amount=1000.0), self._order("TXN002", amount=500.0)]
        settlements = [self._settle("TXN001", amount=900.0), self._settle("TXN002", amount=480.0)]
        report = self.debugger.reconcile(orders, settlements)
        self.assertAlmostEqual(report.amount_variance, 120.0, places=2)


class TestReconcileFromFiles(TestCase):
    """Test file-based reconciliation."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.debugger = ReconDebugger(cwd=self.tmpdir)

    def test_reconcile_from_csv(self):
        orders_path = os.path.join(self.tmpdir, "orders.csv")
        settle_path = os.path.join(self.tmpdir, "settlements.csv")
        _write_csv(orders_path, "txn_id,amount,status,currency\nTXN001,500,success,INR\nTXN002,300,success,INR\n")
        _write_csv(settle_path, "txn_id,amount,status,currency\nTXN001,500,success,INR\nTXN003,200,success,INR\n")
        report = self.debugger.reconcile_from_files("orders.csv", "settlements.csv")
        self.assertEqual(report.matched, 1)
        self.assertEqual(report.missing_in_bank, 1)
        self.assertEqual(report.missing_in_db, 1)

    def test_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            self.debugger.reconcile_from_files("nonexistent.csv", "also_missing.csv")


class TestCommonIssues(TestCase):
    """Test common issue detection patterns."""

    def setUp(self):
        self.debugger = ReconDebugger()

    def test_detect_timeout_retries(self):
        mismatches = [
            ReconMismatch(txn_id=f"TXN{i:03d}", field="presence", our_value="exists", bank_value="missing", mismatch_type="missing_in_bank")
            for i in range(5)
        ]
        issues = self.debugger._detect_common_issues(mismatches)
        self.assertTrue(any("timeout retries" in issue.lower() for issue in issues))

    def test_detect_duplicate_callbacks(self):
        mismatches = [
            ReconMismatch(txn_id="TXN001", field="presence", our_value="missing", bank_value="exists", mismatch_type="missing_in_db")
        ]
        issues = self.debugger._detect_common_issues(mismatches)
        self.assertTrue(any("callback" in issue.lower() or "webhook" in issue.lower() for issue in issues))

    def test_detect_rounding_errors(self):
        mismatches = [
            ReconMismatch(txn_id="TXN001", field="amount", our_value="100.10", bank_value="100.00", mismatch_type="amount"),
            ReconMismatch(txn_id="TXN002", field="amount", our_value="200.05", bank_value="200.00", mismatch_type="amount"),
        ]
        issues = self.debugger._detect_common_issues(mismatches)
        self.assertTrue(any("rounding" in issue.lower() for issue in issues))

    def test_detect_large_discrepancies(self):
        mismatches = [
            ReconMismatch(txn_id="TXN001", field="amount", our_value="1000.00", bank_value="500.00", mismatch_type="amount"),
        ]
        issues = self.debugger._detect_common_issues(mismatches)
        self.assertTrue(any("large" in issue.lower() or "discrepanc" in issue.lower() for issue in issues))

    def test_detect_currency_mismatch(self):
        mismatches = [
            ReconMismatch(txn_id="TXN001", field="currency", our_value="INR", bank_value="USD", mismatch_type="currency"),
        ]
        issues = self.debugger._detect_common_issues(mismatches)
        self.assertTrue(any("currency" in issue.lower() for issue in issues))

    def test_detect_status_mismatch_patterns(self):
        mismatches = [
            ReconMismatch(txn_id="TXN001", field="status", our_value="success", bank_value="pending", mismatch_type="status"),
            ReconMismatch(txn_id="TXN002", field="status", our_value="success", bank_value="pending", mismatch_type="status"),
        ]
        issues = self.debugger._detect_common_issues(mismatches)
        self.assertTrue(any("status" in issue.lower() for issue in issues))

    def test_no_issues_on_empty(self):
        issues = self.debugger._detect_common_issues([])
        self.assertEqual(issues, [])


class TestFormatReport(TestCase):
    """Test report formatting."""

    def _make_report(self, **overrides):
        defaults = dict(
            date="2026-04-09",
            total_orders=1234,
            total_settlements=1230,
            matched=1220,
            mismatched=10,
            missing_in_bank=4,
            missing_in_db=0,
            mismatches=[
                ReconMismatch(txn_id="TXN001", field="amount", our_value="500.00", bank_value="450.00", mismatch_type="amount"),
            ],
            amount_variance=45230.00,
            common_issues=[],
        )
        defaults.update(overrides)
        return ReconReport(**defaults)

    def test_report_contains_header(self):
        report = self._make_report()
        text = format_recon_report(report)
        self.assertIn("Reconciliation Report", text)
        self.assertIn("2026-04-09", text)

    def test_report_contains_counts(self):
        report = self._make_report()
        text = format_recon_report(report)
        self.assertIn("1,234", text)
        self.assertIn("1,230", text)
        self.assertIn("1,220", text)

    def test_report_contains_mismatches(self):
        report = self._make_report()
        text = format_recon_report(report)
        self.assertIn("TXN001", text)
        self.assertIn("500.00", text)
        self.assertIn("450.00", text)

    def test_report_contains_variance(self):
        report = self._make_report()
        text = format_recon_report(report)
        self.assertIn("45,230.00", text)

    def test_report_missing_in_bank(self):
        report = self._make_report(
            mismatches=[
                ReconMismatch(txn_id="TXN099", field="presence", our_value="exists", bank_value="missing", mismatch_type="missing_in_bank"),
            ]
        )
        text = format_recon_report(report)
        self.assertIn("TXN099", text)
        self.assertIn("missing in bank", text)

    def test_report_common_issues(self):
        report = self._make_report(common_issues=["Rounding errors detected"])
        text = format_recon_report(report)
        self.assertIn("Common Issues Detected", text)
        self.assertIn("Rounding errors", text)

    def test_json_format(self):
        report = self._make_report()
        data = format_recon_json(report)
        self.assertEqual(data["total_orders"], 1234)
        self.assertEqual(data["matched"], 1220)
        self.assertEqual(len(data["mismatches"]), 1)
        self.assertEqual(data["mismatches"][0]["txn_id"], "TXN001")
        # Ensure it's JSON serialisable
        json.dumps(data)

    def test_report_no_mismatches(self):
        report = self._make_report(mismatches=[], mismatched=0)
        text = format_recon_report(report)
        self.assertIn("Reconciliation Report", text)
        self.assertNotIn("Mismatches:", text)

    def test_report_box_drawing_chars(self):
        report = self._make_report()
        text = format_recon_report(report)
        # Verify box-drawing characters are present
        self.assertIn("\u256d", text)  # top-left
        self.assertIn("\u256f", text)  # bottom-right
