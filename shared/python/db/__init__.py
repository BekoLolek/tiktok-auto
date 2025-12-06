"""Database module for TikTok Auto."""

from .connection import (
    SessionLocal,
    drop_db,
    engine,
    get_database_url,
    get_db,
    get_session,
    init_db,
    update_story_progress,
)
from .models import (
    Audio,
    Base,
    Batch,
    BatchStatus,
    PipelineRun,
    Script,
    Story,
    StoryStatus,
    Upload,
    UploadStatus,
    Video,
    VoiceGender,
)

__all__ = [
    # Models
    "Base",
    "Story",
    "Script",
    "Audio",
    "Video",
    "Upload",
    "Batch",
    "PipelineRun",
    # Enums
    "StoryStatus",
    "UploadStatus",
    "BatchStatus",
    "VoiceGender",
    # Connection
    "engine",
    "SessionLocal",
    "get_session",
    "get_db",
    "init_db",
    "drop_db",
    "get_database_url",
    "update_story_progress",
]
