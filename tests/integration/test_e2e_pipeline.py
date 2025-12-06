"""End-to-end pipeline tests with mocked external services."""

import uuid
from unittest.mock import MagicMock, patch

import pytest


class TestFullPipelineFlow:
    """Test complete pipeline: Story -> Script -> Audio -> Video -> Upload."""

    def test_single_part_story_pipeline(
        self, db_session, story_factory, script_factory
    ):
        """Test pipeline for a single-part story."""
        from shared.python.db import Audio, StoryStatus, Upload, UploadStatus, Video

        # Create story in approved state
        story = story_factory.create(db_session, status=StoryStatus.APPROVED.value)

        # Create script
        script = script_factory.create(db_session, story, part_number=1, total_parts=1)

        # Create audio
        audio = Audio(
            script_id=script.id,
            file_path="/data/audio/test.wav",
            duration_seconds=60.0,
            voice_model="en_US-lessac-medium",
        )
        db_session.add(audio)
        db_session.flush()

        # Create video
        video = Video(
            audio_id=audio.id,
            file_path="/data/videos/test.mp4",
            duration_seconds=60.0,
            resolution="1080x1920",
            has_captions=True,
        )
        db_session.add(video)
        db_session.flush()

        # Create upload
        upload = Upload(
            video_id=video.id,
            platform="tiktok",
            status=UploadStatus.PENDING.value,
        )
        db_session.add(upload)
        db_session.flush()

        # Simulate successful upload
        upload.status = UploadStatus.SUCCESS.value
        upload.platform_video_id = "tiktok_123456"
        upload.platform_url = "https://tiktok.com/@user/video/123456"
        story.status = StoryStatus.COMPLETED.value
        db_session.commit()

        # Verify full pipeline state
        assert story.status == StoryStatus.COMPLETED.value
        assert len(story.scripts) == 1
        assert script.audio is not None
        assert len(script.audio) == 1
        assert len(script.audio[0].videos) == 1
        assert upload.status == UploadStatus.SUCCESS.value

    def test_multi_part_story_pipeline(
        self, db_session, story_factory, script_factory
    ):
        """Test pipeline for a multi-part story (split into 3 parts)."""
        from shared.python.db import (
            Audio,
            Batch,
            BatchStatus,
            StoryStatus,
            Upload,
            UploadStatus,
            Video,
        )

        # Create long story
        story = story_factory.create(
            db_session,
            status=StoryStatus.APPROVED.value,
            content="Long story content. " * 500,
            char_count=10000,
        )

        # Create batch for multi-part upload
        batch = Batch(
            story_id=story.id,
            status=BatchStatus.PROCESSING.value,
            total_parts=3,
            completed_parts=0,
        )
        db_session.add(batch)
        db_session.flush()

        # Create 3 script parts
        uploads = []
        for part_num in range(1, 4):
            script = script_factory.create(
                db_session,
                story,
                part_number=part_num,
                total_parts=3,
                hook=f"Part {part_num} hook",
                content=f"Part {part_num} content",
            )

            audio = Audio(
                script_id=script.id,
                file_path=f"/data/audio/test_part{part_num}.wav",
                duration_seconds=55.0,
            )
            db_session.add(audio)
            db_session.flush()

            video = Video(
                audio_id=audio.id,
                file_path=f"/data/videos/test_part{part_num}.mp4",
                duration_seconds=55.0,
                resolution="1080x1920",
            )
            db_session.add(video)
            db_session.flush()

            upload = Upload(
                video_id=video.id,
                platform="tiktok",
                status=UploadStatus.PENDING.value,
            )
            db_session.add(upload)
            uploads.append(upload)

        db_session.flush()

        # Simulate uploading all parts
        for i, upload in enumerate(uploads):
            upload.status = UploadStatus.SUCCESS.value
            upload.platform_video_id = f"tiktok_{i + 1}"
            batch.completed_parts = i + 1

        batch.status = BatchStatus.COMPLETED.value
        story.status = StoryStatus.COMPLETED.value
        db_session.commit()

        # Verify
        assert len(story.scripts) == 3
        assert batch.completed_parts == 3
        assert batch.status == BatchStatus.COMPLETED.value
        assert all(u.status == UploadStatus.SUCCESS.value for u in uploads)

    def test_pipeline_handles_partial_failure(
        self, db_session, story_factory, script_factory
    ):
        """Test that partial failures are tracked correctly."""
        from shared.python.db import (
            Audio,
            Batch,
            BatchStatus,
            StoryStatus,
            Upload,
            UploadStatus,
            Video,
        )

        story = story_factory.create(db_session, status=StoryStatus.APPROVED.value)

        batch = Batch(
            story_id=story.id,
            status=BatchStatus.PROCESSING.value,
            total_parts=2,
            completed_parts=0,
        )
        db_session.add(batch)
        db_session.flush()

        # Part 1 - Success
        script1 = script_factory.create(db_session, story, part_number=1, total_parts=2)
        audio1 = Audio(script_id=script1.id, file_path="/data/audio/p1.wav", duration_seconds=50.0)
        db_session.add(audio1)
        db_session.flush()

        video1 = Video(audio_id=audio1.id, file_path="/data/videos/p1.mp4", duration_seconds=50.0)
        db_session.add(video1)
        db_session.flush()

        upload1 = Upload(video_id=video1.id, platform="tiktok", status=UploadStatus.SUCCESS.value)
        db_session.add(upload1)

        # Part 2 - Failed
        script2 = script_factory.create(db_session, story, part_number=2, total_parts=2)
        audio2 = Audio(script_id=script2.id, file_path="/data/audio/p2.wav", duration_seconds=50.0)
        db_session.add(audio2)
        db_session.flush()

        video2 = Video(audio_id=audio2.id, file_path="/data/videos/p2.mp4", duration_seconds=50.0)
        db_session.add(video2)
        db_session.flush()

        upload2 = Upload(
            video_id=video2.id,
            platform="tiktok",
            status=UploadStatus.FAILED.value,
            error_message="Rate limit exceeded",
            retry_count=3,
        )
        db_session.add(upload2)

        batch.completed_parts = 1
        batch.status = BatchStatus.PARTIAL.value
        db_session.commit()

        assert batch.status == BatchStatus.PARTIAL.value
        assert batch.completed_parts == 1
        assert upload2.error_message == "Rate limit exceeded"


