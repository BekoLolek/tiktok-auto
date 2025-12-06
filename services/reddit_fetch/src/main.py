"""Main entry point for Reddit Fetch service."""

import logging
import signal
import time

import schedule

from shared.python.logging import setup_logging

from .config import get_settings
from .fetcher import run_fetch

# Global flag for graceful shutdown
shutdown_requested = False


def handle_shutdown(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    logging.info(f"Received signal {signum}, initiating shutdown...")
    shutdown_requested = True


def fetch_job():
    """Scheduled job to fetch stories."""
    logger = logging.getLogger(__name__)
    try:
        logger.info("Starting scheduled fetch...")
        result = run_fetch()
        logger.info(
            "Fetch completed",
            extra={
                "new_stories": result.new_stories,
                "duplicates": result.duplicates,
                "filtered": result.filtered_out,
                "errors": len(result.errors) if result.errors else 0,
            },
        )
    except Exception as e:
        logger.exception(f"Fetch job failed: {e}")


def main():
    """Main entry point."""
    settings = get_settings()
    logger = setup_logging("reddit-fetch")

    # Register signal handlers
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    logger.info(
        "Reddit Fetch service starting",
        extra={
            "subreddits": settings.subreddit_list,
            "interval_minutes": settings.fetch_interval_minutes,
        },
    )

    # Run immediately on startup
    fetch_job()

    # Schedule periodic fetches
    schedule.every(settings.fetch_interval_minutes).minutes.do(fetch_job)

    # Main loop
    while not shutdown_requested:
        schedule.run_pending()
        time.sleep(1)

    logger.info("Reddit Fetch service shutting down")


if __name__ == "__main__":
    main()
