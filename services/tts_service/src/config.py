"""Configuration for TTS service."""

from pathlib import Path

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

    # Piper TTS
    piper_host: str = "localhost"
    piper_port: int = 10200

    # Voice settings
    male_voice: str = "en_US-lessac-medium"
    female_voice: str = "en_US-amy-medium"

    # Output settings
    audio_output_dir: str = "/data/audio"
    audio_format: str = "wav"
    sample_rate: int = 22050

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
    def audio_path(self) -> Path:
        """Get audio output directory as Path."""
        path = Path(self.audio_output_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    model_config = {"env_prefix": "", "case_sensitive": False}


def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
