"""Configuration for Text Processor service."""

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

    # Ollama
    ollama_host: str = "localhost"
    ollama_port: int = 11434
    ollama_model: str = "llama3.1:8b"

    # Processing settings
    max_duration_per_part_seconds: int = 180  # 3 minutes max per part
    words_per_minute: int = 150  # Average speaking rate for duration estimation

    # Retry settings
    max_retries: int = 3
    retry_delay_seconds: int = 5

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
    def ollama_url(self) -> str:
        """Build Ollama API URL."""
        return f"http://{self.ollama_host}:{self.ollama_port}"

    model_config = {"env_prefix": "", "case_sensitive": False}


def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
