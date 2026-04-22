#!/usr/bin/env python3
"""
Query the acq order table via Redash.

Discovers data sources, finds acq_order tables (including sharded variants),
fetches schema, and runs a sample SELECT query.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

from code_agents.integrations.redash_client import RedashClient, RedashError


def main():
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

    # 1. List data sources
    print("=" * 60)
    print("Step 1: Listing data sources...")
    try:
        sources = client.list_data_sources()
    except RedashError as e:
        print(f"Failed: {e}")
        sys.exit(1)

    # Prefer acq-related data sources
    acq_sources = [s for s in sources if "acq" in s.get("name", "").lower()]
    candidates = acq_sources if acq_sources else sources

    print(f"Found {len(sources)} data source(s)")
    for s in candidates[:10]:
        print(f"  id={s['id']}  name={s.get('name')!r}  type={s.get('type')!r}")
    if len(candidates) > 10:
        print(f"  ... and {len(candidates) - 10} more")

    # 2. Find acq_order table(s) in schema
    print()
    print("=" * 60)
    print("Step 2: Finding acq_order table(s) in schema...")

    table_found = None
    ds_id = None
    ds_name = None

    for src in candidates:
        sid = src["id"]
        sname = src.get("name", "?")
        try:
            schema = client.get_schema(sid)
        except RedashError as e:
            print(f"  Skipping {sname}: {e}")
            continue

        for t in schema:
            tname = t.get("name", "")
            if "acq_order" in tname.lower():
                table_found = tname
                ds_id = sid
                ds_name = sname
                cols = t.get("columns", [])
                col_names = [c.get("name", c) if isinstance(c, dict) else c for c in cols]
                print(f"  Found: {tname} in data source id={sid} ({sname})")
                print(f"  Columns: {col_names[:15]}{'...' if len(col_names) > 15 else ''}")
                break

        if table_found:
            break

    if not table_found:
        print("  No acq_order table found. Listing first 20 tables from first acq data source:")
        if candidates:
            sid = candidates[0]["id"]
            sname = candidates[0].get("name", "?")
            try:
                schema = client.get_schema(sid)
                for t in schema[:20]:
                    print(f"    {t.get('name')}")
            except RedashError as e:
                print(f"    Error: {e}")
        sys.exit(1)

    # 3. Run sample query
    print()
    print("=" * 60)
    print(f"Step 3: Running query on {table_found} (data_source_id={ds_id})...")

    query = f"SELECT * FROM `{table_found}` ORDER BY created_at DESC LIMIT 100"
    print(f"  SQL: {query}")
    print()

    try:
        result = client.run_query(data_source_id=ds_id, query=query)
    except RedashError as e:
        # Try without created_at in case column name differs
        query_alt = f"SELECT * FROM `{table_found}` LIMIT 100"
        print(f"  First attempt failed: {e}")
        print(f"  Retrying: {query_alt}")
        try:
            result = client.run_query(data_source_id=ds_id, query=query_alt)
        except RedashError as e2:
            print(f"  Failed: {e2}")
            sys.exit(1)

    columns = result.get("columns", [])
    rows = result.get("rows", [])
    meta = result.get("metadata", {})

    col_names = [c.get("name", c) if isinstance(c, dict) else c for c in columns]
    print(f"  Columns: {col_names}")
    print(f"  Rows: {len(rows)}")
    print(f"  Runtime: {meta.get('runtime')}s")
    print()

    if rows:
        print("Sample results (first 5 rows):")
        print("-" * 80)
        for i, row in enumerate(rows[:5]):
            print(f"  Row {i + 1}: {row}")
    else:
        print("No rows returned.")


if __name__ == "__main__":
    main()
