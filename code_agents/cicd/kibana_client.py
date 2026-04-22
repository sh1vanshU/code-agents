"""
Kibana log viewer — search application logs by service, time range, log level.

Queries Elasticsearch (behind Kibana) for structured log search.
Config: KIBANA_URL, KIBANA_USERNAME, KIBANA_PASSWORD (or use existing ELASTICSEARCH_* vars)
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional, Any
from datetime import datetime, timedelta

import httpx

logger = logging.getLogger("code_agents.kibana_client")


class KibanaError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class KibanaClient:
    def __init__(
        self,
        kibana_url: str = "",
        username: str = "",
        password: str = "",
        timeout: float = 30.0,
    ):
        self.kibana_url = kibana_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout

    def _client(self) -> httpx.AsyncClient:
        auth = None
        if self.username and self.password:
            auth = (self.username, self.password)
        return httpx.AsyncClient(
            base_url=self.kibana_url,
            auth=auth,
            timeout=self.timeout,
            headers={"kbn-xsrf": "true", "Content-Type": "application/json"},
        )

    async def get_indices(self) -> list[str]:
        """List available index patterns from Kibana."""
        async with self._client() as client:
            # Try Kibana saved objects API for index patterns
            r = await client.get("/api/saved_objects/_find?type=index-pattern&per_page=100")
            if r.status_code == 200:
                data = r.json()
                return [obj.get("attributes", {}).get("title", "") for obj in data.get("saved_objects", [])]
            # Fallback: list ES indices directly
            r = await client.get("/api/console/proxy?path=/_cat/indices&method=GET")
            if r.status_code == 200:
                return [line.split()[2] for line in r.text.strip().splitlines() if len(line.split()) > 2]
            return []

    async def search_logs(
        self,
        index: str = "logs-*",
        query: str = "*",
        service: str = "",
        log_level: str = "",
        time_range: str = "15m",
        size: int = 100,
    ) -> list[dict]:
        """Search logs with filters."""
        logger.info("Kibana log search: index=%s, service=%s, time_range=%s", index, service or "*", time_range)
        # Build time range
        now = datetime.utcnow()
        ranges = {"5m": 5, "15m": 15, "30m": 30, "1h": 60, "3h": 180, "6h": 360, "12h": 720, "24h": 1440}
        minutes = ranges.get(time_range, 15)
        time_from = (now - timedelta(minutes=minutes)).isoformat() + "Z"
        time_to = now.isoformat() + "Z"

        # Build ES query
        must = []
        if query and query != "*":
            must.append({"query_string": {"query": query, "default_field": "message"}})

        filters = [{"range": {"@timestamp": {"gte": time_from, "lte": time_to}}}]

        service_field = os.getenv("KIBANA_SERVICE_FIELD", "kubernetes.labels.app")
        if service:
            filters.append({"term": {service_field: service}})
        if log_level:
            filters.append({"term": {"level": log_level.upper()}})

        body = {
            "query": {"bool": {"must": must or [{"match_all": {}}], "filter": filters}},
            "sort": [{"@timestamp": {"order": "desc"}}],
            "size": size,
            "_source": ["@timestamp", "message", "level", "kubernetes.labels.app", "logger_name", "stack_trace"],
        }

        async with self._client() as client:
            r = await client.post(f"/api/console/proxy?path=/{index}/_search&method=POST", json=body)
            if r.status_code != 200:
                raise KibanaError(f"Search failed: {r.status_code} {r.text[:200]}", r.status_code)
            data = r.json()

        hits = data.get("hits", {}).get("hits", [])
        logger.info("Kibana search returned %d hits", len(hits))
        results = []
        for hit in hits:
            src = hit.get("_source", {})
            results.append({
                "timestamp": src.get("@timestamp", ""),
                "level": src.get("level", ""),
                "message": (src.get("message", ""))[:500],
                "service": src.get("kubernetes", {}).get("labels", {}).get("app", ""),
                "logger": src.get("logger_name", ""),
                "stack_trace": (src.get("stack_trace", ""))[:1000] if src.get("stack_trace") else None,
            })
        return results

    async def error_summary(
        self,
        index: str = "logs-*",
        service: str = "",
        time_range: str = "1h",
        top_n: int = 10,
    ) -> list[dict]:
        """Aggregate top error patterns."""
        now = datetime.utcnow()
        ranges = {"5m": 5, "15m": 15, "30m": 30, "1h": 60, "3h": 180, "6h": 360, "24h": 1440}
        minutes = ranges.get(time_range, 60)
        time_from = (now - timedelta(minutes=minutes)).isoformat() + "Z"

        filters = [
            {"range": {"@timestamp": {"gte": time_from}}},
            {"terms": {"level": ["ERROR", "FATAL", "WARN"]}},
        ]
        service_field = os.getenv("KIBANA_SERVICE_FIELD", "kubernetes.labels.app")
        if service:
            filters.append({"term": {service_field: service}})

        body = {
            "query": {"bool": {"filter": filters}},
            "size": 0,
            "aggs": {
                "error_patterns": {
                    "terms": {"field": "message.keyword", "size": top_n, "order": {"_count": "desc"}},
                }
            },
        }

        async with self._client() as client:
            r = await client.post(f"/api/console/proxy?path=/{index}/_search&method=POST", json=body)
            if r.status_code != 200:
                raise KibanaError(f"Aggregation failed: {r.status_code}", r.status_code)
            data = r.json()

        buckets = data.get("aggregations", {}).get("error_patterns", {}).get("buckets", [])
        return [{"pattern": b["key"][:200], "count": b["doc_count"]} for b in buckets]
