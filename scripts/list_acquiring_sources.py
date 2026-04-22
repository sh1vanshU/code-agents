#!/usr/bin/env python3
"""List and count acquiring-related Redash data sources."""

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

    try:
        client = RedashClient(
            base_url=base_url,
            api_key=api_key,
            username=username,
            password=password,
        )
    except RedashError as e:
        print(f"Connection failed: {e}")
        sys.exit(1)

    sources = client.list_data_sources()
    acquiring = [s for s in sources if "acquiring" in s.get("name", "").lower()]

    print(f"Total data sources: {len(sources)}")
    print(f"Acquiring-related data sources: {len(acquiring)}")
    print()
    for s in acquiring:
        print(f"  id={s['id']}  name={s.get('name')!r}  type={s.get('type')!r}")


if __name__ == "__main__":
    main()
