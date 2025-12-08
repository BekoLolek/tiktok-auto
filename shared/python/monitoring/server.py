"""HTTP server for Prometheus metrics endpoint."""

import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .metrics import MetricsCollector

logger = logging.getLogger(__name__)


class MetricsHandler(BaseHTTPRequestHandler):
    """HTTP handler for /metrics endpoint."""

    metrics_collector: "MetricsCollector | None" = None

    def do_GET(self):
        """Handle GET requests."""
        if self.path == "/metrics":
            self._serve_metrics()
        elif self.path == "/health":
            self._serve_health()
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def _serve_metrics(self):
        """Serve Prometheus metrics."""
        if self.metrics_collector is None:
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b"Metrics not initialized")
            return

        try:
            output = self.metrics_collector.get_metrics()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(output)))
            self.end_headers()
            self.wfile.write(output)
        except Exception as e:
            logger.error(f"Error serving metrics: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f"Error: {e}".encode())

    def _serve_health(self):
        """Serve health check."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "healthy"}')

    def log_message(self, format, *args):
        """Suppress request logging."""
        pass


def start_metrics_server(
    metrics_collector: "MetricsCollector",
    host: str = "0.0.0.0",
    port: int = 9090,
) -> HTTPServer:
    """Start the metrics HTTP server in a background thread.

    Args:
        metrics_collector: The metrics collector instance
        host: Host to bind to
        port: Port to listen on

    Returns:
        The HTTPServer instance
    """
    MetricsHandler.metrics_collector = metrics_collector

    server = HTTPServer((host, port), MetricsHandler)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    logger.info(f"Metrics server started on http://{host}:{port}/metrics")
    return server
