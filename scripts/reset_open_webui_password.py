#!/usr/bin/env python3
"""Reset Open WebUI user password(s) by updating webui.db (bcrypt).

Run via reset-open-webui-password.sh so the same Python env as ``open-webui`` is used.

Stop ``open-webui serve`` before running to avoid SQLite locks / corruption.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys


def _default_db_path() -> str:
    import open_webui

    return os.path.join(os.path.dirname(open_webui.__file__), "data", "webui.db")


def _hash_password(plain: str) -> str:
    import bcrypt

    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")


def main() -> int:
    p = argparse.ArgumentParser(
        description="Set password(s) in Open WebUI webui.db (bcrypt). "
        "Stop open-webui before running."
    )
    p.add_argument(
        "password",
        nargs="?",
        help="New password (or set OPEN_WEBUI_RESET_PASSWORD)",
    )
    p.add_argument(
        "--db-path",
        metavar="PATH",
        help="Path to webui.db (default: next to installed open_webui package)",
    )
    p.add_argument(
        "--email",
        metavar="ADDR",
        help="Only this user; omit to update every row in auth",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print DB path and row count; do not write",
    )
    args = p.parse_args()

    password = args.password or os.environ.get("OPEN_WEBUI_RESET_PASSWORD")
    if not args.dry_run and not password:
        print(
            "error: password required (argument or OPEN_WEBUI_RESET_PASSWORD)",
            file=sys.stderr,
        )
        return 1

    db_path = args.db_path or os.environ.get("OPEN_WEBUI_DB_PATH") or _default_db_path()
    if not os.path.isfile(db_path):
        print(f"error: database not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='auth'")
        if not cur.fetchone():
            print("error: table 'auth' not found in database", file=sys.stderr)
            return 1

        if args.email:
            cur.execute(
                "SELECT COUNT(*) FROM auth WHERE email = ?", (args.email,)
            )
            n = cur.fetchone()[0]
            if n == 0:
                print(f"error: no user with email {args.email!r}", file=sys.stderr)
                return 1
        else:
            cur.execute("SELECT COUNT(*) FROM auth")
            n = cur.fetchone()[0]
            if n == 0:
                print("error: auth table is empty", file=sys.stderr)
                return 1

        if args.dry_run:
            print(f"db: {db_path}")
            print(f"rows to update: {n}" + (f" (email={args.email!r})" if args.email else " (all users)"))
            return 0

        hashed = _hash_password(password)
        if args.email:
            cur.execute(
                "UPDATE auth SET password = ? WHERE email = ?",
                (hashed, args.email),
            )
        else:
            cur.execute("UPDATE auth SET password = ?", (hashed,))
        conn.commit()
        print(f"updated {cur.rowcount} row(s) in {db_path}")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
