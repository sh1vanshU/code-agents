"""
Elasticsearch client: connect with URL + API key or basic auth (env-driven).
"""

from __future__ import annotations

import os
from typing import Any, Optional

import logging

from elasticsearch import Elasticsearch
from elasticsearch.exceptions import ApiError, TransportError

logger = logging.getLogger("code_agents.integrations.elasticsearch_client")


class ElasticsearchConnError(Exception):
    """Raised when Elasticsearch returns an error or connection fails."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response: Optional[dict[str, Any]] | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


def _truthy(s: str) -> bool:
    return s.strip().lower() in ("1", "true", "yes", "on")


def client_from_env() -> Elasticsearch:
    """
    Build an Elasticsearch client from environment.

    Required:
        ELASTICSEARCH_URL — e.g. https://my-deployment.es.region.cloud.es.io:443
        or comma-separated hosts (first wins for scheme if mixing).

    Optional auth (one of):
        ELASTICSEARCH_API_KEY — Base64-encoded API key (id:api_key encoded)
        ELASTICSEARCH_USERNAME + ELASTICSEARCH_PASSWORD — HTTP basic

    Optional:
        ELASTICSEARCH_CLOUD_ID — Elastic Cloud; if set, URL may be omitted for cloud_id-based connect
        ELASTICSEARCH_CA_CERTS — path to CA bundle for TLS
        ELASTICSEARCH_VERIFY_SSL — set to 0/false to disable cert verification (insecure)
    """
    cloud_id = os.getenv("ELASTICSEARCH_CLOUD_ID", "").strip()
    url = os.getenv("ELASTICSEARCH_URL", "").strip()

    if not cloud_id and not url:
        raise ElasticsearchConnError(
            "Set ELASTICSEARCH_URL (or ELASTICSEARCH_CLOUD_ID for Elastic Cloud).",
        )

    api_key = os.getenv("ELASTICSEARCH_API_KEY", "").strip() or None
    user = os.getenv("ELASTICSEARCH_USERNAME", "").strip()
    password = os.getenv("ELASTICSEARCH_PASSWORD", "").strip()
    basic: tuple[str, str] | None = (user, password) if user and password else None

    if api_key and basic:
        raise ElasticsearchConnError("Use either ELASTICSEARCH_API_KEY or USERNAME/PASSWORD, not both.")

    verify_ssl = _truthy(os.getenv("ELASTICSEARCH_VERIFY_SSL", "1"))
    ca_certs = os.getenv("ELASTICSEARCH_CA_CERTS", "").strip() or None

    kw: dict[str, Any] = {
        "verify_certs": verify_ssl,
        "request_timeout": 30,
    }
    if ca_certs:
        kw["ca_certs"] = ca_certs
    if api_key:
        kw["api_key"] = api_key
    if basic:
        kw["basic_auth"] = basic

    if cloud_id:
        kw["cloud_id"] = cloud_id
        return Elasticsearch(**kw)

    # Single or multiple URLs — client accepts hosts as list of URLs in 8.x
    hosts = [h.strip() for h in url.split(",") if h.strip()]
    if not hosts:
        raise ElasticsearchConnError("ELASTICSEARCH_URL is empty after parsing.")
    return Elasticsearch(hosts, **{k: v for k, v in kw.items() if k != "cloud_id"})


def _as_dict(resp: Any) -> dict[str, Any]:
    body = getattr(resp, "body", None)
    if isinstance(body, dict):
        return body
    if isinstance(resp, dict):
        return resp
    try:
        return dict(resp)
    except TypeError:
        return {"raw": str(resp)}


def info(es: Elasticsearch) -> dict[str, Any]:
    try:
        return _as_dict(es.info())
    except (ApiError, TransportError) as e:
        code = getattr(e, "meta", None)
        status = getattr(code, "status", None) if code is not None else None
        raise ElasticsearchConnError(str(e), status_code=status) from e
    except Exception as e:
        raise ElasticsearchConnError(str(e)) from e


def search(es: Elasticsearch, index: str, body: dict[str, Any]) -> dict[str, Any]:
    """Run search using REST-style ``body`` (``query``, ``size``, ``from``, aggs, …)."""
    try:
        if body:
            out = es.search(index=index, body=body)
        else:
            out = es.search(index=index, query={"match_all": {}})
        return _as_dict(out)
    except (ApiError, TransportError) as e:
        code = getattr(e, "meta", None)
        status = getattr(code, "status", None) if code is not None else None
        raise ElasticsearchConnError(str(e), status_code=status) from e
    except Exception as e:
        raise ElasticsearchConnError(str(e)) from e
