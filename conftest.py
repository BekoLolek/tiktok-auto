"""
Pytest configuration and shared fixtures for TikTok Auto tests.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from datetime import datetime
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from shared.python.db import Script, Story

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Set test environment variables before importing modules
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_USER", "test_user")
os.environ.setdefault("POSTGRES_PASSWORD", "test_password")
os.environ.setdefault("POSTGRES_DB", "test_db")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")
os.environ.setdefault("ELASTICSEARCH_HOST", "localhost")
os.environ.setdefault("ELASTICSEARCH_PORT", "9200")
os.environ.setdefault("LOG_LEVEL", "DEBUG")


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """Get the test database URL."""
    return (
        f"postgresql://{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}"
        f"@{os.environ['POSTGRES_HOST']}:{os.environ['POSTGRES_PORT']}"
        f"/{os.environ['POSTGRES_DB']}"
    )


@pytest.fixture(scope="session")
def test_engine(test_database_url: str):
    """Create a test database engine."""
    try:
        engine = create_engine(test_database_url, echo=False)
        yield engine
        engine.dispose()
    except Exception:
        # If database is not available, use SQLite for testing
        engine = create_engine("sqlite:///:memory:", echo=False)
        yield engine
        engine.dispose()


@pytest.fixture(scope="session")
def test_tables(test_engine):
    """Create test tables."""
    from shared.python.db.models import Base

    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session(test_engine, test_tables) -> Generator[Session, None, None]:
    """Create a database session for tests."""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def sample_story_data() -> dict:
    """Sample story data for testing."""
    return {
        "reddit_id": f"test_{uuid.uuid4().hex[:8]}",
        "subreddit": "scifi",
        "title": "Test Story Title",
        "content": "This is a test story content. " * 100,  # ~3500 chars
        "author": "test_author",
        "score": 100,
        "url": "https://reddit.com/r/scifi/comments/test",
        "char_count": 3500,
        "status": "pending",
    }


@pytest.fixture
def sample_long_story_data() -> dict:
    """Sample long story data (>5000 chars) for testing multi-part splitting."""
    return {
        "reddit_id": f"test_long_{uuid.uuid4().hex[:8]}",
        "subreddit": "fantasy",
        "title": "Long Test Story Title",
        "content": "This is a much longer test story content that needs to be split. " * 200,
        "author": "test_author",
        "score": 500,
        "url": "https://reddit.com/r/fantasy/comments/test_long",
        "char_count": 13400,
        "status": "pending",
    }


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    with patch("redis.Redis") as mock:
        mock_client = MagicMock()
        mock.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_elasticsearch():
    """Mock Elasticsearch client."""
    with patch("elasticsearch.Elasticsearch") as mock:
        mock_client = MagicMock()
        mock.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_celery_app():
    """Mock Celery app for testing tasks."""
    with patch("shared.python.celery_app.app.app") as mock:
        mock.send_task = MagicMock()
        yield mock


@pytest.fixture
def mock_smtp():
    """Mock SMTP for email testing."""
    with patch("smtplib.SMTP") as mock:
        mock_server = MagicMock()
        mock.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock.return_value.__exit__ = MagicMock(return_value=False)
        yield mock_server


@pytest.fixture
def mock_praw():
    """Mock PRAW (Reddit API) client."""
    with patch("praw.Reddit") as mock:
        mock_reddit = MagicMock()
        mock.return_value = mock_reddit
        yield mock_reddit


@pytest.fixture
def mock_ollama():
    """Mock Ollama client."""
    with patch("httpx.Client") as mock:
        mock_client = MagicMock()
        mock.return_value = mock_client
        yield mock_client


class FactoryBase:
    """Base class for test factories."""

    @staticmethod
    def generate_uuid() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def generate_timestamp() -> datetime:
        return datetime.utcnow()


class StoryFactory(FactoryBase):
    """Factory for creating Story test objects."""

    @classmethod
    def create(cls, db_session: Session, **kwargs) -> Story:
        from shared.python.db import Story

        defaults = {
            "reddit_id": f"factory_{uuid.uuid4().hex[:8]}",
            "subreddit": "scifi",
            "title": "Factory Generated Story",
            "content": "This is factory generated content for testing.",
            "author": "factory_user",
            "score": 50,
            "char_count": 50,
            "status": "pending",
        }
        defaults.update(kwargs)

        story = Story(**defaults)
        db_session.add(story)
        db_session.flush()
        return story


class ScriptFactory(FactoryBase):
    """Factory for creating Script test objects."""

    @classmethod
    def create(cls, db_session: Session, story: Story, **kwargs) -> Script:
        from shared.python.db import Script

        defaults = {
            "story_id": story.id,
            "part_number": 1,
            "total_parts": 1,
            "hook": "Did you hear about...",
            "content": "Factory generated script content.",
            "cta": "Follow for more!",
            "char_count": 50,
            "voice_gender": "male",
        }
        defaults.update(kwargs)

        script = Script(**defaults)
        db_session.add(script)
        db_session.flush()
        return script


@pytest.fixture
def story_factory():
    """Provide StoryFactory for tests."""
    return StoryFactory


@pytest.fixture
def script_factory():
    """Provide ScriptFactory for tests."""
    return ScriptFactory
