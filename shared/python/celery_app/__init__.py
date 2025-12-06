"""Celery app module for TikTok Auto."""

from .app import app

# Alias for backwards compatibility
celery_app = app

from .tasks import (  # noqa: E402
    PermanentError,
    TransientError,
    fetch_reddit,
    generate_audio,
    process_scripts_to_videos,
    process_story,
    render_video,
    run_full_pipeline,
    send_failure_notification,
    upload_batch,
    upload_video,
)

__all__ = [
    "app",
    "celery_app",
    "TransientError",
    "PermanentError",
    "fetch_reddit",
    "process_story",
    "generate_audio",
    "render_video",
    "upload_video",
    "send_failure_notification",
    "run_full_pipeline",
    "process_scripts_to_videos",
    "upload_batch",
]
