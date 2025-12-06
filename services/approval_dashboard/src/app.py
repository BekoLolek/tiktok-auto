"""Approval Dashboard FastAPI application."""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, select, update

from shared.python.celery_app import celery_app
from shared.python.db import (
    Audio,
    Batch,
    BatchStatus,
    Script,
    Story,
    StoryStatus,
    Upload,
    UploadStatus,
    Video,
    get_session,
)

from .config import get_settings
from .logs import LogService

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)
settings = get_settings()

# Templates directory
TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    logger.info("Dashboard starting up")
    yield
    logger.info("Dashboard shutting down")


app = FastAPI(
    title="TikTok Auto - Approval Dashboard",
    description="Story approval and pipeline monitoring dashboard",
    version="1.0.0",
    lifespan=lifespan,
)


# Custom Jinja2 filters
def format_datetime(value: datetime | None) -> str:
    """Format datetime for display."""
    if value is None:
        return "N/A"
    return value.strftime("%Y-%m-%d %H:%M:%S")


def truncate_text(value: str, length: int = 200) -> str:
    """Truncate text with ellipsis."""
    if len(value) <= length:
        return value
    return value[:length] + "..."


templates.env.filters["datetime"] = format_datetime
templates.env.filters["truncate"] = truncate_text


def story_to_dict(story: Story) -> dict:
    """Convert Story object to dictionary to avoid DetachedInstanceError."""
    return {
        "id": story.id,
        "reddit_id": story.reddit_id,
        "subreddit": story.subreddit,
        "title": story.title,
        "content": story.content,
        "author": story.author,
        "score": story.score,
        "url": story.url,
        "char_count": story.char_count,
        "status": story.status,
        "error_message": story.error_message,
        "rejection_reason": story.rejection_reason,
        "created_at": story.created_at,
        "updated_at": story.updated_at,
    }


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard view."""
    with get_session() as session:
        # Get counts by status
        pending_count = session.execute(
            select(func.count(Story.id)).where(Story.status == StoryStatus.PENDING.value)
        ).scalar()

        approved_count = session.execute(
            select(func.count(Story.id)).where(Story.status == StoryStatus.APPROVED.value)
        ).scalar()

        processing_count = session.execute(
            select(func.count(Story.id)).where(
                Story.status == StoryStatus.PROCESSING.value
            )
        ).scalar()

        completed_count = session.execute(
            select(func.count(Story.id)).where(
                Story.status == StoryStatus.COMPLETED.value
            )
        ).scalar()

        failed_count = session.execute(
            select(func.count(Story.id)).where(Story.status == StoryStatus.FAILED.value)
        ).scalar()

        # Get recent stories
        recent_stories_orm = session.execute(
            select(Story).order_by(desc(Story.created_at)).limit(10)
        ).scalars().all()

        # Convert to dictionaries to avoid DetachedInstanceError
        recent_stories = [story_to_dict(s) for s in recent_stories_orm]

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "pending_count": pending_count,
            "approved_count": approved_count,
            "processing_count": processing_count,
            "completed_count": completed_count,
            "failed_count": failed_count,
            "recent_stories": recent_stories,
        },
    )


@app.get("/stories", response_class=HTMLResponse)
async def list_stories(
    request: Request,
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
):
    """List stories with optional status filter."""
    with get_session() as session:
        query = select(Story)

        if status:
            query = query.where(Story.status == status)

        # Get total count
        count_query = select(func.count(Story.id))
        if status:
            count_query = count_query.where(Story.status == status)
        total_count = session.execute(count_query).scalar()

        # Paginate
        offset = (page - 1) * settings.stories_per_page
        query = (
            query.order_by(desc(Story.created_at))
            .offset(offset)
            .limit(settings.stories_per_page)
        )

        stories_orm = session.execute(query).scalars().all()

        total_pages = (total_count + settings.stories_per_page - 1) // settings.stories_per_page

        # Convert to dictionaries to avoid DetachedInstanceError
        stories = [story_to_dict(s) for s in stories_orm]

    return templates.TemplateResponse(
        "stories.html",
        {
            "request": request,
            "stories": stories,
            "current_status": status,
            "current_page": page,
            "total_pages": total_pages,
            "total_count": total_count,
            "statuses": [s.value for s in StoryStatus],
        },
    )


@app.get("/stories/new", response_class=HTMLResponse)
async def new_story_form(request: Request):
    """Display form for manual story submission."""
    return templates.TemplateResponse(
        "story_submit.html",
        {
            "request": request,
        },
    )


@app.post("/stories/new")
async def submit_story(
    title: str = Form(...),
    content: str = Form(...),
    subreddit: str = Form(default="manual"),
    author: str = Form(default=""),
):
    """Handle manual story submission."""
    # Generate unique ID for manual stories
    manual_id = f"manual_{uuid.uuid4().hex[:12]}"

    # Calculate character count
    char_count = len(content)

    with get_session() as session:
        story = Story(
            reddit_id=manual_id,
            subreddit=subreddit.strip() or "manual",
            title=title.strip(),
            content=content.strip(),
            author=author.strip() if author else None,
            score=0,
            url=None,
            char_count=char_count,
            status=StoryStatus.PENDING.value,
        )
        session.add(story)
        session.commit()

        story_id = story.id
        logger.info(f"Manual story submitted: {story_id} - {title[:50]}")

    return RedirectResponse(url=f"/stories/{story_id}", status_code=303)


@app.get("/stories/{story_id}", response_class=HTMLResponse)
async def view_story(request: Request, story_id: str):
    """View a single story with full content."""
    with get_session() as session:
        story = session.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

        # Get related data
        scripts = story.scripts if story.scripts else []
        batches = (
            session.execute(select(Batch).where(Batch.story_id == story_id))
            .scalars()
            .all()
        )

        # Expunge objects so they can be used outside session
        session.expunge_all()

    return templates.TemplateResponse(
        "story_detail.html",
        {
            "request": request,
            "story": story,
            "scripts": scripts,
            "batches": batches,
        },
    )


@app.post("/stories/{story_id}/approve")
async def approve_story(story_id: str):
    """Approve a story for processing."""
    with get_session() as session:
        story = session.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

        if story.status != StoryStatus.PENDING.value:
            raise HTTPException(
                status_code=400, detail=f"Story is not pending (status: {story.status})"
            )

        # Update status
        session.execute(
            update(Story)
            .where(Story.id == story_id)
            .values(status=StoryStatus.APPROVED.value)
        )
        session.commit()

        # Trigger processing pipeline
        celery_app.send_task("shared.python.celery_app.tasks.process_story", args=[story_id])

        logger.info(f"Story {story_id} approved and queued for processing")

    return RedirectResponse(url=f"/stories/{story_id}", status_code=303)


@app.post("/stories/{story_id}/reject")
async def reject_story(story_id: str, reason: str = Form(default="")):
    """Reject a story."""
    with get_session() as session:
        story = session.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

        # Update status
        session.execute(
            update(Story)
            .where(Story.id == story_id)
            .values(status=StoryStatus.REJECTED.value, rejection_reason=reason)
        )
        session.commit()

        logger.info(f"Story {story_id} rejected: {reason}")

    return RedirectResponse(url="/stories?status=pending", status_code=303)


@app.post("/stories/{story_id}/retry")
async def retry_story(story_id: str):
    """Retry a failed story."""
    with get_session() as session:
        story = session.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

        if story.status != StoryStatus.FAILED.value:
            raise HTTPException(status_code=400, detail="Story is not failed")

        # Reset status to approved
        session.execute(
            update(Story)
            .where(Story.id == story_id)
            .values(status=StoryStatus.APPROVED.value, error_message=None)
        )
        session.commit()

        # Re-trigger processing
        celery_app.send_task("shared.python.celery_app.tasks.process_story", args=[story_id])

        logger.info(f"Story {story_id} queued for retry")

    return RedirectResponse(url=f"/stories/{story_id}", status_code=303)


@app.get("/logs", response_class=HTMLResponse)
async def view_logs(
    request: Request,
    service: str | None = Query(None),
    level: str | None = Query(None),
    story_id: str | None = Query(None),
    page: int = Query(1, ge=1),
):
    """View logs from Elasticsearch."""
    log_service = LogService(settings.elasticsearch_url)

    try:
        logs, total = await log_service.search_logs(
            service=service,
            level=level,
            story_id=story_id,
            page=page,
            per_page=settings.logs_per_page,
        )
    except Exception as e:
        logger.warning(f"Failed to fetch logs: {e}")
        logs = []
        total = 0

    total_pages = (total + settings.logs_per_page - 1) // settings.logs_per_page

    return templates.TemplateResponse(
        "logs.html",
        {
            "request": request,
            "logs": logs,
            "current_service": service,
            "current_level": level,
            "current_story_id": story_id,
            "current_page": page,
            "total_pages": total_pages,
            "total_count": total,
            "services": [
                "reddit-fetch",
                "text-processor",
                "tts-service",
                "video-renderer",
                "uploader",
            ],
            "levels": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        },
    )


@app.get("/batches", response_class=HTMLResponse)
async def list_batches(
    request: Request,
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
):
    """List batches (multi-part story uploads)."""
    with get_session() as session:
        query = select(Batch)

        if status:
            query = query.where(Batch.status == status)

        # Get total count
        count_query = select(func.count(Batch.id))
        if status:
            count_query = count_query.where(Batch.status == status)
        total_count = session.execute(count_query).scalar()

        # Paginate
        offset = (page - 1) * settings.stories_per_page
        query = (
            query.order_by(desc(Batch.created_at))
            .offset(offset)
            .limit(settings.stories_per_page)
        )

        batches = session.execute(query).scalars().all()
        total_pages = (total_count + settings.stories_per_page - 1) // settings.stories_per_page

        # Expunge objects so they can be used outside session
        session.expunge_all()

    return templates.TemplateResponse(
        "batches.html",
        {
            "request": request,
            "batches": batches,
            "current_status": status,
            "current_page": page,
            "total_pages": total_pages,
            "total_count": total_count,
            "statuses": [s.value for s in BatchStatus],
        },
    )


@app.get("/downloads", response_class=HTMLResponse)
async def list_downloads(
    request: Request,
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
):
    """List videos available for manual download/upload."""
    with get_session() as session:
        # Get videos that need manual upload
        query = (
            select(Video)
            .join(Upload, Video.id == Upload.video_id)
            .where(Upload.status == UploadStatus.MANUAL_REQUIRED.value)
        )

        if status:
            query = query.where(Upload.status == status)

        # Get total count
        count_query = (
            select(func.count(Video.id))
            .join(Upload, Video.id == Upload.video_id)
            .where(Upload.status == UploadStatus.MANUAL_REQUIRED.value)
        )
        total_count = session.execute(count_query).scalar()

        # Paginate
        offset = (page - 1) * settings.stories_per_page
        query = query.order_by(desc(Video.created_at)).offset(offset).limit(settings.stories_per_page)

        videos = session.execute(query).scalars().all()
        total_pages = (total_count + settings.stories_per_page - 1) // settings.stories_per_page

        # Get upload info for each video
        video_uploads = []
        for video in videos:
            upload = session.execute(
                select(Upload).where(Upload.video_id == video.id)
            ).scalar_one_or_none()

            # Get story info through the chain
            audio = session.get(Audio, video.audio_id)
            script = session.get(Script, audio.script_id) if audio else None
            story = session.get(Story, script.story_id) if script else None

            video_uploads.append({
                "video": video,
                "upload": upload,
                "story": story,
                "script": script,
            })

        # Expunge objects so they can be used outside session
        session.expunge_all()

    return templates.TemplateResponse(
        "downloads.html",
        {
            "request": request,
            "video_uploads": video_uploads,
            "current_status": status,
            "current_page": page,
            "total_pages": total_pages,
            "total_count": total_count,
        },
    )


@app.get("/downloads/{video_id}/file")
async def download_video_file(video_id: str):
    """Download a video file for manual upload."""
    with get_session() as session:
        video = session.execute(
            select(Video).where(Video.id == video_id)
        ).scalar_one_or_none()

        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        file_path = Path(video.file_path)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Video file not found on disk")

        return FileResponse(
            path=str(file_path),
            filename=file_path.name,
            media_type="video/mp4",
        )


@app.post("/downloads/{video_id}/mark-uploaded")
async def mark_video_uploaded(
    video_id: str,
    platform_url: str = Form(default=""),
):
    """Mark a video as manually uploaded."""
    with get_session() as session:
        upload = session.execute(
            select(Upload).where(Upload.video_id == video_id)
        ).scalar_one_or_none()

        if not upload:
            raise HTTPException(status_code=404, detail="Upload record not found")

        session.execute(
            update(Upload)
            .where(Upload.video_id == video_id)
            .values(
                status=UploadStatus.SUCCESS.value,
                platform_url=platform_url if platform_url else None,
                uploaded_at=datetime.utcnow(),
            )
        )
        session.commit()

        logger.info(f"Video {video_id} marked as manually uploaded")

    return RedirectResponse(url="/downloads", status_code=303)


@app.get("/health")
async def health_check():
    """Health check endpoint with database connectivity."""
    health_status = {
        "status": "healthy",
        "service": "approval-dashboard",
        "checks": {},
    }

    # Check database connectivity
    try:
        with get_session() as session:
            session.execute(select(func.count(Story.id)))
        health_status["checks"]["database"] = "ok"
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["checks"]["database"] = f"error: {e!s}"

    status_code = 200 if health_status["status"] == "healthy" else 503

    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=health_status)

    return health_status
