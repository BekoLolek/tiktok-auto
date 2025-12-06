"""Prometheus metrics collection for all services."""

import os
import time
from collections.abc import Callable
from contextlib import contextmanager
from functools import wraps
from typing import Any

try:
    from prometheus_client import (
        REGISTRY,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


class MetricsCollector:
    """Centralized metrics collection for TikTok Auto pipeline."""

    def __init__(self, service_name: str):
        self.service_name = service_name
        self.enabled = PROMETHEUS_AVAILABLE and os.getenv("METRICS_ENABLED", "true").lower() == "true"

        if not self.enabled:
            return

        # Pipeline counters
        self.stories_fetched = Counter(
            "tiktok_auto_stories_fetched_total",
            "Total number of stories fetched from Reddit",
            ["subreddit"],
        )

        self.stories_processed = Counter(
            "tiktok_auto_stories_processed_total",
            "Total number of stories processed",
            ["status"],
        )

        self.scripts_created = Counter(
            "tiktok_auto_scripts_created_total",
            "Total number of scripts created",
        )

        self.audio_generated = Counter(
            "tiktok_auto_audio_generated_total",
            "Total number of audio files generated",
            ["voice_model"],
        )

        self.videos_rendered = Counter(
            "tiktok_auto_videos_rendered_total",
            "Total number of videos rendered",
        )

        self.uploads_total = Counter(
            "tiktok_auto_uploads_total",
            "Total number of upload attempts",
            ["status"],
        )

        # Processing time histograms
        self.text_processing_duration = Histogram(
            "tiktok_auto_text_processing_duration_seconds",
            "Time spent processing text",
            buckets=[0.5, 1, 2, 5, 10, 30, 60],
        )

        self.audio_generation_duration = Histogram(
            "tiktok_auto_audio_generation_duration_seconds",
            "Time spent generating audio",
            buckets=[1, 5, 10, 30, 60, 120, 300],
        )

        self.video_rendering_duration = Histogram(
            "tiktok_auto_video_rendering_duration_seconds",
            "Time spent rendering video",
            buckets=[10, 30, 60, 120, 300, 600],
        )

        self.upload_duration = Histogram(
            "tiktok_auto_upload_duration_seconds",
            "Time spent uploading to TikTok",
            buckets=[5, 10, 30, 60, 120, 300],
        )

        # Queue gauges
        self.pending_stories = Gauge(
            "tiktok_auto_pending_stories",
            "Number of stories pending approval",
        )

        self.pending_uploads = Gauge(
            "tiktok_auto_pending_uploads",
            "Number of videos pending upload",
        )

        self.failed_uploads = Gauge(
            "tiktok_auto_failed_uploads",
            "Number of failed uploads awaiting retry",
        )

        # Celery task gauges
        self.celery_tasks_active = Gauge(
            "tiktok_auto_celery_tasks_active",
            "Number of active Celery tasks",
            ["task_name"],
        )

        self.celery_tasks_total = Counter(
            "tiktok_auto_celery_tasks_total",
            "Total Celery tasks executed",
            ["task_name", "status"],
        )

        # Error counters
        self.errors_total = Counter(
            "tiktok_auto_errors_total",
            "Total errors by type",
            ["service", "error_type"],
        )

    def get_metrics(self) -> bytes:
        """Generate Prometheus metrics output."""
        if not self.enabled:
            return b""
        return generate_latest(REGISTRY)

    @contextmanager
    def track_duration(self, histogram_name: str):
        """Context manager to track operation duration."""
        if not self.enabled:
            yield
            return

        histogram = getattr(self, histogram_name, None)
        if histogram is None:
            yield
            return

        start = time.time()
        try:
            yield
        finally:
            duration = time.time() - start
            histogram.observe(duration)

    def track_task(self, task_name: str) -> Callable:
        """Decorator to track Celery task execution."""

        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                if not self.enabled:
                    return func(*args, **kwargs)

                self.celery_tasks_active.labels(task_name=task_name).inc()
                try:
                    result = func(*args, **kwargs)
                    self.celery_tasks_total.labels(task_name=task_name, status="success").inc()
                    return result
                except Exception:
                    self.celery_tasks_total.labels(task_name=task_name, status="failure").inc()
                    raise
                finally:
                    self.celery_tasks_active.labels(task_name=task_name).dec()

            return wrapper

        return decorator

    def record_story_fetched(self, subreddit: str) -> None:
        """Record a story being fetched."""
        if self.enabled:
            self.stories_fetched.labels(subreddit=subreddit).inc()

    def record_story_processed(self, status: str) -> None:
        """Record a story being processed."""
        if self.enabled:
            self.stories_processed.labels(status=status).inc()

    def record_script_created(self) -> None:
        """Record a script being created."""
        if self.enabled:
            self.scripts_created.inc()

    def record_audio_generated(self, voice_model: str = "default") -> None:
        """Record audio being generated."""
        if self.enabled:
            self.audio_generated.labels(voice_model=voice_model).inc()

    def record_video_rendered(self) -> None:
        """Record a video being rendered."""
        if self.enabled:
            self.videos_rendered.inc()

    def record_upload(self, status: str) -> None:
        """Record an upload attempt."""
        if self.enabled:
            self.uploads_total.labels(status=status).inc()

    def record_error(self, error_type: str) -> None:
        """Record an error occurrence."""
        if self.enabled:
            self.errors_total.labels(service=self.service_name, error_type=error_type).inc()

    def set_pending_stories(self, count: int) -> None:
        """Set the pending stories gauge."""
        if self.enabled:
            self.pending_stories.set(count)

    def set_pending_uploads(self, count: int) -> None:
        """Set the pending uploads gauge."""
        if self.enabled:
            self.pending_uploads.set(count)

    def set_failed_uploads(self, count: int) -> None:
        """Set the failed uploads gauge."""
        if self.enabled:
            self.failed_uploads.set(count)


# Global metrics instance (initialized per service)
metrics: MetricsCollector | None = None


def init_metrics(service_name: str) -> MetricsCollector:
    """Initialize metrics for a service."""
    global metrics
    metrics = MetricsCollector(service_name)
    return metrics
