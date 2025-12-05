"""Celery application configuration."""

import os

from celery import Celery

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
        "celery_app.tasks",
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
        "celery_app.tasks.process_story": {"queue": "text_processing"},
        "celery_app.tasks.generate_audio": {"queue": "tts"},
        "celery_app.tasks.render_video": {"queue": "video"},
        "celery_app.tasks.upload_video": {"queue": "upload"},
        "celery_app.tasks.fetch_reddit": {"queue": "fetch"},
    },
    # Task time limits
    task_soft_time_limit=300,  # 5 minutes soft limit
    task_time_limit=600,  # 10 minutes hard limit
)

# Beat schedule for periodic tasks
app.conf.beat_schedule = {
    # Example: fetch new stories every hour
    # "fetch-reddit-stories": {
    #     "task": "celery_app.tasks.fetch_reddit",
    #     "schedule": 3600.0,  # Every hour
    #     "args": (["scifi", "fantasy"],),
    # },
}


if __name__ == "__main__":
    app.start()
