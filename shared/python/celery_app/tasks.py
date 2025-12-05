"""Celery tasks for TikTok Auto pipeline."""

import logging
from typing import Any

from celery import chain, group
from celery.exceptions import MaxRetriesExceededError

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
    logger.info(f"Processing story: {story_id}")

    try:
        # Import here to avoid circular imports
        from services.text_processor.src.processor import TextProcessor

        processor = TextProcessor()
        script_ids = processor.process(story_id)

        logger.info(f"Story {story_id} processed into {len(script_ids)} scripts")
        return {"status": "success", "story_id": story_id, "script_ids": script_ids}

    except Exception as e:
        logger.error(f"Story processing failed: {e}")
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
        return {"status": "success", "script_id": script_id, "audio_id": audio_id}

    except Exception as e:
        logger.error(f"Audio generation failed: {e}")
        raise TransientError(str(e)) from e


@app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(TransientError,),
    retry_backoff=True,
    soft_time_limit=300,
    time_limit=600,
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
        return {"status": "success", "audio_id": audio_id, "video_id": video_id}

    except Exception as e:
        logger.error(f"Video rendering failed: {e}")
        raise TransientError(str(e)) from e


@app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=120,
    autoretry_for=(TransientError,),
    retry_backoff=True,
)
def upload_video(self, video_id: str, batch_id: str | None = None) -> dict[str, Any]:
    """
    Upload video to TikTok.

    Args:
        video_id: UUID of the video to upload
        batch_id: Optional batch ID for multi-part uploads

    Returns:
        Dict with upload results
    """
    logger.info(f"Uploading video: {video_id}")

    try:
        # Import here to avoid circular imports
        from services.uploader.src.tiktok import TikTokUploader

        uploader = TikTokUploader()
        result = uploader.upload(video_id, batch_id)

        if result["status"] == "success":
            logger.info(f"Video {video_id} uploaded successfully: {result['url']}")
        elif result["status"] == "manual_required":
            logger.warning(f"Video {video_id} requires manual upload")
            # Send email notification
            send_failure_notification.delay(video_id, "manual_required", result.get("reason"))

        return result

    except MaxRetriesExceededError:
        logger.error(f"Upload failed after max retries: {video_id}")
        send_failure_notification.delay(video_id, "max_retries_exceeded", "Upload failed")
        return {"status": "failed", "video_id": video_id, "reason": "max_retries_exceeded"}

    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise TransientError(str(e)) from e


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


@app.task(bind=True)
def process_scripts_to_videos(self, process_result: dict[str, Any]) -> dict[str, Any]:
    """
    Process all scripts from a story into videos.

    Args:
        process_result: Result from process_story task

    Returns:
        Dict with all video IDs
    """
    script_ids = process_result.get("script_ids", [])

    if not script_ids:
        return {"status": "no_scripts", "video_ids": []}

    # Create a group of tasks for parallel processing
    audio_tasks = group(generate_audio.s(sid) for sid in script_ids)

    # Execute audio generation
    audio_results = audio_tasks.apply_async().get()

    # Now render videos for each audio
    video_ids = []
    for result in audio_results:
        if result.get("status") == "success":
            audio_id = result["audio_id"]
            video_result = render_video.apply_async(args=[audio_id]).get()
            if video_result.get("status") == "success":
                video_ids.append(video_result["video_id"])

    return {
        "status": "success",
        "story_id": process_result.get("story_id"),
        "video_ids": video_ids,
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
    video_ids = videos_result.get("video_ids", [])
    story_id = videos_result.get("story_id")

    if not video_ids:
        return {"status": "no_videos", "uploads": []}

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

    # Upload each video
    upload_results = []
    for video_id in video_ids:
        result = upload_video.apply_async(args=[video_id, batch_id]).get()
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

    return {
        "status": "success" if successful == len(video_ids) else "partial",
        "batch_id": batch_id,
        "uploads": upload_results,
        "successful": successful,
        "total": len(video_ids),
    }