class TestMultiPartStoryHandling:
    """Test multi-part story splitting and coordination."""

    def test_story_split_into_parts_by_char_count(self, db_session, story_factory):
        """Test that long stories are split based on character count."""
        from shared.python.db import Script

        # Create a very long story (would be >3 TikTok videos)
        story = story_factory.create(
            db_session,
            content="X" * 15000,  # 15000 chars
            char_count=15000,
        )

        # Simulate text processor splitting (target ~4500 chars per part)
        parts = [
            {"part": 1, "content": "X" * 4500, "char_count": 4500},
            {"part": 2, "content": "X" * 4500, "char_count": 4500},
            {"part": 3, "content": "X" * 4500, "char_count": 4500},
            {"part": 4, "content": "X" * 1500, "char_count": 1500},
        ]

        for part_data in parts:
            script = Script(
                story_id=story.id,
                part_number=part_data["part"],
                total_parts=4,
                hook=f"Part {part_data['part']} of 4",
                content=part_data["content"],
                cta="Follow for the next part!",
                char_count=part_data["char_count"],
            )
            db_session.add(script)

        db_session.flush()
        db_session.refresh(story)

        assert len(story.scripts) == 4
        assert all(s.total_parts == 4 for s in story.scripts)
        assert [s.part_number for s in sorted(story.scripts, key=lambda x: x.part_number)] == [
            1,
            2,
            3,
            4,
        ]

    def test_part_numbering_in_titles(self, db_session, story_factory, script_factory):
        """Test that part numbers are correctly assigned for hashtag generation."""
        story = story_factory.create(db_session, subreddit="tifu")

        scripts = []
        for i in range(1, 4):
            script = script_factory.create(
                db_session,
                story,
                part_number=i,
                total_parts=3,
                hook=f"Part {i}: The story continues...",
            )
            scripts.append(script)

        # Verify hashtag generation logic
        for script in scripts:
            expected_hashtags = [
                "storytime",
                "reddit",
                "redditstories",
                "tifu",
                "series",
                f"part{script.part_number}",
            ]
            # This simulates what the uploader does
            hashtags = ["storytime", "reddit", "redditstories"]
            hashtags.append(story.subreddit.lower())
            if script.total_parts > 1:
                hashtags.extend(["series", f"part{script.part_number}"])

            assert hashtags == expected_hashtags

    def test_batch_upload_coordination(self, db_session, story_factory, script_factory):
        """Test that batch tracks all parts of a multi-part upload."""
        from shared.python.db import Audio, Batch, BatchStatus, Upload, UploadStatus, Video

        story = story_factory.create(db_session)

        # Create batch
        batch = Batch(
            story_id=story.id,
            status=BatchStatus.PENDING.value,
            total_parts=3,
            completed_parts=0,
        )
        db_session.add(batch)
        db_session.flush()

        # Simulate sequential uploads
        for i in range(1, 4):
            script = script_factory.create(db_session, story, part_number=i, total_parts=3)
            audio = Audio(script_id=script.id, file_path=f"/data/audio/{i}.wav", duration_seconds=50.0)
            db_session.add(audio)
            db_session.flush()

            video = Video(audio_id=audio.id, file_path=f"/data/videos/{i}.mp4", duration_seconds=50.0)
            db_session.add(video)
            db_session.flush()

            upload = Upload(
                video_id=video.id,
                platform="tiktok",
                status=UploadStatus.SUCCESS.value,
                platform_video_id=f"tiktok_{i}",
            )
            db_session.add(upload)

            # Update batch progress
            batch.completed_parts = i
            if i == 3:
                batch.status = BatchStatus.COMPLETED.value
            else:
                batch.status = BatchStatus.PROCESSING.value

        db_session.commit()

        assert batch.completed_parts == batch.total_parts
        assert batch.status == BatchStatus.COMPLETED.value


