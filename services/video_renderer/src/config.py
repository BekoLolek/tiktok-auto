"""Configuration for Video Renderer service."""

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

    # Video settings
    video_width: int = 1080
    video_height: int = 1920
    video_fps: int = 30
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    video_bitrate: str = "5000k"
    audio_bitrate: str = "192k"

    # Paths
    background_videos_dir: str = "/data/backgrounds"
    audio_input_dir: str = "/data/audio"
    video_output_dir: str = "/data/videos"
    temp_dir: str = "/data/temp"

    # Caption settings
    caption_font: str = "Arial-Bold"
    caption_font_size: int = 60
    caption_color: str = "white"
    caption_stroke_color: str = "black"
    caption_stroke_width: int = 3
    caption_position: str = "center"
    caption_margin_bottom: int = 200

    # Whisper settings
    whisper_model: str = "base"

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
    def background_path(self) -> Path:
        """Get background videos directory as Path."""
        path = Path(self.background_videos_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def output_path(self) -> Path:
        """Get video output directory as Path."""
        path = Path(self.video_output_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def temp_path(self) -> Path:
        """Get temp directory as Path."""
        path = Path(self.temp_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    model_config = {"env_prefix": "", "case_sensitive": False}


def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
