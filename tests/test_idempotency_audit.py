"""Tests for code_agents.idempotency_audit — Idempotency Key Auditor."""

from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path

import pytest

from code_agents.domain.idempotency_audit import (
    IdempotencyAuditor,
    IdempotencyFinding,
    format_idempotency_report,
)


@pytest.fixture()
def tmp_repo(tmp_path: Path) -> Path:
    """Create a temporary repo directory."""
    return tmp_path


def _write(repo: Path, relpath: str, content: str) -> Path:
    """Write a file under the temp repo."""
    fp = repo / relpath
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(textwrap.dedent(content), encoding="utf-8")
    return fp


# ---------------------------------------------------------------------------
# TestFindEndpoints
# ---------------------------------------------------------------------------

class TestFindEndpoints:
    """Detect POST endpoints in FastAPI, Spring, and Express code."""

    def test_fastapi_post(self, tmp_repo: Path):
        _write(tmp_repo, "app/pay.py", """\
            from fastapi import APIRouter
            router = APIRouter()

            @router.post("/api/v1/pay")
            async def create_payment(req):
                pass
        """)
        auditor = IdempotencyAuditor(cwd=str(tmp_repo))
        eps = auditor._find_payment_endpoints()
        assert len(eps) == 1
        assert eps[0].method == "POST"
        assert "/pay" in eps[0].path

    def test_spring_post_mapping(self, tmp_repo: Path):
        _write(tmp_repo, "src/PayController.java", """\
            @RestController
            public class PayController {
                @PostMapping("/api/charge")
                public ResponseEntity charge(@RequestBody Req req) {
                    return ok();
                }
            }
        """)
        auditor = IdempotencyAuditor(cwd=str(tmp_repo))
        eps = auditor._find_payment_endpoints()
        assert len(eps) == 1
        assert eps[0].method == "POST"
        assert "/charge" in eps[0].path

    def test_express_post(self, tmp_repo: Path):
        _write(tmp_repo, "routes/order.js", """\
            const express = require('express');
            const router = express.Router();
            router.post('/api/order/create', (req, res) => {
                res.json({ok: true});
            });
        """)
        auditor = IdempotencyAuditor(cwd=str(tmp_repo))
        eps = auditor._find_payment_endpoints()
        assert len(eps) == 1
        assert "/order" in eps[0].path

    def test_non_payment_endpoint_ignored(self, tmp_repo: Path):
        _write(tmp_repo, "app/user.py", """\
            from fastapi import APIRouter
            router = APIRouter()

            @router.post("/api/v1/users")
            async def create_user(req):
                pass
        """)
        auditor = IdempotencyAuditor(cwd=str(tmp_repo))
        eps = auditor._find_payment_endpoints()
        assert len(eps) == 0

    def test_put_and_patch_detected(self, tmp_repo: Path):
        _write(tmp_repo, "app/refund.py", """\
            from fastapi import APIRouter
            router = APIRouter()

            @router.put("/api/v1/refund/process")
            async def process_refund(req):
                pass

            @router.patch("/api/v1/capture/update")
            async def update_capture(req):
                pass
        """)
        auditor = IdempotencyAuditor(cwd=str(tmp_repo))
        eps = auditor._find_payment_endpoints()
        assert len(eps) == 2
        methods = {ep.method for ep in eps}
        assert "PUT" in methods
        assert "PATCH" in methods


# ---------------------------------------------------------------------------
# TestIdempotencyKey
# ---------------------------------------------------------------------------

class TestIdempotencyKey:
    """Endpoint with idempotency key -> info, without -> critical."""

    def test_missing_key_is_critical(self, tmp_repo: Path):
        _write(tmp_repo, "app/pay.py", """\
            from fastapi import APIRouter
            router = APIRouter()

            @router.post("/api/v1/pay")
            async def create_payment(amount: int):
                db.save(amount)
        """)
        auditor = IdempotencyAuditor(cwd=str(tmp_repo))
        findings = auditor.audit()
        critical = [f for f in findings if f.severity == "critical" and "idempotency key" in f.issue.lower()]
        assert len(critical) >= 1

    def test_header_key_detected(self, tmp_repo: Path):
        _write(tmp_repo, "app/pay.py", """\
            from fastapi import APIRouter, Header
            router = APIRouter()

            @router.post("/api/v1/pay")
            async def create_payment(
                amount: int,
                x_idempotency_key: str = Header(alias="X-Idempotency-Key"),
            ):
                if cache.get(x_idempotency_key):
                    return cache.get(x_idempotency_key)
                result = db.save(amount)
                cache.set(x_idempotency_key, result)
                return result
        """)
        auditor = IdempotencyAuditor(cwd=str(tmp_repo))
        findings = auditor.audit()
        key_findings = [f for f in findings if "idempotency key" in f.issue.lower()]
        # Should be info (detected), not critical
        assert all(f.severity == "info" for f in key_findings)

    def test_param_key_detected(self, tmp_repo: Path):
        _write(tmp_repo, "app/pay.py", """\
            from fastapi import APIRouter
            router = APIRouter()

            @router.post("/api/v1/pay")
            async def create_payment(amount: int, idempotency_key: str):
                existing = db.find_by_key(idempotency_key)
                if existing:
                    return existing
                return db.save(amount, idempotency_key)
        """)
        auditor = IdempotencyAuditor(cwd=str(tmp_repo))
        findings = auditor.audit()
        key_findings = [f for f in findings if "idempotency key" in f.issue.lower()]
        assert all(f.severity == "info" for f in key_findings)


