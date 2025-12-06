"""Configuration for Reddit Fetch service."""

import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Service configuration loaded from environment variables."""

    # Reddit API credentials
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "TikTokAuto/1.0"

    # Subreddits to fetch from (comma-separated)
    subreddits: str = "nosleep,shortscarystories,creepypasta"

    # Content filters
    min_char_count: int = 500
    max_char_count: int = 15000  # ~5 min at 150 wpm, allows for splitting
    min_upvotes: int = 100
    max_stories_per_fetch: int = 10

    # Database
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "tiktok_auto"
    postgres_password: str = ""
    postgres_db: str = "tiktok_auto"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379

    # Fetch schedule (cron-like)
    fetch_interval_minutes: int = 60

    @property
    def database_url(self) -> str:
        """Build database connection URL."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        """Build Redis connection URL."""
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    @property
    def subreddit_list(self) -> list[str]:
        """Parse comma-separated subreddits into list."""
        return [s.strip() for s in self.subreddits.split(",") if s.strip()]

    model_config = {"env_prefix": "", "case_sensitive": False}


def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
