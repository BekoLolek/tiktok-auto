"""Approval Dashboard FastAPI application."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, select, update

from shared.python.celery_app import celery_app
from shared.python.db import (
    Batch,
    BatchStatus,
    Story,
    StoryStatus,
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
        recent_stories = session.execute(
            select(Story).order_by(desc(Story.created_at)).limit(10)
        ).scalars().all()

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

        stories = session.execute(query).scalars().all()

        total_pages = (total_count + settings.stories_per_page - 1) // settings.stories_per_page

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


@app.get("/stories/{story_id}", response_class=HTMLResponse)
async def view_story(request: Request, story_id: int):
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
async def approve_story(story_id: int):
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
        celery_app.send_task("process_story", args=[story_id])

        logger.info(f"Story {story_id} approved and queued for processing")

    return RedirectResponse(url=f"/stories/{story_id}", status_code=303)


@app.post("/stories/{story_id}/reject")
async def reject_story(story_id: int, reason: str = Form(default="")):
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
async def retry_story(story_id: int):
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
        celery_app.send_task("process_story", args=[story_id])

        logger.info(f"Story {story_id} queued for retry")

    return RedirectResponse(url=f"/stories/{story_id}", status_code=303)


@app.get("/logs", response_class=HTMLResponse)
async def view_logs(
    request: Request,
    service: str | None = Query(None),
    level: str | None = Query(None),
    story_id: int | None = Query(None),
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


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "approval-dashboard"}