# ---------------------------------------------------------------------------
# TestAtomicOps
# ---------------------------------------------------------------------------

class TestAtomicOps:
    """With transaction -> no finding, without -> warning."""

    def test_missing_transaction_is_warning(self, tmp_repo: Path):
        _write(tmp_repo, "app/pay.py", """\
            from fastapi import APIRouter
            router = APIRouter()

            @router.post("/api/v1/pay")
            async def create_payment(amount: int, idempotency_key: str):
                order = Order.create(amount=amount)
                order.status = "PAID"
                order.save()
        """)
        auditor = IdempotencyAuditor(cwd=str(tmp_repo))
        findings = auditor.audit()
        atomic_warnings = [f for f in findings if f.severity == "warning" and "atomic" in f.issue.lower()]
        assert len(atomic_warnings) >= 1

    def test_transaction_atomic_present(self, tmp_repo: Path):
        _write(tmp_repo, "app/pay.py", """\
            from fastapi import APIRouter
            from django.db import transaction
            router = APIRouter()

            @router.post("/api/v1/pay")
            async def create_payment(amount: int, idempotency_key: str):
                with transaction.atomic():
                    order = Order.create(amount=amount)
                    order.status = "PAID"
                    order.save()
        """)
        auditor = IdempotencyAuditor(cwd=str(tmp_repo))
        findings = auditor.audit()
        atomic_warnings = [f for f in findings if f.severity == "warning" and "atomic" in f.issue.lower()]
        assert len(atomic_warnings) == 0

    def test_spring_transactional(self, tmp_repo: Path):
        _write(tmp_repo, "src/PayService.java", """\
            @RestController
            public class PayService {
                @PostMapping("/api/authorize")
                @Transactional
                public ResponseEntity authorize(@RequestBody Req req) {
                    String idempotency_key = req.getIdempotencyKey();
                    if (order.status == "PENDING") {
                        order.setStatus("AUTHORIZED");
                        version = order.getVersion();
                    }
                    return ok();
                }
            }
        """)
        auditor = IdempotencyAuditor(cwd=str(tmp_repo))
        findings = auditor.audit()
        atomic_warnings = [f for f in findings if f.severity == "warning" and "atomic" in f.issue.lower()]
        assert len(atomic_warnings) == 0


# ---------------------------------------------------------------------------
# TestRetrySafety
# ---------------------------------------------------------------------------

class TestRetrySafety:
    """INSERT without ON CONFLICT -> warning."""

    def test_insert_without_conflict_clause(self, tmp_repo: Path):
        _write(tmp_repo, "app/pay.py", """\
            from fastapi import APIRouter
            router = APIRouter()

            @router.post("/api/v1/pay")
            async def create_payment(amount: int, idempotency_key: str):
                with transaction.atomic():
                    if order.status == "PENDING":
                        db.execute("INSERT INTO payments (amount) VALUES (%s)", [amount])
        """)
        auditor = IdempotencyAuditor(cwd=str(tmp_repo))
        findings = auditor.audit()
        retry_warnings = [f for f in findings if "INSERT" in f.issue]
        assert len(retry_warnings) >= 1

    def test_insert_with_on_conflict_ok(self, tmp_repo: Path):
        _write(tmp_repo, "app/pay.py", """\
            from fastapi import APIRouter
            router = APIRouter()

            @router.post("/api/v1/pay")
            async def create_payment(amount: int, idempotency_key: str):
                with transaction.atomic():
                    if order.status == "PENDING":
                        db.execute(
                            "INSERT INTO payments (amount, key) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
                            [amount, idempotency_key],
                        )
        """)
        auditor = IdempotencyAuditor(cwd=str(tmp_repo))
        findings = auditor.audit()
        retry_warnings = [f for f in findings if "INSERT" in f.issue]
        assert len(retry_warnings) == 0

    def test_counter_increment_warning(self, tmp_repo: Path):
        _write(tmp_repo, "app/pay.py", """\
            from fastapi import APIRouter
            router = APIRouter()

            @router.post("/api/v1/pay")
            async def create_payment(amount: int, idempotency_key: str):
                with transaction.atomic():
                    if order.status == "PENDING":
                        order.attempt_count += 1
                        order.save()
        """)
        auditor = IdempotencyAuditor(cwd=str(tmp_repo))
        findings = auditor.audit()
        counter_warnings = [f for f in findings if "counter" in f.issue.lower() or "increment" in f.issue.lower()]
        assert len(counter_warnings) >= 1


# ---------------------------------------------------------------------------
# TestDoubleCharge
# ---------------------------------------------------------------------------

