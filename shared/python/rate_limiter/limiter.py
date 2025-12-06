"""Rate limiting implementation using Redis."""

import logging
import os
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from functools import wraps
from typing import Any

import redis

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Exception raised when rate limit is exceeded."""

    def __init__(self, limit_type: str, retry_after: int):
        self.limit_type = limit_type
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded for {limit_type}. Retry after {retry_after} seconds.")


class RateLimiter:
    """
    Redis-based rate limiter for API and upload throttling.

    Supports multiple rate limiting strategies:
    - Token bucket for API calls
    - Daily limits for uploads
    - Sliding window for burst protection
    """

    def __init__(self):
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        self.redis = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=1,  # Use separate DB for rate limiting
            decode_responses=True,
        )

        # Configuration from environment
        self.reddit_requests_per_minute = int(os.getenv("REDDIT_RATE_LIMIT", "30"))
        self.tiktok_uploads_per_day = int(os.getenv("TIKTOK_DAILY_UPLOAD_LIMIT", "10"))
        self.ollama_requests_per_minute = int(os.getenv("OLLAMA_RATE_LIMIT", "20"))

    def _get_window_key(self, key: str, window_seconds: int) -> str:
        """Get a time-windowed key."""
        window = int(time.time() // window_seconds)
        return f"ratelimit:{key}:{window}"

    def check_reddit_api(self) -> bool:
        """
        Check if Reddit API call is allowed.

        Uses sliding window counter with 1-minute windows.

        Returns:
            True if allowed, raises RateLimitExceeded otherwise
        """
        key = self._get_window_key("reddit", 60)

        current = self.redis.get(key)
        if current and int(current) >= self.reddit_requests_per_minute:
            ttl = self.redis.ttl(key)
            raise RateLimitExceeded("reddit_api", ttl if ttl > 0 else 60)

        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, 60)
        pipe.execute()

        return True

    def check_tiktok_upload(self) -> bool:
        """
        Check if TikTok upload is allowed.

        Uses daily counter resetting at midnight UTC.

        Returns:
            True if allowed, raises RateLimitExceeded otherwise
        """
        today = datetime.utcnow().strftime("%Y-%m-%d")
        key = f"ratelimit:tiktok_upload:{today}"

        current = self.redis.get(key)
        if current and int(current) >= self.tiktok_uploads_per_day:
            # Calculate seconds until midnight
            now = datetime.utcnow()
            midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            retry_after = int((midnight - now).total_seconds())
            raise RateLimitExceeded("tiktok_upload", retry_after)

        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.expireat(key, int((datetime.utcnow() + timedelta(days=1)).timestamp()))
        pipe.execute()

        return True

    def check_ollama_api(self) -> bool:
        """
        Check if Ollama API call is allowed.

        Uses sliding window counter with 1-minute windows.

        Returns:
            True if allowed, raises RateLimitExceeded otherwise
        """
        key = self._get_window_key("ollama", 60)

        current = self.redis.get(key)
        if current and int(current) >= self.ollama_requests_per_minute:
            ttl = self.redis.ttl(key)
            raise RateLimitExceeded("ollama_api", ttl if ttl > 0 else 60)

        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, 60)
        pipe.execute()

        return True

    def get_upload_count_today(self) -> int:
        """Get the number of uploads made today."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        key = f"ratelimit:tiktok_upload:{today}"
        count = self.redis.get(key)
        return int(count) if count else 0

    def get_remaining_uploads_today(self) -> int:
        """Get the remaining upload quota for today."""
        return max(0, self.tiktok_uploads_per_day - self.get_upload_count_today())

    def wait_for_slot(self, limit_type: str, max_wait: int = 300) -> bool:
        """
        Wait for a rate limit slot to become available.

        Args:
            limit_type: Type of rate limit ('reddit', 'tiktok', 'ollama')
            max_wait: Maximum seconds to wait

        Returns:
            True if slot acquired, False if max_wait exceeded
        """
        check_methods = {
            "reddit": self.check_reddit_api,
            "tiktok": self.check_tiktok_upload,
            "ollama": self.check_ollama_api,
        }

        if limit_type not in check_methods:
            raise ValueError(f"Unknown limit type: {limit_type}")

        waited = 0
        while waited < max_wait:
            try:
                check_methods[limit_type]()
                return True
            except RateLimitExceeded as e:
                wait_time = min(e.retry_after, max_wait - waited)
                if wait_time <= 0:
                    return False
                logger.info(f"Rate limited for {limit_type}, waiting {wait_time}s")
                time.sleep(wait_time)
                waited += wait_time

        return False


def rate_limited(limit_type: str) -> Callable:
    """
    Decorator to apply rate limiting to a function.

    Args:
        limit_type: Type of rate limit to apply

    Example:
        @rate_limited("reddit")
        def fetch_posts():
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            limiter = RateLimiter()
            check_methods = {
                "reddit": limiter.check_reddit_api,
                "tiktok": limiter.check_tiktok_upload,
                "ollama": limiter.check_ollama_api,
            }

            if limit_type in check_methods:
                check_methods[limit_type]()

            return func(*args, **kwargs)

        return wrapper

    return decorator
