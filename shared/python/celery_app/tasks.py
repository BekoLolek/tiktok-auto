"""Celery tasks for TikTok Auto pipeline."""

import logging
import os
from typing import Any

from celery import chain

from .app import app

logger = logging.getLogger(__name__)


class TransientError(Exception):
    """Errors that should trigger a retry."""

    pass


class PermanentError(Exception):
    """Errors that should not retry."""

    pass


@app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(TransientError,),
    retry_backoff=True,
    retry_backoff_max=600,
)
def fetch_reddit(self, subreddits: list[str], limit: int = 50) -> dict[str, Any]:
    """
    Fetch stories from Reddit.

    Args:
        subreddits: List of subreddit names to fetch from
        limit: Maximum number of posts to fetch per subreddit

    Returns:
        Dict with fetch results
    """
    logger.info(f"Fetching from subreddits: {subreddits}, limit: {limit}")

    try:
        # Import here to avoid circular imports
        from services.reddit_fetch.src.reddit_client import RedditClient

        client = RedditClient()
        results = client.fetch_posts(subreddits, limit)

        logger.info(f"Fetched {len(results)} posts")
        return {"status": "success", "posts_fetched": len(results)}

    except Exception as e:
        logger.error(f"Reddit fetch failed: {e}")
        raise TransientError(str(e)) from e


@app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    autoretry_for=(TransientError,),
    retry_backoff=True,
)
def process_story(self, story_id: str) -> dict[str, Any]:
    """
    Process a story: add hook/CTA, split if needed.

    Args:
        story_id: UUID of the story to process

    Returns:
        Dict with processing results including script IDs
    """
    from shared.python.db import StoryStatus, update_story_progress

    logger.info(f"Processing story: {story_id}")

    # Update status to scripting
    update_story_progress(story_id, StoryStatus.SCRIPTING.value, "Generating scripts with LLM...")

    try:
        # Import here to avoid circular imports
        from services.text_processor.src.processor import TextProcessor

        processor = TextProcessor()
        script_ids = processor.process_story(story_id)

        # Update progress
        update_story_progress(
            story_id,
            StoryStatus.SCRIPTING.value,
            f"Scripts created: {len(script_ids)} part(s)"
        )

        logger.info(f"Story {story_id} processed into {len(script_ids)} scripts")
        return {"status": "success", "story_id": story_id, "script_ids": script_ids}

    except Exception as e:
        logger.error(f"Story processing failed: {e}")
        update_story_progress(story_id, StoryStatus.FAILED.value, f"Scripting failed: {e}")
        raise TransientError(str(e)) from e


@app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    autoretry_for=(TransientError,),
    retry_backoff=True,
)
def generate_audio(self, script_id: str) -> dict[str, Any]:
    """
    Generate audio narration for a script.

    Args:
        script_id: UUID of the script to narrate

    Returns:
        Dict with audio generation results including audio ID
    """
    logger.info(f"Generating audio for script: {script_id}")

    try:
        # Import here to avoid circular imports
        from services.tts_service.src.synthesizer import TTSSynthesizer

        synthesizer = TTSSynthesizer()
        audio_id = synthesizer.synthesize(script_id)

        logger.info(f"Audio generated for script {script_id}: {audio_id}")
        return {"status": "success", "script_id": script_id, "audio_id": str(audio_id)}

    except Exception as e:
        logger.error(f"Audio generation failed: {e}")
        raise TransientError(str(e)) from e


@app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(TransientError,),
    retry_backoff=True,
    soft_time_limit=900,  # 15 minutes for CPU Whisper transcription
    time_limit=1800,  # 30 minutes hard limit
)
def render_video(self, audio_id: str) -> dict[str, Any]:
    """
    Render video with background, audio, and captions.

    Args:
        audio_id: UUID of the audio to use

    Returns:
        Dict with video rendering results including video ID
    """
    logger.info(f"Rendering video for audio: {audio_id}")

    try:
        # Import here to avoid circular imports
        from services.video_renderer.src.renderer import VideoRenderer

        renderer = VideoRenderer()
        video_id = renderer.render(audio_id)

        logger.info(f"Video rendered for audio {audio_id}: {video_id}")
        return {"status": "success", "audio_id": audio_id, "video_id": str(video_id)}

    except Exception as e:
        logger.error(f"Video rendering failed: {e}")
        raise TransientError(str(e)) from e


