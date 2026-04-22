#!/usr/bin/env python3
"""Quick smoke test for the Redash API client — validates connectivity and basic operations."""

import os
import sys

# Ensure project root is importable
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

    print(f"Connecting to Redash: {base_url}")
    auth_method = "API key" if api_key else f"username ({username})"
    print(f"Auth method: {auth_method}")

    try:
        client = RedashClient(
            base_url=base_url,
            api_key=api_key,
            username=username,
            password=password,
        )
        print("Login successful!\n")
    except RedashError as e:
        print(f"Login FAILED: {e}")
        sys.exit(1)

    # Step 1: List data sources
    print("=" * 60)
    print("Step 1: Listing data sources...")
    try:
        sources = client.list_data_sources()
        print(f"Found {len(sources)} data source(s):\n")
        for src in sources:
            print(f"  id={src.get('id')}  name={src.get('name')!r}  type={src.get('type')!r}")
        print()
    except RedashError as e:
        print(f"Failed to list data sources: {e}")
        sys.exit(1)

    if not sources:
        print("No data sources found. Cannot run test query.")
        sys.exit(0)

    # Step 2: Run a simple test query on the first data source
    ds_id = sources[0]["id"]
    ds_name = sources[0].get("name", "unknown")
    ds_type = sources[0].get("type", "unknown")

    # Pick a safe test query based on data source type
    if ds_type in ("pg", "redshift"):
        test_query = "SELECT current_database(), current_user, now() AS server_time"
    elif ds_type == "mysql":
        test_query = "SELECT DATABASE() AS db, USER() AS user, NOW() AS server_time"
    elif ds_type == "sqlite":
        test_query = "SELECT sqlite_version() AS version, datetime('now') AS server_time"
    else:
        test_query = "SELECT 1 AS test"

    print("=" * 60)
    print(f"Step 2: Running test query on data source id={ds_id} ({ds_name!r}, type={ds_type!r})")
    print(f"  Query: {test_query}")
    print()

    try:
        result = client.run_query(data_source_id=ds_id, query=test_query)
        print(f"Query succeeded!")
        print(f"  Columns: {[c.get('name') for c in result.get('columns', [])]}")
        print(f"  Rows: {result.get('rows', [])}")
        print(f"  Runtime: {result.get('metadata', {}).get('runtime')}s")
        print(f"  Row count: {result.get('metadata', {}).get('row_count')}")
    except RedashError as e:
        print(f"Query FAILED: {e}")
        if e.status_code:
            print(f"  HTTP status: {e.status_code}")
        if e.response_text:
            print(f"  Response: {e.response_text[:300]}")
        sys.exit(1)

    # Step 3: Fetch schema for the data source
    print()
    print("=" * 60)
    print(f"Step 3: Fetching schema for data source id={ds_id}...")
    try:
        r = client._request("GET", f"/api/data_sources/{ds_id}/schema")
        if r.status_code == 200:
            schema = r.json()
            tables = schema.get("schema", [])
            print(f"  Found {len(tables)} table(s)")
            for t in tables[:10]:
                tname = t.get("name", "?")
                cols = [c.get("name", "?") for c in t.get("columns", [])]
                print(f"    {tname}: {cols[:5]}{'...' if len(cols) > 5 else ''}")
            if len(tables) > 10:
                print(f"    ... and {len(tables) - 10} more tables")
        else:
            print(f"  Schema fetch returned HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"  Schema fetch error: {e}")

    print()
    print("=" * 60)
    print("All checks passed! Redash API is working.")


if __name__ == "__main__":
    main()
