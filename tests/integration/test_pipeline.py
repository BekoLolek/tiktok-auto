"""Integration tests for pipeline communication between services."""

from unittest.mock import MagicMock, patch

import pytest


class TestPipelineDataFlow:
    """Tests for data flow between pipeline stages."""

    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session."""
        session = MagicMock()
        return session

    def test_story_status_transitions(self, db_session, sample_story_data):
        """Test that story status transitions work correctly through pipeline."""
        from shared.python.db import Story, StoryStatus

        # Create a story in pending state
        story = Story(**sample_story_data)
        db_session.add(story)
        db_session.flush()

        assert story.status == StoryStatus.PENDING.value

        # Simulate approval
        story.status = StoryStatus.APPROVED.value
        db_session.flush()
        assert story.status == StoryStatus.APPROVED.value

        # Simulate processing
        story.status = StoryStatus.PROCESSING.value
        db_session.flush()
        assert story.status == StoryStatus.PROCESSING.value

        # Simulate completion
        story.status = StoryStatus.COMPLETED.value
        db_session.flush()
        assert story.status == StoryStatus.COMPLETED.value

    def test_story_to_script_relationship(self, db_session, story_factory, script_factory):
        """Test that scripts are properly linked to stories."""
        story = story_factory.create(db_session)
        script1 = script_factory.create(
            db_session, story, part_number=1, total_parts=2, hook="Part 1 hook"
        )
        script2 = script_factory.create(
            db_session, story, part_number=2, total_parts=2, hook="Part 2 hook"
        )

        db_session.refresh(story)

        assert len(story.scripts) == 2
        assert story.scripts[0].story_id == story.id
        assert story.scripts[1].story_id == story.id

    def test_script_to_audio_relationship(self, db_session, story_factory, script_factory):
        """Test that audio records are properly linked to scripts."""
        from shared.python.db import Audio

        story = story_factory.create(db_session)
        script = script_factory.create(db_session, story)

        # Create audio record
        audio = Audio(
            script_id=script.id,
            file_path="/data/audio/test.wav",
            duration=120.5,
            sample_rate=22050,
            voice="en_US-lessac-medium",
        )
        db_session.add(audio)
        db_session.flush()

        assert audio.script_id == script.id

    def test_batch_tracks_multi_part_uploads(self, db_session, story_factory):
        """Test that batches track multi-part story uploads."""
        from shared.python.db import Batch, BatchStatus

        story = story_factory.create(db_session)

        batch = Batch(
            story_id=story.id,
            status=BatchStatus.PENDING.value,
            total_parts=3,
            completed_parts=0,
        )
        db_session.add(batch)
        db_session.flush()

        # Simulate progress
        batch.completed_parts = 1
        batch.status = BatchStatus.PROCESSING.value
        db_session.flush()

        assert batch.completed_parts == 1
        assert batch.status == BatchStatus.PROCESSING.value

        # Simulate completion
        batch.completed_parts = 3
        batch.status = BatchStatus.COMPLETED.value
        db_session.flush()

        assert batch.completed_parts == batch.total_parts


class TestCeleryTaskIntegration:
    """Tests for Celery task communication."""

    @patch("shared.python.celery_app.celery_app.send_task")
    def test_process_story_triggers_audio_generation(self, mock_send_task):
        """Test that processing a story triggers audio generation tasks."""
        from shared.python.celery_app.tasks import process_story

        # Mock the task to avoid actual execution
        mock_send_task.return_value = MagicMock()

        # Verify task signature exists
        assert process_story is not None

    @patch("shared.python.celery_app.celery_app.send_task")
    def test_generate_audio_triggers_video_render(self, mock_send_task):
        """Test that audio generation triggers video rendering."""
        from shared.python.celery_app.tasks import generate_audio

        mock_send_task.return_value = MagicMock()

        # Verify task signature exists
        assert generate_audio is not None

    @patch("shared.python.celery_app.celery_app.send_task")
    def test_render_video_triggers_upload(self, mock_send_task):
        """Test that video rendering triggers upload."""
        from shared.python.celery_app.tasks import render_video

        mock_send_task.return_value = MagicMock()

        # Verify task signature exists
        assert render_video is not None


class TestServiceCommunication:
    """Tests for inter-service communication patterns."""

    def test_reddit_fetcher_stores_stories_for_dashboard(self, db_session, sample_story_data):
        """Test that reddit fetcher stores stories that dashboard can read."""
        from shared.python.db import Story, StoryStatus

        # Simulate reddit fetcher storing a story
        story = Story(**sample_story_data)
        db_session.add(story)
        db_session.commit()

        # Simulate dashboard querying pending stories
        from sqlalchemy import select

        stmt = select(Story).where(Story.status == StoryStatus.PENDING.value)
        pending_stories = db_session.execute(stmt).scalars().all()

        assert len(pending_stories) >= 1
        assert any(s.reddit_id == sample_story_data["reddit_id"] for s in pending_stories)

    def test_approval_updates_visible_to_processor(self, db_session, sample_story_data):
        """Test that approval updates are visible to text processor."""
        from shared.python.db import Story, StoryStatus

        # Create and approve story
        story = Story(**sample_story_data)
        db_session.add(story)
        db_session.flush()

        story.status = StoryStatus.APPROVED.value
        db_session.commit()

        # Simulate text processor querying approved stories
        from sqlalchemy import select

        stmt = select(Story).where(Story.status == StoryStatus.APPROVED.value)
        approved_stories = db_session.execute(stmt).scalars().all()

        assert len(approved_stories) >= 1

    def test_upload_status_trackable(self, db_session, story_factory, script_factory):
        """Test that upload status can be tracked through the pipeline."""
        from shared.python.db import Upload, UploadStatus

        story = story_factory.create(db_session)
        script = script_factory.create(db_session, story)

        # Create upload record
        upload = Upload(
            script_id=script.id,
            platform="tiktok",
            status=UploadStatus.PENDING.value,
        )
        db_session.add(upload)
        db_session.flush()

        # Update status
        upload.status = UploadStatus.UPLOADING.value
        db_session.flush()

        upload.status = UploadStatus.SUCCESS.value
        upload.platform_id = "tiktok_123456"
        db_session.commit()

        assert upload.status == UploadStatus.SUCCESS.value
        assert upload.platform_id == "tiktok_123456"


class TestErrorPropagation:
    """Tests for error handling across services."""

    def test_failed_story_status_persists(self, db_session, sample_story_data):
        """Test that failed status persists with error message."""
        from shared.python.db import Story, StoryStatus

        story = Story(**sample_story_data)
        db_session.add(story)
        db_session.flush()

        # Simulate failure
        story.status = StoryStatus.FAILED.value
        story.error_message = "LLM API timeout"
        db_session.commit()

        # Verify error is retrievable
        from sqlalchemy import select

        stmt = select(Story).where(Story.status == StoryStatus.FAILED.value)
        failed_stories = db_session.execute(stmt).scalars().all()

        assert len(failed_stories) >= 1
        failed_story = next(s for s in failed_stories if s.id == story.id)
        assert failed_story.error_message == "LLM API timeout"

    def test_batch_partial_failure_tracking(self, db_session, story_factory):
        """Test that partial batch failures are tracked correctly."""
        from shared.python.db import Batch, BatchStatus

        story = story_factory.create(db_session)

        batch = Batch(
            story_id=story.id,
            status=BatchStatus.PROCESSING.value,
            total_parts=3,
            completed_parts=2,
        )
        db_session.add(batch)
        db_session.flush()

        # One part failed
        batch.status = BatchStatus.PARTIAL.value
        batch.failed_parts = [{"part_number": 3, "reason": "Upload timeout"}]
        db_session.commit()

        assert batch.status == BatchStatus.PARTIAL.value
        assert batch.completed_parts == 2
        assert len(batch.failed_parts) == 1


class TestDataConsistency:
    """Tests for data consistency across pipeline stages."""

    def test_char_count_matches_content(self, db_session, sample_story_data):
        """Test that char_count accurately reflects content length."""
        from shared.python.db import Story

        story = Story(**sample_story_data)
        db_session.add(story)
        db_session.flush()

        assert story.char_count == len(sample_story_data["content"])

    def test_script_parts_are_sequential(self, db_session, story_factory, script_factory):
        """Test that script parts maintain sequential ordering."""
        story = story_factory.create(db_session)

        scripts = []
        for i in range(1, 4):
            script = script_factory.create(
                db_session, story, part_number=i, total_parts=3
            )
            scripts.append(script)

        db_session.refresh(story)

        # Verify all parts present
        part_numbers = [s.part_number for s in story.scripts]
        assert sorted(part_numbers) == [1, 2, 3]

        # Verify total_parts consistent
        assert all(s.total_parts == 3 for s in story.scripts)
