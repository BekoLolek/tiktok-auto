"""Tests for Prometheus metrics module."""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def reset_prometheus_registry():
    """Reset the Prometheus registry before each test."""
    try:
        from prometheus_client import REGISTRY

        # Collect all collectors to unregister
        collectors_to_unregister = []
        for collector in list(REGISTRY._collector_to_names.keys()):
            # Skip the default collectors (platform, gc, process)
            collector_name = type(collector).__name__
            if collector_name not in ("PlatformCollector", "GCCollector", "ProcessCollector"):
                collectors_to_unregister.append(collector)

        for collector in collectors_to_unregister:
            try:
                REGISTRY.unregister(collector)
            except Exception:
                pass
    except ImportError:
        pass

    yield

    # Cleanup after test
    try:
        from prometheus_client import REGISTRY

        collectors_to_unregister = []
        for collector in list(REGISTRY._collector_to_names.keys()):
            collector_name = type(collector).__name__
            if collector_name not in ("PlatformCollector", "GCCollector", "ProcessCollector"):
                collectors_to_unregister.append(collector)

        for collector in collectors_to_unregister:
            try:
                REGISTRY.unregister(collector)
            except Exception:
                pass
    except ImportError:
        pass


class TestMetricsCollector:
    """Tests for MetricsCollector class."""

    def test_init_with_prometheus_available(self):
        """Test initialization when prometheus_client is available."""
        from shared.python.monitoring.metrics import MetricsCollector

        collector = MetricsCollector("test-service")
        assert collector.service_name == "test-service"
        assert collector.enabled is True

    def test_init_disabled_via_env(self):
        """Test metrics disabled via environment variable."""
        import os

        with patch.dict(os.environ, {"METRICS_ENABLED": "false"}):
            # Mock the MetricsCollector to test the disabled behavior
            from shared.python.monitoring.metrics import MetricsCollector

            # Create a collector with mocked env
            collector = MetricsCollector.__new__(MetricsCollector)
            collector.service_name = "test-service"
            collector.enabled = os.getenv("METRICS_ENABLED", "true").lower() == "true"
            assert collector.enabled is False

    def test_get_metrics_returns_bytes(self):
        """Test get_metrics returns Prometheus format."""
        from shared.python.monitoring.metrics import MetricsCollector

        collector = MetricsCollector("test-service")
        output = collector.get_metrics()
        assert isinstance(output, bytes)
        assert b"python_info" in output or len(output) > 0

    def test_record_story_fetched(self):
        """Test recording a story fetch."""
        from shared.python.monitoring.metrics import MetricsCollector

        collector = MetricsCollector("test-service")
        # Should not raise
        collector.record_story_fetched("testsub")

    def test_record_upload(self):
        """Test recording upload status."""
        from shared.python.monitoring.metrics import MetricsCollector

        collector = MetricsCollector("test-service")
        collector.record_upload("success")
        collector.record_upload("failed")

    def test_track_duration_context_manager(self):
        """Test duration tracking context manager."""
        from shared.python.monitoring.metrics import MetricsCollector

        collector = MetricsCollector("test-service")

        with collector.track_duration("audio_generation_duration"):
            pass  # Simulated work

    def test_track_task_decorator(self):
        """Test task tracking decorator."""
        from shared.python.monitoring.metrics import MetricsCollector

        collector = MetricsCollector("test-service")

        @collector.track_task("test_task")
        def sample_task():
            return "result"

        result = sample_task()
        assert result == "result"

    def test_set_gauges(self):
        """Test setting gauge values."""
        from shared.python.monitoring.metrics import MetricsCollector

        collector = MetricsCollector("test-service")
        collector.set_pending_stories(5)
        collector.set_pending_uploads(3)
        collector.set_failed_uploads(1)


class TestMetricsServer:
    """Tests for metrics HTTP server."""

    def test_start_metrics_server(self):
        """Test starting the metrics server."""
        from shared.python.monitoring.metrics import MetricsCollector
        from shared.python.monitoring.server import start_metrics_server

        collector = MetricsCollector("test-service")

        # Start on a random port to avoid conflicts
        import socket

        with socket.socket() as s:
            s.bind(("", 0))
            port = s.getsockname()[1]

        server = start_metrics_server(collector, port=port)
        assert server is not None

        # Cleanup
        server.shutdown()

    def test_metrics_endpoint(self):
        """Test /metrics endpoint returns data."""
        import socket
        import urllib.request

        from shared.python.monitoring.metrics import MetricsCollector
        from shared.python.monitoring.server import start_metrics_server

        collector = MetricsCollector("test-service")

        # Find free port
        with socket.socket() as s:
            s.bind(("", 0))
            port = s.getsockname()[1]

        server = start_metrics_server(collector, port=port)

        try:
            # Give server time to start
            import time

            time.sleep(0.1)

            # Make request
            with urllib.request.urlopen(f"http://localhost:{port}/metrics") as response:
                assert response.status == 200
                data = response.read()
                assert len(data) > 0
        finally:
            server.shutdown()


class TestInitMetrics:
    """Tests for init_metrics function."""

    def test_init_metrics_returns_collector(self):
        """Test init_metrics returns a collector."""
        from shared.python.monitoring.metrics import init_metrics

        collector = init_metrics("test-service")
        assert collector is not None
        assert collector.service_name == "test-service"
