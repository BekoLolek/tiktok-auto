"""Database models for TikTok Auto pipeline."""

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class StoryStatus(str, Enum):
    """Status values for stories."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class UploadStatus(str, Enum):
    """Status values for uploads."""

    PENDING = "pending"
    UPLOADING = "uploading"
    SUCCESS = "success"
    FAILED = "failed"
    MANUAL_REQUIRED = "manual_required"


class BatchStatus(str, Enum):
    """Status values for batches."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class VoiceGender(str, Enum):
    """Voice gender options."""

    MALE = "male"
    FEMALE = "female"


class Story(Base):
    """Raw Reddit posts."""

    __tablename__ = "stories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reddit_id = Column(String(20), unique=True, nullable=False)
    subreddit = Column(String(100), nullable=False)
    title = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    author = Column(String(100))
    score = Column(Integer)
    url = Column(Text)
    char_count = Column(Integer, nullable=False)
    status = Column(String(20), default=StoryStatus.PENDING.value)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    scripts = relationship("Script", back_populates="story", cascade="all, delete-orphan")
    batches = relationship("Batch", back_populates="story", cascade="all, delete-orphan")
    pipeline_runs = relationship(
        "PipelineRun", back_populates="story", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_stories_status", "status"),
        Index("idx_stories_subreddit", "subreddit"),
    )


class Script(Base):
    """Processed scripts (can be multiple parts per story)."""

    __tablename__ = "scripts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    story_id = Column(UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"))
    part_number = Column(Integer, nullable=False)
    total_parts = Column(Integer, nullable=False)
    hook = Column(Text)
    content = Column(Text, nullable=False)
    cta = Column(Text)
    char_count = Column(Integer, nullable=False)
    voice_gender = Column(String(10))
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    story = relationship("Story", back_populates="scripts")
    audio = relationship("Audio", back_populates="script", cascade="all, delete-orphan")

    __table_args__ = (Index("idx_scripts_story_id", "story_id"),)


class Audio(Base):
    """Generated narration files."""

    __tablename__ = "audio"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    script_id = Column(UUID(as_uuid=True), ForeignKey("scripts.id", ondelete="CASCADE"))
    file_path = Column(Text, nullable=False)
    duration_seconds = Column(Float)
    voice_model = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    script = relationship("Script", back_populates="audio")
    videos = relationship("Video", back_populates="audio", cascade="all, delete-orphan")


class Video(Base):
    """Rendered video files."""

    __tablename__ = "videos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    audio_id = Column(UUID(as_uuid=True), ForeignKey("audio.id", ondelete="CASCADE"))
    file_path = Column(Text, nullable=False)
    duration_seconds = Column(Float)
    resolution = Column(String(20))
    background_video = Column(Text)
    has_captions = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    audio = relationship("Audio", back_populates="videos")
    uploads = relationship("Upload", back_populates="video", cascade="all, delete-orphan")


class Upload(Base):
    """Publishing status."""

    __tablename__ = "uploads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    video_id = Column(UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"))
    platform = Column(String(20), nullable=False)  # tiktok
    status = Column(String(20), nullable=False)
    platform_video_id = Column(Text)
    platform_url = Column(Text)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    uploaded_at = Column(DateTime)

    # Relationships
    video = relationship("Video", back_populates="uploads")

    __table_args__ = (Index("idx_uploads_status", "status"),)


class Batch(Base):
    """Group multi-part uploads."""

    __tablename__ = "batches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    story_id = Column(UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"))
    status = Column(String(20), nullable=False)
    total_parts = Column(Integer, nullable=False)
    completed_parts = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    story = relationship("Story", back_populates="batches")
    pipeline_runs = relationship(
        "PipelineRun", back_populates="batch", cascade="all, delete-orphan"
    )


class PipelineRun(Base):
    """Track pipeline executions."""

    __tablename__ = "pipeline_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    story_id = Column(UUID(as_uuid=True), ForeignKey("stories.id"))
    batch_id = Column(UUID(as_uuid=True), ForeignKey("batches.id"))
    status = Column(String(20), nullable=False)
    current_step = Column(String(50))
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    error_message = Column(Text)

    # Relationships
    story = relationship("Story", back_populates="pipeline_runs")
    batch = relationship("Batch", back_populates="pipeline_runs")

    __table_args__ = (Index("idx_pipeline_runs_status", "status"),)