def _do_upload_video(video_id: str, batch_id: str | None = None) -> dict[str, Any]:
    """
    Core upload logic - can be called directly without Celery.

    Args:
        video_id: UUID of the video to upload
        batch_id: Optional batch ID for multi-part uploads

    Returns:
        Dict with upload results
    """
    import httpx

    from shared.python.db import Video, get_session

    logger.info(f"Uploading video: {video_id}")

    try:
        # Get video details from database
        with get_session() as session:
            video = session.get(Video, video_id)
            if not video:
                raise ValueError(f"Video {video_id} not found")

            video_data = {
                "id": str(video.id),
                "file_path": video.file_path,
            }

        # Call the uploader service
        uploader_url = os.getenv("UPLOADER_URL", "http://uploader:3000")

        with httpx.Client(timeout=300.0) as client:
            response = client.post(
                f"{uploader_url}/upload",
                json={
                    "videoId": video_data["id"],
                    "videoPath": video_data["file_path"],
                },
            )
            response.raise_for_status()
            result = response.json()

        if result.get("status") == "success":
            logger.info(f"Video {video_id} uploaded successfully: {result.get('platformUrl')}")
            return {
                "status": "success",
                "video_id": video_id,
                "platform_video_id": result.get("platformVideoId"),
                "url": result.get("platformUrl"),
            }
        elif result.get("status") == "manual_required":
            logger.warning(f"Video {video_id} requires manual upload")
            return {
                "status": "manual_required",
                "video_id": video_id,
                "reason": result.get("message"),
            }
        else:
            return {
                "status": result.get("status", "unknown"),
                "video_id": video_id,
                "reason": result.get("message"),
            }

    except Exception as e:
        logger.error(f"Upload failed: {e}")
        return {"status": "failed", "video_id": video_id, "reason": str(e)}


@app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=120,
    autoretry_for=(TransientError,),
    retry_backoff=True,
)
def upload_video(self, video_id: str, batch_id: str | None = None) -> dict[str, Any]:
    """
    Upload video to TikTok via the uploader service (Celery task wrapper).

    Args:
        video_id: UUID of the video to upload
        batch_id: Optional batch ID for multi-part uploads

    Returns:
        Dict with upload results
    """
    result = _do_upload_video(video_id, batch_id)
    if result.get("status") == "failed":
        raise TransientError(result.get("reason", "Upload failed"))
    return result


@app.task(bind=True)
def send_failure_notification(
    self, video_id: str, failure_type: str, reason: str | None = None
) -> dict[str, Any]:
    """
    Send email notification on failure.

    Args:
        video_id: UUID of the failed video
        failure_type: Type of failure
        reason: Optional failure reason

    Returns:
        Dict with notification status
    """
    logger.info(f"Sending failure notification for video: {video_id}")

    try:
        from shared.python.email.notifier import EmailNotifier

        notifier = EmailNotifier()
        notifier.send_failure_alert(video_id, failure_type, reason)

        return {"status": "sent", "video_id": video_id}

    except Exception as e:
        logger.error(f"Failed to send notification: {e}")
        return {"status": "failed", "error": str(e)}


def run_full_pipeline(story_id: str) -> Any:
    """
    Run the full pipeline for a story.

    This creates a Celery chain that processes the story through
    all stages: text processing -> audio generation -> video rendering -> upload.

    Args:
        story_id: UUID of the story to process

    Returns:
        AsyncResult of the pipeline chain
    """
    # First, process the story to get scripts
    pipeline = chain(
        process_story.s(story_id),
        process_scripts_to_videos.s(),
        upload_batch.s(),
    )

    return pipeline.apply_async()


