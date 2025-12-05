"""Elasticsearch logging handler for centralized logging."""

import logging
import os
import threading
from datetime import datetime
from queue import Empty, Queue
from typing import Any

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk


class ElasticsearchHandler(logging.Handler):
    """
    Logging handler that sends logs to Elasticsearch.

    Features:
    - Buffered writes for better performance
    - Async bulk indexing
    - Automatic index creation with date-based naming
    - Graceful error handling
    """

    def __init__(
        self,
        service_name: str,
        es_host: str | None = None,
        es_port: int | None = None,
        buffer_size: int = 100,
        flush_interval: float = 5.0,
        index_prefix: str = "tiktok-auto",
    ):
        """
        Initialize the Elasticsearch handler.

        Args:
            service_name: Name of the service (e.g., 'text-processor')
            es_host: Elasticsearch host (defaults to env var)
            es_port: Elasticsearch port (defaults to env var)
            buffer_size: Number of logs to buffer before flush
            flush_interval: Seconds between automatic flushes
            index_prefix: Prefix for index names
        """
        super().__init__()

        self.service_name = service_name
        self.index_prefix = index_prefix
        self.buffer_size = buffer_size
        self.flush_interval = flush_interval

        # Elasticsearch connection
        host = es_host or os.getenv("ELASTICSEARCH_HOST", "localhost")
        port = es_port or int(os.getenv("ELASTICSEARCH_PORT", "9200"))

        self.es = Elasticsearch(
            [{"host": host, "port": port, "scheme": "http"}],
            retry_on_timeout=True,
            max_retries=3,
        )

        # Buffer for batching
        self._buffer: Queue[dict[str, Any]] = Queue()
        self._buffer_lock = threading.Lock()

        # Background flush thread
        self._flush_thread = threading.Thread(target=self._flush_worker, daemon=True)
        self._flush_thread.start()

        self._closed = False

    def _get_index_name(self) -> str:
        """Generate index name with current date."""
        date_str = datetime.utcnow().strftime("%Y.%m.%d")
        return f"{self.index_prefix}-{self.service_name}-{date_str}"

    def emit(self, record: logging.LogRecord) -> None:
        """
        Emit a log record to the buffer.

        Args:
            record: The log record to emit
        """
        if self._closed:
            return

        try:
            log_entry = self._format_record(record)
            self._buffer.put(log_entry)

            # Flush if buffer is full
            if self._buffer.qsize() >= self.buffer_size:
                self._flush()

        except Exception:
            self.handleError(record)

    def _format_record(self, record: logging.LogRecord) -> dict[str, Any]:
        """
        Format a log record for Elasticsearch.

        Args:
            record: The log record to format

        Returns:
            Dict ready for indexing
        """
        # Extract extra fields
        extra = {}
        for key, value in record.__dict__.items():
            if key not in (
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "exc_info",
                "exc_text",
                "thread",
                "threadName",
                "message",
            ):
                try:
                    # Only include JSON-serializable values
                    import json

                    json.dumps(value)
                    extra[key] = value
                except (TypeError, ValueError):
                    extra[key] = str(value)

        return {
            "_index": self._get_index_name(),
            "_source": {
                "timestamp": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
                "service": self.service_name,
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
                "process_id": record.process,
                "thread_id": record.thread,
                "extra": extra,
            },
        }

    def _flush(self) -> None:
        """Flush the buffer to Elasticsearch."""
        with self._buffer_lock:
            docs = []
            try:
                while True:
                    docs.append(self._buffer.get_nowait())
            except Empty:
                pass

            if docs:
                try:
                    bulk(self.es, docs, raise_on_error=False, raise_on_exception=False)
                except Exception as e:
                    # Log to stderr if ES is unavailable
                    import sys

                    print(f"Failed to flush logs to Elasticsearch: {e}", file=sys.stderr)

    def _flush_worker(self) -> None:
        """Background worker that flushes periodically."""
        import time

        while not self._closed:
            time.sleep(self.flush_interval)
            if not self._buffer.empty():
                self._flush()

    def close(self) -> None:
        """Close the handler and flush remaining logs."""
        self._closed = True
        self._flush()
        super().close()


def setup_logging(
    service_name: str,
    level: str | None = None,
    enable_elasticsearch: bool = True,
) -> logging.Logger:
    """
    Set up logging for a service.

    Args:
        service_name: Name of the service
        level: Log level (defaults to env var LOG_LEVEL)
        enable_elasticsearch: Whether to enable ES logging

    Returns:
        Configured logger
    """
    log_level = level or os.getenv("LOG_LEVEL", "INFO")
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Configure root logger
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Get logger for service
    logger = logging.getLogger(service_name)
    logger.setLevel(numeric_level)

    # Add Elasticsearch handler
    if enable_elasticsearch:
        try:
            es_handler = ElasticsearchHandler(service_name)
            es_handler.setLevel(numeric_level)
            logger.addHandler(es_handler)
        except Exception as e:
            logger.warning(f"Failed to initialize Elasticsearch logging: {e}")

    return logger


class LogContext:
    """
    Context manager for adding extra fields to log records.

    Usage:
        with LogContext(story_id="123", task_id="456"):
            logger.info("Processing story")  # Will include story_id and task_id
    """

    _context: dict[str, Any] = {}
    _lock = threading.Lock()

    def __init__(self, **kwargs: Any):
        self.extra = kwargs

    def __enter__(self) -> "LogContext":
        with self._lock:
            self._context.update(self.extra)
        return self

    def __exit__(self, *args: Any) -> None:
        with self._lock:
            for key in self.extra:
                self._context.pop(key, None)

    @classmethod
    def get_context(cls) -> dict[str, Any]:
        """Get the current logging context."""
        return cls._context.copy()


class ContextFilter(logging.Filter):
    """Filter that adds context to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in LogContext.get_context().items():
            setattr(record, key, value)
        return True