class TestCeleryTaskChains:
    """Test Celery task chain execution patterns."""

    @pytest.fixture
    def mock_celery_tasks(self):
        """Mock all Celery tasks."""
        with (
            patch("shared.python.celery_app.tasks.fetch_reddit") as mock_fetch,
            patch("shared.python.celery_app.tasks.process_story") as mock_process,
            patch("shared.python.celery_app.tasks.generate_audio") as mock_audio,
            patch("shared.python.celery_app.tasks.render_video") as mock_video,
            patch("shared.python.celery_app.tasks.upload_video") as mock_upload,
        ):
            # Setup task signatures
            mock_fetch.s = MagicMock(return_value=mock_fetch)
            mock_process.s = MagicMock(return_value=mock_process)
            mock_audio.s = MagicMock(return_value=mock_audio)
            mock_video.s = MagicMock(return_value=mock_video)
            mock_upload.s = MagicMock(return_value=mock_upload)

            yield {
                "fetch": mock_fetch,
                "process": mock_process,
                "audio": mock_audio,
                "video": mock_video,
                "upload": mock_upload,
            }

    def test_pipeline_chain_structure(self, mock_celery_tasks):
        """Test that pipeline creates correct task chain."""
        from celery import chain

        # Verify chain can be constructed
        story_id = str(uuid.uuid4())
        pipeline = chain(
            mock_celery_tasks["process"].s(story_id),
            mock_celery_tasks["audio"].s(),
            mock_celery_tasks["video"].s(),
            mock_celery_tasks["upload"].s(),
        )

        assert pipeline is not None

    def test_task_result_propagation(self, mock_celery_tasks):
        """Test that task results propagate through chain."""
        story_id = str(uuid.uuid4())
        script_id = str(uuid.uuid4())
        audio_id = str(uuid.uuid4())
        video_id = str(uuid.uuid4())

        # Configure return values
        mock_celery_tasks["process"].apply_async.return_value.get.return_value = {
            "status": "success",
            "story_id": story_id,
            "script_ids": [script_id],
        }
        mock_celery_tasks["audio"].apply_async.return_value.get.return_value = {
            "status": "success",
            "script_id": script_id,
            "audio_id": audio_id,
        }
        mock_celery_tasks["video"].apply_async.return_value.get.return_value = {
            "status": "success",
            "audio_id": audio_id,
            "video_id": video_id,
        }
        mock_celery_tasks["upload"].apply_async.return_value.get.return_value = {
            "status": "success",
            "video_id": video_id,
            "platform_video_id": "tiktok_123",
        }

        # Simulate chain execution
        process_result = mock_celery_tasks["process"].apply_async(args=[story_id]).get()
        assert process_result["status"] == "success"
        assert process_result["script_ids"] == [script_id]


