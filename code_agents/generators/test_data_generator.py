"""Domain-specific test data generation.

Generates realistic test data for payments, users, merchants, APIs, and more.
Detects project domain from file names and generates appropriate fixtures.
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import string
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("code_agents.generators.test_data_generator")


# ---------------------------------------------------------------------------
# Domain data generators
# ---------------------------------------------------------------------------

def _random_string(length: int = 8) -> str:
    return "".join(random.choices(string.ascii_lowercase, k=length))


def _random_amount() -> float:
    return round(random.uniform(1.0, 9999.99), 2)


def _random_phone() -> str:
    return f"+91{random.randint(7000000000, 9999999999)}"


def _random_email(name: str = "") -> str:
    if not name:
        name = _random_string(6)
    domains = ["example.com", "test.org", "mail.test"]
    return f"{name.lower().replace(' ', '.')}@{random.choice(domains)}"


def _random_timestamp() -> str:
    offset = random.randint(0, 86400 * 30)
    dt = datetime.utcnow() - timedelta(seconds=offset)
    return dt.isoformat() + "Z"


def _random_date() -> str:
    offset = random.randint(0, 365)
    dt = datetime.utcnow() - timedelta(days=offset)
    return dt.strftime("%Y-%m-%d")


DOMAIN_DATA: dict[str, dict[str, Callable[[], Any]]] = {
    "payment": {
        "amount": _random_amount,
        "currency": lambda: random.choice(["INR", "USD", "EUR", "GBP"]),
        "merchant_id": lambda: f"MID{random.randint(100000, 999999)}",
        "status": lambda: random.choice(["SUCCESS", "FAILED", "PENDING", "REFUNDED"]),
        "transaction_id": lambda: f"TXN{uuid.uuid4().hex[:12].upper()}",
        "payment_method": lambda: random.choice(["UPI", "CARD", "WALLET", "NET_BANKING"]),
        "order_id": lambda: f"ORD{random.randint(100000, 999999)}",
    },
    "user": {
        "name": lambda: random.choice(["Rahul Sharma", "Priya Patel", "Amit Kumar", "Sneha Gupta", "Vikram Singh"]),
        "email": lambda: _random_email(_random_string(6)),
        "phone": _random_phone,
        "user_id": lambda: f"USR{random.randint(10000, 99999)}",
        "role": lambda: random.choice(["customer", "admin", "merchant", "support"]),
    },
    "merchant": {
        "merchant_id": lambda: f"MID{random.randint(100000, 999999)}",
        "merchant_name": lambda: random.choice(["QuickMart", "FreshBasket", "TechStore", "BookHub"]),
        "category": lambda: random.choice(["retail", "food", "electronics", "services"]),
        "settlement_status": lambda: random.choice(["SETTLED", "PENDING", "HOLD"]),
        "kyc_status": lambda: random.choice(["VERIFIED", "PENDING", "REJECTED"]),
    },
    "api": {
        "request_id": lambda: str(uuid.uuid4()),
        "timestamp": _random_timestamp,
        "method": lambda: random.choice(["GET", "POST", "PUT", "DELETE"]),
        "status_code": lambda: random.choice([200, 201, 400, 401, 404, 500]),
        "endpoint": lambda: random.choice(["/api/v1/users", "/api/v1/payments", "/api/v1/orders"]),
        "response_time_ms": lambda: random.randint(5, 2000),
    },
    "date": {
        "date": _random_date,
        "timestamp": _random_timestamp,
        "created_at": _random_timestamp,
        "updated_at": _random_timestamp,
        "start_date": _random_date,
        "end_date": _random_date,
    },
}


# File name patterns that hint at domain
_DOMAIN_FILE_PATTERNS: dict[str, list[str]] = {
    "payment": ["payment", "transaction", "checkout", "billing", "invoice", "refund", "settlement"],
    "user": ["user", "auth", "login", "signup", "registration", "profile", "account"],
    "merchant": ["merchant", "vendor", "seller", "store", "shop", "kyc"],
    "api": ["controller", "router", "endpoint", "handler", "api", "rest", "grpc"],
    "date": ["schedule", "calendar", "booking", "event", "cron"],
}


class TestDataGenerator:
    """Generate domain-specific test data."""

    def __init__(self, repo_path: str = "."):
        self.repo_path = repo_path

    def detect_domain(self) -> list[str]:
        """Detect project domains from file names.

        Returns:
            List of detected domain names (e.g. ["payment", "user"]).
        """
        detected = set()
        repo = Path(self.repo_path)

        try:
            for ext in ("*.py", "*.java", "*.ts", "*.js", "*.go"):
                for f in repo.rglob(ext):
                    name_lower = f.stem.lower()
                    for domain, patterns in _DOMAIN_FILE_PATTERNS.items():
                        for pattern in patterns:
                            if pattern in name_lower:
                                detected.add(domain)
        except Exception:
            pass

        return sorted(detected) if detected else ["api"]

    def generate(self, domains: list[str] | None = None, count: int = 5) -> list[dict[str, Any]]:
        """Generate N records with fields from the specified domains.

        Args:
            domains: List of domain names. Auto-detected if None.
            count: Number of records to generate.

        Returns:
            List of dicts with generated fields.
        """
        if domains is None:
            domains = self.detect_domain()

        # Merge all fields from requested domains
        generators: dict[str, Callable[[], Any]] = {}
        for domain in domains:
            domain_gens = DOMAIN_DATA.get(domain, {})
            generators.update(domain_gens)

        if not generators:
            return []

        records = []
        for _ in range(count):
            record = {field_name: gen() for field_name, gen in generators.items()}
            records.append(record)

        return records

    def generate_for_class(self, filepath: str) -> list[dict[str, Any]]:
        """Generate test data by matching class fields to domain generators.

        Args:
            filepath: Path to source file.

        Returns:
            List of dicts with matching field data.
        """
        full_path = os.path.join(self.repo_path, filepath) if not os.path.isabs(filepath) else filepath
        if not os.path.exists(full_path):
            return []

        try:
            content = Path(full_path).read_text()
        except Exception:
            return []

        # Extract field names (Python: self.field, Java: Type field)
        field_names = set()
        # Python fields
        for m in re.finditer(r"self\.(\w+)\s*=", content):
            field_names.add(m.group(1).lower())
        # Java/TypeScript fields
        for m in re.finditer(r"(?:private|public|protected)?\s+\w+\s+(\w+)\s*[;=]", content):
            field_names.add(m.group(1).lower())

        if not field_names:
            return []

        # Match fields to generators
        generators: dict[str, Callable[[], Any]] = {}
        for domain, gens in DOMAIN_DATA.items():
            for gen_name, gen_func in gens.items():
                normalized = gen_name.lower().replace("_", "")
                for field_name in field_names:
                    normalized_field = field_name.replace("_", "")
                    if normalized in normalized_field or normalized_field in normalized:
                        generators[gen_name] = gen_func

        if not generators:
            return []

        records = []
        for _ in range(5):
            record = {name: gen() for name, gen in generators.items()}
            records.append(record)

        return records


def format_test_data(records: list[dict[str, Any]], language: str = "json") -> str:
    """Format generated test data for display.

    Args:
        records: List of generated records.
        language: Output format: json, java, python.

    Returns:
        Formatted string.
    """
    if not records:
        return "  No test data generated."

    if language == "json":
        return json.dumps(records, indent=2)

    elif language == "python":
        lines = ["test_data = ["]
        for record in records:
            lines.append("    {")
            for key, value in record.items():
                lines.append(f"        {key!r}: {value!r},")
            lines.append("    },")
        lines.append("]")
        return "\n".join(lines)

    elif language == "java":
        lines = []
        for i, record in enumerate(records):
            lines.append(f"// Record {i + 1}")
            for key, value in record.items():
                camel = re.sub(r"_(\w)", lambda m: m.group(1).upper(), key)
                if isinstance(value, str):
                    lines.append(f'String {camel} = "{value}";')
                elif isinstance(value, (int, float)):
                    type_name = "double" if isinstance(value, float) else "int"
                    lines.append(f"{type_name} {camel} = {value};")
            lines.append("")
        return "\n".join(lines)

    return json.dumps(records, indent=2)
