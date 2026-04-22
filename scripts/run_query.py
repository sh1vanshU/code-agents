#!/usr/bin/env python3
"""Run a single SQL query via Redash. Usage: python scripts/run_query.py "SELECT * FROM acq_order_0 LIMIT 1" """

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

from code_agents.integrations.redash_client import RedashClient, RedashError


def main():
    if len(sys.argv) < 2:
        print("Usage: python run_query.py \"<SQL query>\"")
        sys.exit(1)

    query = sys.argv[1].strip()
    if not query.upper().startswith("SELECT"):
        print("Only SELECT queries are allowed.")
        sys.exit(1)

    base_url = os.getenv("REDASH_BASE_URL")
    api_key = os.getenv("REDASH_API_KEY")
    username = os.getenv("REDASH_USERNAME")
    password = os.getenv("REDASH_PASSWORD")

    if not base_url:
        print("REDASH_BASE_URL not set in .env")
        sys.exit(1)

    if not api_key and not (username and password):
        print("Set either REDASH_API_KEY or both REDASH_USERNAME and REDASH_PASSWORD in .env")
        sys.exit(1)

    try:
        client = RedashClient(
            base_url=base_url,
            api_key=api_key,
            username=username,
            password=password,
        )
    except RedashError as e:
        print(f"Redash connection failed: {e}")
        sys.exit(1)

    # Extract table name from query for schema lookup (e.g. acq_order_0 from "SELECT * FROM acq_order_0 ...")
    table_hint = None
    for tok in ["FROM", "from"]:
        if tok in query:
            parts = query.split(tok, 1)[1].strip().split()
            if parts:
                t = parts[0].strip("`\"'")
                if t and t != "*":
                    table_hint = t
                    break

    sources = client.list_data_sources()
    acq_sources = [s for s in sources if "acq" in s.get("name", "").lower()]
    candidates = acq_sources if acq_sources else sources

    ds_id = None
    for src in candidates:
        sid = src["id"]
        sname = src.get("name", "?")
        try:
            schema = client.get_schema(sid)
        except RedashError:
            continue
        for t in schema:
            tname = t.get("name", "")
            if table_hint and table_hint.lower() in tname.lower():
                ds_id = sid
                break
            if not table_hint and "acq_order" in tname.lower():
                ds_id = sid
                break
        if ds_id:
            break

    if not ds_id and candidates:
        ds_id = candidates[0]["id"]

    if not ds_id:
        print("No suitable data source found.")
        sys.exit(1)

    print(f"SQL: {query}")
    print(f"Data source ID: {ds_id}")
    print()

    try:
        result = client.run_query(data_source_id=ds_id, query=query)
    except RedashError as e:
        print(f"Query failed: {e}")
        sys.exit(1)

    columns = result.get("columns", [])
    rows = result.get("rows", [])
    meta = result.get("metadata", {})

    col_names = [c.get("name", c) if isinstance(c, dict) else c for c in columns]
    print("Columns:", col_names)
    print("Rows:", len(rows))
    if meta.get("runtime"):
        print("Runtime:", meta.get("runtime"), "s")
    print()
    if rows:
        for i, row in enumerate(rows):
            print(f"  {i + 1}: {row}")
    else:
        print("No rows returned.")


if __name__ == "__main__":
    main()
