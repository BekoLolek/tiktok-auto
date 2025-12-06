"""Log service for Elasticsearch integration."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from elasticsearch import Elasticsearch

logger = logging.getLogger(__name__)


class LogService:
    """Service for querying logs from Elasticsearch."""

    def __init__(self, es_url: str):
        """Initialize log service with Elasticsearch URL."""
        self.es_url = es_url
        self._client: Elasticsearch | None = None

    @property
    def client(self) -> Elasticsearch:
        """Lazy-load Elasticsearch client."""
        if self._client is None:
            self._client = Elasticsearch([self.es_url])
        return self._client

    async def search_logs(
        self,
        service: str | None = None,
        level: str | None = None,
        story_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        """Search logs with filters.

        Returns:
            Tuple of (logs list, total count)
        """
        # Build query
        must_conditions = []

        if service:
            must_conditions.append({"term": {"service": service}})

        if level:
            must_conditions.append({"term": {"level": level}})

        if story_id:
            must_conditions.append({"term": {"story_id": story_id}})

        # Time range
        time_range = {}
        if start_time:
            time_range["gte"] = start_time.isoformat()
        if end_time:
            time_range["lte"] = end_time.isoformat()
        if time_range:
            must_conditions.append({"range": {"@timestamp": time_range}})

        # Build full query
        query: dict[str, Any] = {"bool": {"must": must_conditions}} if must_conditions else {"match_all": {}}

        try:
            # Search across all tiktok-auto indices
            response = self.client.search(
                index="tiktok-auto-*",
                query=query,
                sort=[{"@timestamp": {"order": "desc"}}],
                from_=(page - 1) * per_page,
                size=per_page,
            )

            logs = []
            for hit in response["hits"]["hits"]:
                log_entry = hit["_source"]
                log_entry["_id"] = hit["_id"]
                log_entry["_index"] = hit["_index"]
                logs.append(log_entry)

            total = response["hits"]["total"]["value"]

            return logs, total

        except Exception as e:
            logger.error(f"Elasticsearch query failed: {e}")
            return [], 0

    async def get_log_by_id(self, index: str, log_id: str) -> dict[str, Any] | None:
        """Get a specific log entry by ID."""
        try:
            response = self.client.get(index=index, id=log_id)
            return response["_source"]
        except Exception as e:
            logger.error(f"Failed to get log {log_id}: {e}")
            return None

    async def get_story_logs(
        self, story_id: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get all logs related to a specific story."""
        logs, _ = await self.search_logs(story_id=story_id, per_page=limit)
        return logs

    def health_check(self) -> bool:
        """Check if Elasticsearch is available."""
        try:
            return self.client.ping()
        except Exception:
            return False