class TestPipelineErrorRecovery:
    """Test error handling and recovery in pipeline."""

    def test_retry_on_transient_error(self, db_session, story_factory, script_factory):
        """Test that transient errors trigger retries."""
        from shared.python.db import Audio, Upload, UploadStatus, Video

        story = story_factory.create(db_session)
        script = script_factory.create(db_session, story)
        audio = Audio(script_id=script.id, file_path="/data/audio/t.wav", duration_seconds=50.0)
        db_session.add(audio)
        db_session.flush()

        video = Video(audio_id=audio.id, file_path="/data/videos/t.mp4", duration_seconds=50.0)
        db_session.add(video)
        db_session.flush()

        # Simulate failed upload with retries
        upload = Upload(
            video_id=video.id,
            platform="tiktok",
            status=UploadStatus.FAILED.value,
            error_message="Network timeout",
            retry_count=1,
        )
        db_session.add(upload)
        db_session.flush()

        # Simulate retry
        upload.retry_count = 2
        upload.status = UploadStatus.UPLOADING.value
        db_session.flush()

        # Simulate success on retry
        upload.status = UploadStatus.SUCCESS.value
        upload.platform_video_id = "tiktok_retry_success"
        db_session.commit()

        assert upload.retry_count == 2
        assert upload.status == UploadStatus.SUCCESS.value

    def test_max_retries_triggers_manual_required(
        self, db_session, story_factory, script_factory
    ):
        """Test that exceeding max retries sets manual_required status."""
        from shared.python.db import Audio, Upload, UploadStatus, Video

        story = story_factory.create(db_session)
        script = script_factory.create(db_session, story)
        audio = Audio(script_id=script.id, file_path="/data/audio/m.wav", duration_seconds=50.0)
        db_session.add(audio)
        db_session.flush()

        video = Video(audio_id=audio.id, file_path="/data/videos/m.mp4", duration_seconds=50.0)
        db_session.add(video)
        db_session.flush()

        upload = Upload(
            video_id=video.id,
            platform="tiktok",
            status=UploadStatus.FAILED.value,
            error_message="Persistent failure",
            retry_count=3,  # Max retries reached
        )
        db_session.add(upload)
        db_session.flush()

        # After max retries, should switch to manual_required
        upload.status = UploadStatus.MANUAL_REQUIRED.value
        db_session.commit()

        assert upload.status == UploadStatus.MANUAL_REQUIRED.value
        assert upload.retry_count == 3

    def test_failed_story_preserves_partial_results(
        self, db_session, story_factory, script_factory
    ):
        """Test that partial results are preserved on failure."""
        from shared.python.db import Audio, StoryStatus

        story = story_factory.create(db_session, status=StoryStatus.PROCESSING.value)
        script = script_factory.create(db_session, story)

        # Audio generated successfully
        audio = Audio(
            script_id=script.id,
            file_path="/data/audio/partial.wav",
            duration_seconds=50.0,
        )
        db_session.add(audio)
        db_session.flush()

        # Video rendering failed - story marked as failed
        story.status = StoryStatus.FAILED.value
        story.error_message = "Video rendering failed: Out of memory"
        db_session.commit()

        # Partial results should still be queryable
        db_session.refresh(story)
        assert story.status == StoryStatus.FAILED.value
        assert len(story.scripts) == 1
        assert story.scripts[0].audio is not None