@app.task(bind=True, soft_time_limit=1800, time_limit=3600)  # 30 min soft, 60 min hard
def process_scripts_to_videos(self, process_result: dict[str, Any]) -> dict[str, Any]:
    """
    Process all scripts from a story into videos.

    Args:
        process_result: Result from process_story task

    Returns:
        Dict with all video IDs
    """
    from services.tts_service.src.synthesizer import TTSSynthesizer
    from services.video_renderer.src.renderer import VideoRenderer
    from shared.python.db import StoryStatus, update_story_progress

    script_ids = process_result.get("script_ids", [])
    story_id = process_result.get("story_id")
    total_parts = len(script_ids)

    if not script_ids:
        return {"status": "no_scripts", "video_ids": []}

    # Update status to generating audio
    update_story_progress(
        story_id,
        StoryStatus.GENERATING_AUDIO.value,
        f"Generating audio for {total_parts} part(s)..."
    )

    # Generate audio for each script (call directly, not as subtask)
    synthesizer = TTSSynthesizer()
    audio_ids = []
    for i, script_id in enumerate(script_ids, 1):
        logger.info(f"Generating audio {i}/{total_parts} for script {script_id}")
        update_story_progress(
            story_id,
            StoryStatus.GENERATING_AUDIO.value,
            f"Generating audio {i}/{total_parts}..."
        )
        audio_id = synthesizer.synthesize(script_id)
        audio_ids.append(audio_id)

    # Now render videos for each audio
    renderer = VideoRenderer()
    video_ids = []
    for i, audio_id in enumerate(audio_ids, 1):
        logger.info(f"Rendering video {i}/{total_parts} for audio {audio_id}")
        update_story_progress(
            story_id,
            StoryStatus.RENDERING_VIDEO.value,
            f"Rendering video {i}/{total_parts}..."
        )
        video_id = renderer.render(audio_id)
        video_ids.append(video_id)

    return {
        "status": "success",
        "story_id": story_id,
        "video_ids": video_ids,
        "total_parts": total_parts,
    }


@app.task(bind=True)
def upload_batch(self, videos_result: dict[str, Any]) -> dict[str, Any]:
    """
    Upload all videos in a batch.

    Args:
        videos_result: Result from process_scripts_to_videos

    Returns:
        Dict with upload results for all videos
    """
    from shared.python.db import StoryStatus, update_story_progress

    video_ids = videos_result.get("video_ids", [])
    story_id = videos_result.get("story_id")

    if not video_ids:
        return {"status": "no_videos", "uploads": []}

    # Update status to uploading
    update_story_progress(
        story_id,
        StoryStatus.UPLOADING.value,
        f"Uploading {len(video_ids)} video(s)..."
    )

    # Create batch record
    from shared.python.db import Batch, BatchStatus, get_session

    with get_session() as session:
        batch = Batch(
            story_id=story_id,
            status=BatchStatus.PROCESSING.value,
            total_parts=len(video_ids),
            completed_parts=0,
        )
        session.add(batch)
        session.flush()
        batch_id = str(batch.id)

    # Upload each video (call directly to avoid Celery subtask blocking)
    upload_results = []
    for i, video_id in enumerate(video_ids, 1):
        logger.info(f"Uploading video {i}/{len(video_ids)}: {video_id}")
        update_story_progress(
            story_id,
            StoryStatus.UPLOADING.value,
            f"Uploading video {i}/{len(video_ids)}..."
        )
        result = _do_upload_video(video_id, batch_id)
        upload_results.append(result)

    # Update batch status
    successful = sum(1 for r in upload_results if r.get("status") == "success")
    with get_session() as session:
        batch = session.query(Batch).filter_by(id=batch_id).first()
        if batch:
            batch.completed_parts = successful
            if successful == len(video_ids):
                batch.status = BatchStatus.COMPLETED.value
            elif successful > 0:
                batch.status = BatchStatus.PARTIAL.value
            else:
                batch.status = BatchStatus.FAILED.value

    # Update story final status
    if successful == len(video_ids):
        update_story_progress(
            story_id,
            StoryStatus.COMPLETED.value,
            f"All {successful} video(s) uploaded successfully!"
        )
    elif successful > 0:
        update_story_progress(
            story_id,
            StoryStatus.COMPLETED.value,
            f"Partial: {successful}/{len(video_ids)} uploaded"
        )
    else:
        update_story_progress(
            story_id,
            StoryStatus.FAILED.value,
            "Upload failed for all videos"
        )

    return {
        "status": "success" if successful == len(video_ids) else "partial",
        "batch_id": batch_id,
        "uploads": upload_results,
        "successful": successful,
        "total": len(video_ids),
    }


