"""Alexandrie REST API client — HOS-053B production.

Full production client with:
- Configurable authentication (Bearer token / API key)
- Retry with exponential backoff
- Connection + read timeouts
- Health monitoring
- Incremental sync support (since timestamp)
"""

from __future__ import annotations

import hashlib
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

_REQUESTS_AVAILABLE = False
try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    _REQUESTS_AVAILABLE = True
except ImportError:
    requests = None  # type: ignore[assignment]

from backend.integrations.alexandrie.alexandrie_models import (
    AlexandrieConfig,
    AlexandrieNode,
    AlexandrieNodeType,
    AlexandrieSearchResult,
)


class AlexandrieClient:
    """Production HTTP client for Alexandrie's REST API.

    Features:
    - Authentication: Bearer token via config
    - Retry: exponential backoff on 429/5xx
    - Timeout: connection (5s) + read (30s) configurable
    - Health: periodic health_check with status
    - Incremental: sync since a timestamp
    """

    def __init__(self, config: Optional[AlexandrieConfig] = None) -> None:
        self.config = config or AlexandrieConfig()
        self._session = self._build_session() if _REQUESTS_AVAILABLE else None
        # Separate session for health probes, deliberately without the retry
        # adapter: retrying a reachability check 4 times with exponential
        # backoff made health_check() take ~22s whenever Alexandrie was down
        # (3 retries x backoff 1/2/4s + 5s connect each). A health check's job
        # is to answer *quickly* whether the service is up, its result is
        # already cached for health_check_interval_seconds, and a negative
        # answer is already handled by callers.
        self._health_session = self._build_session(with_retries=False) if _REQUESTS_AVAILABLE else None
        self._lock = threading.Lock()
        self._last_health: Optional[dict[str, Any]] = None
        self._health_at: float = 0.0

    def _build_session(self, with_retries: bool = True):
        if not _REQUESTS_AVAILABLE:
            return None
        session = requests.Session()
        retry = Retry(
            total=self.config.max_retries if with_retries else 0,
            backoff_factor=self.config.retry_backoff_base if with_retries else 0,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Authentication
        if self.config.api_key:
            hdr = self.config.auth_header
            prefix = self.config.auth_prefix
            session.headers[hdr] = f"{prefix} {self.config.api_key}" if prefix else self.config.api_key

        session.headers["Content-Type"] = "application/json"
        session.headers["User-Agent"] = "HermesOS-Alexandrie-Adapter/2.0"
        return session

    @property
    def _base(self) -> str:
        return f"{self.config.base_url.rstrip('/')}{self.config.api_path}"

    # ── Health ──────────────────────────────────────────────────────

    def health_check(self, force: bool = False) -> dict[str, Any]:
        """Check Alexandrie health with caching."""
        now = time.monotonic()
        if not force and self._last_health and (now - self._health_at) < self.config.health_check_interval_seconds:
            return self._last_health

        if not self._health_session:
            result = {"healthy": False, "error": "requests library not installed"}
            self._last_health = result
            self._health_at = now
            return result

        try:
            resp = self._health_session.get(
                f"{self.config.base_url.rstrip('/')}/api/stats",
                timeout=(self.config.connect_timeout, self.config.timeout_seconds),
            )
            if resp.status_code == 200:
                result = {"healthy": True, "data": resp.json(), "latency_ms": (time.monotonic() - now) * 1000}
            else:
                result = {"healthy": False, "error": f"HTTP {resp.status_code}", "body": resp.text[:200]}
        except Exception as e:
            result = {"healthy": False, "error": str(e), "error_type": type(e).__name__}

        self._last_health = result
        self._health_at = time.monotonic()
        return result

    def is_healthy(self) -> bool:
        return self.health_check().get("healthy", False)

    # ── Search ──────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        include_content: bool = False,
        limit: int = 20,
        since: Optional[datetime] = None,
    ) -> AlexandrieSearchResult:
        """Full-text search with optional incremental filter."""
        if len(query) < 2:
            return AlexandrieSearchResult(query=query)

        start = time.perf_counter()
        if not self._session:
            return AlexandrieSearchResult(query=query)

        try:
            params: dict[str, Any] = {
                "q": query,
                "content": str(include_content).lower(),
                "limit": min(limit, 100),
            }
            if since:
                params["since"] = since.isoformat()

            resp = self._session.get(
                f"{self._base}/nodes/search",
                params=params,
                timeout=(self.config.connect_timeout, self.config.timeout_seconds),
            )
            elapsed = (time.perf_counter() - start) * 1000

            if resp.status_code == 200:
                data = resp.json()
                nodes = self._parse_node_list(data) if isinstance(data, list) else self._parse_node_list(data.get("results", data.get("nodes", [])))
                for n in nodes:
                    n.search_relevance = 1.0
                return AlexandrieSearchResult(query=query, nodes=nodes, total=len(nodes), took_ms=elapsed)

            return AlexandrieSearchResult(query=query)
        except Exception:
            return AlexandrieSearchResult(query=query)

    # ── CRUD ────────────────────────────────────────────────────────

    def get_node(self, node_id: str) -> Optional[AlexandrieNode]:
        if not self._session:
            return None
        try:
            resp = self._session.get(
                f"{self._base}/nodes/{node_id}",
                timeout=(self.config.connect_timeout, self.config.timeout_seconds),
            )
            if resp.status_code == 200:
                return self._parse_node(resp.json())
            return None
        except Exception:
            return None

    def list_nodes(self, user_id: str, since: Optional[datetime] = None) -> list[AlexandrieNode]:
        if not self._session:
            return []
        try:
            params: dict[str, Any] = {}
            if since:
                params["since"] = since.isoformat()
            resp = self._session.get(
                f"{self._base}/nodes/user/{user_id}",
                params=params,
                timeout=(self.config.connect_timeout, self.config.timeout_seconds),
            )
            if resp.status_code == 200:
                return self._parse_node_list(resp.json())
            return []
        except Exception:
            return []

    def create_node(self, node: AlexandrieNode) -> Optional[AlexandrieNode]:
        if not self._session:
            return None
        try:
            payload = {
                "title": node.title,
                "content": node.content,
                "type": node.node_type.value,
                "parent_id": node.parent_id,
                "is_public": node.is_public,
                "tags": node.tags,
            }
            resp = self._session.post(
                f"{self._base}/nodes",
                json=payload,
                timeout=(self.config.connect_timeout, self.config.timeout_seconds),
            )
            if resp.status_code in (200, 201):
                return self._parse_node(resp.json())
            return None
        except Exception:
            return None

    def update_node(self, node_id: str, node: AlexandrieNode) -> Optional[AlexandrieNode]:
        if not self._session:
            return None
        try:
            payload = {
                "title": node.title,
                "content": node.content,
                "is_public": node.is_public,
                "tags": node.tags,
            }
            resp = self._session.put(
                f"{self._base}/nodes/{node_id}",
                json=payload,
                timeout=(self.config.connect_timeout, self.config.timeout_seconds),
            )
            if resp.status_code == 200:
                return self._parse_node(resp.json())
            return None
        except Exception:
            return None

    def delete_node(self, node_id: str) -> bool:
        if not self._session:
            return False
        try:
            resp = self._session.delete(
                f"{self._base}/nodes/{node_id}",
                timeout=(self.config.connect_timeout, self.config.timeout_seconds),
            )
            return resp.status_code in (200, 204)
        except Exception:
            return False

    # ── Parsing ─────────────────────────────────────────────────────

    def _parse_node(self, data: dict[str, Any]) -> AlexandrieNode:
        return AlexandrieNode(
            id=str(data.get("id", data.get("ID", ""))),
            title=str(data.get("title", data.get("Title", ""))),
            content=str(data.get("content", data.get("Content", ""))),
            node_type=AlexandrieNodeType(data.get("type", data.get("Type", "document")).lower()),
            parent_id=data.get("parent_id") or data.get("ParentID"),
            owner_id=str(data.get("owner_id", data.get("ownerId", data.get("OwnerID", "")))),
            is_public=bool(data.get("is_public", data.get("IsPublic", False))),
            tags=data.get("tags", data.get("Tags", [])),
            version=int(data.get("version", data.get("Version", 1))),
            created_at=self._parse_time(data.get("created_at", data.get("CreatedAt"))),
            updated_at=self._parse_time(data.get("updated_at", data.get("UpdatedAt"))),
        )

    def _parse_node_list(self, data: Any) -> list[AlexandrieNode]:
        if isinstance(data, list):
            return [self._parse_node(n) for n in data if isinstance(n, dict)]
        return []

    @staticmethod
    def _parse_time(val: Any) -> datetime:
        if val is None:
            return datetime.now(timezone.utc)
        if isinstance(val, datetime):
            return val
        try:
            return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return datetime.now(timezone.utc)

    def compute_hash(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