class TestDoubleCharge:
    """Status check present -> no finding, missing -> critical."""

    def test_no_status_check_is_critical(self, tmp_repo: Path):
        _write(tmp_repo, "app/pay.py", """\
            from fastapi import APIRouter
            router = APIRouter()

            @router.post("/api/v1/charge")
            async def charge(amount: int, idempotency_key: str):
                with transaction.atomic():
                    gateway.charge(amount)
        """)
        auditor = IdempotencyAuditor(cwd=str(tmp_repo))
        findings = auditor.audit()
        double_crit = [f for f in findings if f.severity == "critical" and "double-charge" in f.issue.lower()]
        assert len(double_crit) >= 1

    def test_status_check_present(self, tmp_repo: Path):
        _write(tmp_repo, "app/pay.py", """\
            from fastapi import APIRouter
            router = APIRouter()

            @router.post("/api/v1/charge")
            async def charge(amount: int, idempotency_key: str):
                with transaction.atomic():
                    if order.status == "PENDING":
                        gateway.charge(amount)
                        order.status = "CHARGED"
                        order.save()
        """)
        auditor = IdempotencyAuditor(cwd=str(tmp_repo))
        findings = auditor.audit()
        double_crit = [f for f in findings if f.severity == "critical" and "double-charge" in f.issue.lower()]
        assert len(double_crit) == 0

    def test_optimistic_lock_present(self, tmp_repo: Path):
        _write(tmp_repo, "app/pay.py", """\
            from fastapi import APIRouter
            router = APIRouter()

            @router.post("/api/v1/charge")
            async def charge(amount: int, idempotency_key: str):
                with transaction.atomic():
                    lock_version = order.version
                    gateway.charge(amount)
        """)
        auditor = IdempotencyAuditor(cwd=str(tmp_repo))
        findings = auditor.audit()
        double_crit = [f for f in findings if f.severity == "critical" and "double-charge" in f.issue.lower()]
        assert len(double_crit) == 0


# ---------------------------------------------------------------------------
# TestFullAudit
# ---------------------------------------------------------------------------

class TestFullAudit:
    """End-to-end with sample payment code."""

    def test_full_audit_mixed(self, tmp_repo: Path):
        _write(tmp_repo, "services/payment.py", """\
            from fastapi import APIRouter
            router = APIRouter()

            @router.post("/api/v1/pay")
            async def pay(amount: int):
                # No idempotency key
                # No transaction
                # No status check
                db.execute("INSERT INTO payments (amount) VALUES (%s)", [amount])
                return {"ok": True}
        """)
        _write(tmp_repo, "services/refund.py", """\
            from fastapi import APIRouter, Header
            from django.db import transaction
            router = APIRouter()

            @router.post("/api/v1/refund")
            async def refund(
                order_id: str,
                x_idempotency_key: str = Header(alias="X-Idempotency-Key"),
            ):
                with transaction.atomic():
                    order = Order.get(order_id)
                    if order.status == "CHARGED":
                        order.status = "REFUNDED"
                        order.version = order.version + 1
                        order.save()
        """)
        auditor = IdempotencyAuditor(cwd=str(tmp_repo))
        findings = auditor.audit()

        # pay endpoint should have critical findings
        pay_critical = [f for f in findings if "pay" in f.endpoint and f.severity == "critical"]
        assert len(pay_critical) >= 1

        # refund endpoint should have no critical findings
        refund_critical = [f for f in findings if "refund" in f.endpoint and f.severity == "critical"]
        assert len(refund_critical) == 0

    def test_empty_repo_no_findings(self, tmp_repo: Path):
        auditor = IdempotencyAuditor(cwd=str(tmp_repo))
        findings = auditor.audit()
        assert findings == []


# ---------------------------------------------------------------------------
# TestFormatReport
# ---------------------------------------------------------------------------

class TestFormatReport:
    """Verify output sections."""

    def test_empty_findings(self):
        report = format_idempotency_report([])
        assert "No idempotency issues" in report

    def test_grouped_by_severity(self):
        findings = [
            IdempotencyFinding(
                file="pay.py", line=10, endpoint="/pay",
                issue="No idempotency key", severity="critical",
                suggestion="Add key",
            ),
            IdempotencyFinding(
                file="pay.py", line=10, endpoint="/pay",
                issue="No transaction", severity="warning",
                suggestion="Add transaction",
            ),
            IdempotencyFinding(
                file="refund.py", line=5, endpoint="/refund",
                issue="Key present", severity="info",
                suggestion="Looks good",
            ),
        ]
        report = format_idempotency_report(findings)
        assert "CRITICAL" in report
        assert "WARNING" in report
        assert "INFO" in report
        assert "3 finding(s)" in report
        assert "Critical: 1" in report
        assert "Warning: 1" in report
        assert "Info: 1" in report

    def test_report_contains_file_and_suggestion(self):
        findings = [
            IdempotencyFinding(
                file="services/pay.py", line=42, endpoint="/api/charge",
                issue="Missing key", severity="critical",
                suggestion="Use X-Idempotency-Key header",
            ),
        ]
        report = format_idempotency_report(findings)
        assert "services/pay.py:42" in report
        assert "/api/charge" in report
        assert "Missing key" in report
        assert "X-Idempotency-Key" in report