# =============================================================================
# Scheduled Tasks
# =============================================================================


@app.task(bind=True)
def scheduled_fetch_reddit(self) -> dict[str, Any]:
    """
    Scheduled task to fetch new stories from Reddit.

    Reads subreddit list from environment or uses defaults.
    """
    import os

    subreddits_env = os.getenv("REDDIT_SUBREDDITS", "scifi,fantasy,tifu,nosleep")
    subreddits = [s.strip() for s in subreddits_env.split(",")]
    limit = int(os.getenv("REDDIT_FETCH_LIMIT", "25"))

    logger.info(f"Scheduled fetch from subreddits: {subreddits}")
    return fetch_reddit.apply_async(args=[subreddits, limit]).get()


@app.task(bind=True)
def process_pending_uploads(self) -> dict[str, Any]:
    """
    Process videos that are ready for upload.

    Checks for videos with completed rendering that haven't been uploaded yet.
    """
    logger.info("Processing pending uploads...")

    from shared.python.db import Upload, UploadStatus, Video, get_session

    processed = 0
    with get_session() as session:
        # Find videos without uploads or with pending uploads
        from sqlalchemy import select

        # Get videos that have no upload record yet
        subquery = select(Upload.video_id)
        stmt = select(Video).where(~Video.id.in_(subquery))
        videos_without_uploads = session.execute(stmt).scalars().all()

        for video in videos_without_uploads:
            logger.info(f"Queuing upload for video: {video.id}")
            upload_video.delay(str(video.id))
            processed += 1

        # Also check pending uploads
        pending_uploads = (
            session.query(Upload).filter_by(status=UploadStatus.PENDING.value).limit(10).all()
        )

        for upload in pending_uploads:
            logger.info(f"Requeuing pending upload: {upload.id}")
            upload_video.delay(str(upload.video_id))
            processed += 1

    return {"status": "success", "processed": processed}


@app.task(bind=True)
def retry_failed_uploads(self) -> dict[str, Any]:
    """
    Retry uploads that failed but haven't exceeded max retries.
    """
    logger.info("Retrying failed uploads...")

    from shared.python.db import Upload, UploadStatus, get_session

    max_retries = int(os.getenv("MAX_UPLOAD_RETRIES", "3"))
    retried = 0

    with get_session() as session:
        failed_uploads = (
            session.query(Upload)
            .filter(
                Upload.status == UploadStatus.FAILED.value,
                Upload.retry_count < max_retries,
            )
            .all()
        )

        for upload in failed_uploads:
            logger.info(f"Retrying upload {upload.id} (attempt {upload.retry_count + 1})")
            upload.status = UploadStatus.PENDING.value
            upload_video.delay(str(upload.video_id))
            retried += 1

        session.commit()

    return {"status": "success", "retried": retried}


