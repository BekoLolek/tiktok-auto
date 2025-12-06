"""Structured logging configuration for all services."""

import json
import logging
import os
import sys
from datetime import datetime
from typing import Any


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging to Elasticsearch."""

    def __init__(self, service_name: str):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "@timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.service_name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields (story_id, script_id, etc.)
        extra_fields = [
            "story_id",
            "script_id",
            "audio_id",
            "video_id",
            "upload_id",
            "batch_id",
            "task_id",
            "duration_ms",
            "status",
            "error_type",
        ]
        for field in extra_fields:
            if hasattr(record, field):
                log_data[field] = getattr(record, field)

        return json.dumps(log_data)


class CorrelationAdapter(logging.LoggerAdapter):
    """Logger adapter that adds correlation IDs to all log messages."""

    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        extra = kwargs.get("extra", {})
        extra.update(self.extra)
        kwargs["extra"] = extra
        return msg, kwargs


def configure_logging(
    service_name: str,
    log_level: str | None = None,
    json_output: bool | None = None,
) -> None:
    """
    Configure logging for a service.

    Args:
        service_name: Name of the service (e.g., 'reddit_fetch', 'tts_service')
        log_level: Log level (DEBUG, INFO, WARNING, ERROR). Defaults to env LOG_LEVEL or INFO.
        json_output: Whether to output JSON format. Defaults to True in production.
    """
    level = log_level or os.getenv("LOG_LEVEL", "INFO")
    use_json = json_output if json_output is not None else os.getenv("LOG_FORMAT") == "json"

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level.upper()))

    if use_json:
        handler.setFormatter(JSONFormatter(service_name))
    else:
        handler.setFormatter(
            logging.Formatter(
                f"%(asctime)s | {service_name} | %(levelname)s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root_logger.addHandler(handler)

    # Reduce noise from third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("elasticsearch").setLevel(logging.WARNING)


def get_logger(
    name: str,
    story_id: str | None = None,
    script_id: str | None = None,
    **extra: Any,
) -> CorrelationAdapter:
    """
    Get a logger with optional correlation IDs.

    Args:
        name: Logger name (usually __name__)
        story_id: Optional story UUID for correlation
        script_id: Optional script UUID for correlation
        **extra: Additional fields to include in all log messages

    Returns:
        Logger adapter with correlation context
    """
    logger = logging.getLogger(name)
    context = {k: v for k, v in extra.items() if v is not None}
    if story_id:
        context["story_id"] = story_id
    if script_id:
        context["script_id"] = script_id

    return CorrelationAdapter(logger, context)
