"""Celery application configuration."""

import os

from celery import Celery
from celery.schedules import crontab

# Build Redis URL from environment
redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = os.getenv("REDIS_PORT", "6379")
redis_url = f"redis://{redis_host}:{redis_port}/0"

# Create Celery app
app = Celery(
    "tiktok_auto",
    broker=redis_url,
    backend=redis_url,
    include=[
        "shared.python.celery_app.tasks",
    ],
)

# Celery configuration
app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Task execution settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Result backend settings
    result_expires=3600,  # Results expire after 1 hour
    # Worker settings
    worker_prefetch_multiplier=1,
    worker_concurrency=2,
    # Retry settings
    task_default_retry_delay=60,
    task_max_retries=3,
    # Task routing
    task_routes={
        "shared.python.celery_app.tasks.process_story": {"queue": "text_processing"},
        "shared.python.celery_app.tasks.generate_audio": {"queue": "tts"},
        "shared.python.celery_app.tasks.render_video": {"queue": "video"},
        "shared.python.celery_app.tasks.upload_video": {"queue": "upload"},
        "shared.python.celery_app.tasks.fetch_reddit": {"queue": "fetch"},
        "shared.python.celery_app.tasks.process_pending_uploads": {"queue": "upload"},
        "shared.python.celery_app.tasks.cleanup_old_files": {"queue": "maintenance"},
        "shared.python.celery_app.tasks.retry_failed_uploads": {"queue": "upload"},
        "shared.python.celery_app.tasks.process_dead_letter_queue": {"queue": "maintenance"},
    },
    # Task time limits
    task_soft_time_limit=300,  # 5 minutes soft limit
    task_time_limit=600,  # 10 minutes hard limit
    # Dead letter queue settings
    task_acks_on_failure_or_timeout=False,
)

# Beat schedule for periodic tasks
app.conf.beat_schedule = {
    # Fetch new stories from Reddit (configurable via env)
    "fetch-reddit-stories": {
        "task": "shared.python.celery_app.tasks.scheduled_fetch_reddit",
        "schedule": crontab(
            minute=os.getenv("REDDIT_FETCH_MINUTE", "0"),
            hour=os.getenv("REDDIT_FETCH_HOUR", "*/2"),  # Every 2 hours by default
        ),
        "args": (),
    },
    # Process pending uploads (check for ready videos)
    "process-pending-uploads": {
        "task": "shared.python.celery_app.tasks.process_pending_uploads",
        "schedule": crontab(minute="*/15"),  # Every 15 minutes
        "args": (),
    },
    # Retry failed uploads
    "retry-failed-uploads": {
        "task": "shared.python.celery_app.tasks.retry_failed_uploads",
        "schedule": crontab(minute="30", hour="*/1"),  # Every hour at :30
        "args": (),
    },
    # Cleanup old processed files
    "cleanup-old-files": {
        "task": "shared.python.celery_app.tasks.cleanup_old_files",
        "schedule": crontab(minute="0", hour="3"),  # Daily at 3 AM
        "args": (),
    },
    # Process dead letter queue
    "process-dead-letter-queue": {
        "task": "shared.python.celery_app.tasks.process_dead_letter_queue",
        "schedule": crontab(minute="*/30"),  # Every 30 minutes
        "args": (),
    },
}


if __name__ == "__main__":
    app.start()