@app.task(bind=True)
def cleanup_old_files(self) -> dict[str, Any]:
    """
    Clean up old processed files (audio, video) after successful upload.

    Respects retention period from environment.
    """
    import os
    from datetime import datetime, timedelta
    from pathlib import Path

    logger.info("Cleaning up old files...")

    retention_days = int(os.getenv("FILE_RETENTION_DAYS", "7"))
    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

    from shared.python.db import Upload, UploadStatus, get_session

    deleted_files = 0
    deleted_records = 0

    with get_session() as session:
        # Find successfully uploaded videos older than retention period
        old_uploads = (
            session.query(Upload)
            .filter(
                Upload.status == UploadStatus.SUCCESS.value,
                Upload.uploaded_at < cutoff_date,
            )
            .all()
        )

        for upload in old_uploads:
            video = upload.video
            if video:
                # Delete video file
                if video.file_path:
                    video_path = Path(video.file_path)
                    if video_path.exists():
                        video_path.unlink()
                        deleted_files += 1
                        logger.info(f"Deleted video file: {video.file_path}")

                # Delete audio file
                audio = video.audio
                if audio and audio.file_path:
                    audio_path = Path(audio.file_path)
                    if audio_path.exists():
                        audio_path.unlink()
                        deleted_files += 1
                        logger.info(f"Deleted audio file: {audio.file_path}")

    logger.info(f"Cleanup complete: {deleted_files} files deleted")
    return {"status": "success", "deleted_files": deleted_files, "deleted_records": deleted_records}


@app.task(bind=True)
def process_dead_letter_queue(self) -> dict[str, Any]:
    """
    Process tasks that have failed permanently and are in the dead letter queue.

    Marks associated stories as failed and sends notifications.
    """
    import redis

    logger.info("Processing dead letter queue...")

    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))

    try:
        r = redis.Redis(host=redis_host, port=redis_port, db=0)

        # Check for failed tasks in Celery's default dead letter patterns
        dead_letter_keys = r.keys("celery-task-meta-*")
        processed = 0

        for key in dead_letter_keys[:100]:  # Process up to 100 at a time
            try:
                task_data = r.get(key)
                if task_data:
                    import json

                    data = json.loads(task_data)
                    if data.get("status") == "FAILURE":
                        task_id = data.get("task_id")
                        error = data.get("result", "Unknown error")

                        logger.warning(f"Dead letter task {task_id}: {error}")

                        # Send notification about permanent failure
                        send_failure_notification.delay(
                            video_id=task_id or "unknown",
                            failure_type="dead_letter",
                            reason=str(error)[:500],
                        )
                        processed += 1

                        # Remove processed dead letter
                        r.delete(key)

            except Exception as e:
                logger.error(f"Error processing dead letter {key}: {e}")

        return {"status": "success", "processed": processed}

    except Exception as e:
        logger.error(f"Dead letter queue processing failed: {e}")
        return {"status": "error", "error": str(e)}


@app.task(bind=True)
def process_approved_stories(self) -> dict[str, Any]:
    """
    Find approved stories and start their pipeline processing.
    """
    logger.info("Processing approved stories...")

    from shared.python.db import Story, StoryStatus, get_session

    processed = 0
    with get_session() as session:
        approved_stories = (
            session.query(Story)
            .filter_by(status=StoryStatus.APPROVED.value)
            .limit(5)
            .all()
        )

        for story in approved_stories:
            logger.info(f"Starting pipeline for story: {story.id}")
            story.status = StoryStatus.PROCESSING.value
            run_full_pipeline(str(story.id))
            processed += 1

        session.commit()

    return {"status": "success", "processed": processed}


# =============================================================================
# Error Handling Tasks
# =============================================================================


@app.task(bind=True, max_retries=0)
def handle_pipeline_failure(
    self, story_id: str, stage: str, error_message: str
) -> dict[str, Any]:
    """
    Handle pipeline failure by updating story status and notifying.

    Args:
        story_id: UUID of the failed story
        stage: Pipeline stage where failure occurred
        error_message: Error description

    Returns:
        Dict with handling status
    """
    logger.error(f"Pipeline failure for story {story_id} at {stage}: {error_message}")

    from shared.python.db import Story, StoryStatus, get_session

    with get_session() as session:
        story = session.query(Story).filter_by(id=story_id).first()
        if story:
            story.status = StoryStatus.FAILED.value
            story.error_message = f"[{stage}] {error_message}"[:1000]
            session.commit()

    # Send notification
    send_failure_notification.delay(
        video_id=story_id,
        failure_type=f"pipeline_failure_{stage}",
        reason=error_message,
    )

    return {"status": "handled", "story_id": story_id, "stage": stage}
