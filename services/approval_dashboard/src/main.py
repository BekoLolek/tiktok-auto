"""Main entry point for Approval Dashboard service."""

import uvicorn

from shared.python.logging import setup_logging

from .config import get_settings


def main():
    """Run the dashboard server."""
    settings = get_settings()
    setup_logging("approval-dashboard")

    uvicorn.run(
        "services.approval_dashboard.src.app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info",
    )


if __name__ == "__main__":
    main()
