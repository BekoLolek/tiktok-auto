"""Health check utilities for all services."""

import os
from datetime import datetime
from typing import Any

import redis
from sqlalchemy import text

from shared.python.db import engine


def check_database() -> dict[str, Any]:
    """Check PostgreSQL database connectivity."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "healthy", "latency_ms": 0}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


def check_redis() -> dict[str, Any]:
    """Check Redis connectivity."""
    try:
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        r = redis.Redis(host=redis_host, port=redis_port, socket_timeout=5)
        r.ping()
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


def check_elasticsearch() -> dict[str, Any]:
    """Check Elasticsearch connectivity."""
    try:
        from elasticsearch import Elasticsearch

        es_host = os.getenv("ELASTICSEARCH_HOST", "localhost")
        es_port = os.getenv("ELASTICSEARCH_PORT", "9200")
        es = Elasticsearch([f"http://{es_host}:{es_port}"])
        if es.ping():
            return {"status": "healthy"}
        return {"status": "unhealthy", "error": "Ping failed"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


def get_health_status(
    service_name: str,
    version: str = "1.0.0",
    checks: list[str] | None = None,
) -> dict[str, Any]:
    """
    Get comprehensive health status for a service.

    Args:
        service_name: Name of the service
        version: Service version
        checks: List of checks to perform ('database', 'redis', 'elasticsearch')

    Returns:
        Health status dictionary
    """
    checks = checks or ["database", "redis"]

    status = {
        "service": service_name,
        "version": version,
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "checks": {},
    }

    check_functions = {
        "database": check_database,
        "redis": check_redis,
        "elasticsearch": check_elasticsearch,
    }

    for check_name in checks:
        if check_name in check_functions:
            result = check_functions[check_name]()
            status["checks"][check_name] = result
            if result["status"] != "healthy":
                status["status"] = "degraded"

    return status


def create_health_endpoints(app: Any, service_name: str, version: str = "1.0.0") -> None:
    """
    Add health check endpoints to a FastAPI app.

    Args:
        app: FastAPI application instance
        service_name: Name of the service
        version: Service version
    """
    from fastapi import Response

    from .metrics import metrics

    @app.get("/health")
    async def health():
        """Basic health check endpoint."""
        return get_health_status(service_name, version)

    @app.get("/health/live")
    async def liveness():
        """Kubernetes liveness probe."""
        return {"status": "ok"}

    @app.get("/health/ready")
    async def readiness():
        """Kubernetes readiness probe."""
        status = get_health_status(service_name, version)
        if status["status"] == "healthy":
            return {"status": "ready"}
        return Response(status_code=503, content='{"status": "not ready"}')

    @app.get("/metrics")
    async def prometheus_metrics():
        """Prometheus metrics endpoint."""
        if metrics:
            return Response(
                content=metrics.get_metrics(),
                media_type="text/plain; version=0.0.4; charset=utf-8",
            )
        return Response(content=b"", media_type="text/plain")
