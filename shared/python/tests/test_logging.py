"""Tests for logging module."""

import logging
from unittest.mock import patch


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_setup_logging_returns_logger(self):
        """Test that setup_logging returns a logger."""
        from shared.python.logging import setup_logging

        with patch("shared.python.logging.elastic_handler.Elasticsearch"):
            logger = setup_logging("test-service", enable_elasticsearch=False)

        assert isinstance(logger, logging.Logger)
        assert logger.name == "test-service"

    def test_setup_logging_respects_level(self):
        """Test that setup_logging sets the correct level."""
        from shared.python.logging import setup_logging

        logger = setup_logging("test-service", level="DEBUG", enable_elasticsearch=False)
        assert logger.level == logging.DEBUG

        logger2 = setup_logging("test-service-2", level="WARNING", enable_elasticsearch=False)
        assert logger2.level == logging.WARNING

    def test_setup_logging_with_env_level(self, monkeypatch):
        """Test that setup_logging uses LOG_LEVEL env var."""
        from shared.python.logging import setup_logging

        monkeypatch.setenv("LOG_LEVEL", "ERROR")
        logger = setup_logging("test-service-env", enable_elasticsearch=False)
        assert logger.level == logging.ERROR


class TestLogContext:
    """Tests for LogContext context manager."""

    def test_log_context_adds_fields(self):
        """Test that LogContext adds extra fields."""
        from shared.python.logging import LogContext

        with LogContext(story_id="123", task_id="456"):
            context = LogContext.get_context()
            assert context["story_id"] == "123"
            assert context["task_id"] == "456"

    def test_log_context_removes_fields_on_exit(self):
        """Test that LogContext removes fields when exiting."""
        from shared.python.logging import LogContext

        with LogContext(story_id="123"):
            assert "story_id" in LogContext.get_context()

        assert "story_id" not in LogContext.get_context()

    def test_log_context_nested(self):
        """Test nested LogContext."""
        from shared.python.logging import LogContext

        with LogContext(outer="value1"):
            with LogContext(inner="value2"):
                context = LogContext.get_context()
                assert context["outer"] == "value1"
                assert context["inner"] == "value2"

            context_after_inner = LogContext.get_context()
            assert context_after_inner["outer"] == "value1"
            assert "inner" not in context_after_inner


class TestElasticsearchHandler:
    """Tests for ElasticsearchHandler."""

    def test_handler_format_record(self, mock_elasticsearch):
        """Test that records are formatted correctly."""
        from shared.python.logging.elastic_handler import ElasticsearchHandler

        handler = ElasticsearchHandler("test-service", es_host="localhost", es_port=9200)

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="/test/path.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        formatted = handler._format_record(record)

        assert "_index" in formatted
        assert "test-service" in formatted["_index"]
        assert formatted["_source"]["level"] == "INFO"
        assert formatted["_source"]["message"] == "Test message"
        assert formatted["_source"]["service"] == "test-service"

    def test_handler_index_name_includes_date(self, mock_elasticsearch):
        """Test that index name includes current date."""
        from datetime import datetime

        from shared.python.logging.elastic_handler import ElasticsearchHandler

        handler = ElasticsearchHandler("test-service", es_host="localhost", es_port=9200)

        index_name = handler._get_index_name()
        today = datetime.utcnow().strftime("%Y.%m.%d")

        assert f"tiktok-auto-test-service-{today}" == index_name


class TestContextFilter:
    """Tests for ContextFilter."""

    def test_filter_adds_context_to_record(self):
        """Test that filter adds context to log records."""
        from shared.python.logging import ContextFilter, LogContext

        filter_obj = ContextFilter()

        with LogContext(request_id="abc123"):
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="/test/path.py",
                lineno=1,
                msg="Test",
                args=(),
                exc_info=None,
            )

            result = filter_obj.filter(record)

            assert result is True
            assert hasattr(record, "request_id")
            assert record.request_id == "abc123"
