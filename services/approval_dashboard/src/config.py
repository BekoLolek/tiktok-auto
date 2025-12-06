"""Configuration for Approval Dashboard service."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Service configuration loaded from environment variables."""

    # Database
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "tiktok_auto"
    postgres_password: str = ""
    postgres_db: str = "tiktok_auto"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379

    # Elasticsearch
    elasticsearch_host: str = "localhost"
    elasticsearch_port: int = 9200

    # Server
    host: str = "0.0.0.0"
    port: int = 8080
    debug: bool = False

    # Pagination
    stories_per_page: int = 20
    logs_per_page: int = 50

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
    def elasticsearch_url(self) -> str:
        """Build Elasticsearch URL."""
        return f"http://{self.elasticsearch_host}:{self.elasticsearch_port}"

    model_config = {"env_prefix": "", "case_sensitive": False}


def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
