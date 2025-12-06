"""Database connection and session management."""

import os
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base


def get_database_url() -> str:
    """Build database URL from environment variables."""
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "tiktok_auto")
    password = os.getenv("POSTGRES_PASSWORD", "devpassword")
    db = os.getenv("POSTGRES_DB", "tiktok_auto")

    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


# Create engine with connection pooling
engine = create_engine(
    get_database_url(),
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
    echo=os.getenv("LOG_LEVEL", "INFO").upper() == "DEBUG",
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create all database tables."""
    Base.metadata.create_all(bind=engine)


def drop_db() -> None:
    """Drop all database tables (use with caution!)."""
    Base.metadata.drop_all(bind=engine)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions.

    Usage:
        with get_session() as session:
            story = session.query(Story).first()
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency for FastAPI endpoints.

    Usage:
        @app.get("/stories")
        def get_stories(db: Session = Depends(get_db)):
            return db.query(Story).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def update_story_progress(
    story_id: str, status: str, progress_info: str | None = None
) -> None:
    """
    Update story status and progress info.

    Args:
        story_id: UUID of the story
        status: New status value (from StoryStatus enum)
        progress_info: Optional progress details (e.g., "Part 2/3: generating audio")
    """
    from sqlalchemy import update

    from .models import Story

    with get_session() as session:
        stmt = update(Story).where(Story.id == story_id).values(status=status)
        if progress_info is not None:
            stmt = stmt.values(progress_info=progress_info)
        session.execute(stmt)
