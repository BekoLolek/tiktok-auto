"""Tests for database models."""

import uuid
from datetime import datetime

import pytest


class TestStoryModel:
    """Tests for the Story model."""

    def test_create_story(self, db_session, sample_story_data):
        """Test creating a new story."""
        from shared.python.db import Story, StoryStatus

        story = Story(**sample_story_data)
        db_session.add(story)
        db_session.flush()

        assert story.id is not None
        assert story.reddit_id == sample_story_data["reddit_id"]
        assert story.status == StoryStatus.PENDING.value
        assert story.created_at is not None

    def test_story_status_enum(self):
        """Test StoryStatus enum values."""
        from shared.python.db import StoryStatus

        assert StoryStatus.PENDING.value == "pending"
        assert StoryStatus.APPROVED.value == "approved"
        assert StoryStatus.REJECTED.value == "rejected"
        assert StoryStatus.PROCESSING.value == "processing"
        assert StoryStatus.COMPLETED.value == "completed"
        assert StoryStatus.FAILED.value == "failed"

    def test_story_unique_reddit_id(self, db_session, sample_story_data):
        """Test that reddit_id must be unique."""
        from shared.python.db import Story
        from sqlalchemy.exc import IntegrityError

        story1 = Story(**sample_story_data)
        db_session.add(story1)
        db_session.flush()

        story2_data = sample_story_data.copy()
        story2 = Story(**story2_data)
        db_session.add(story2)

        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_story_char_count_required(self, db_session):
        """Test that char_count is required."""
        from shared.python.db import Story
        from sqlalchemy.exc import IntegrityError

        story = Story(
            reddit_id="test_no_char_count",
            subreddit="test",
            title="Test",
            content="Test content",
            # char_count is missing
        )
        db_session.add(story)

        with pytest.raises(IntegrityError):
            db_session.flush()


class TestScriptModel:
    """Tests for the Script model."""

    def test_create_script(self, db_session, story_factory, script_factory):
        """Test creating a script linked to a story."""
        from shared.python.db import Script

        story = story_factory.create(db_session)
        script = script_factory.create(db_session, story)

        assert script.id is not None
        assert script.story_id == story.id
        assert script.part_number == 1
        assert script.total_parts == 1

    def test_script_story_relationship(self, db_session, story_factory, script_factory):
        """Test the relationship between Script and Story."""
        story = story_factory.create(db_session)
        script = script_factory.create(db_session, story)

        db_session.refresh(story)
        assert len(story.scripts) == 1
        assert story.scripts[0].id == script.id

    def test_script_cascade_delete(self, db_session, story_factory, script_factory):
        """Test that scripts are deleted when story is deleted."""
        from shared.python.db import Script

        story = story_factory.create(db_session)
        script = script_factory.create(db_session, story)
        script_id = script.id

        db_session.delete(story)
        db_session.flush()

        deleted_script = db_session.get(Script, script_id)
        assert deleted_script is None

    def test_multi_part_scripts(self, db_session, story_factory, script_factory):
        """Test creating multiple script parts for one story."""
        story = story_factory.create(db_session)

        script1 = script_factory.create(
            db_session, story, part_number=1, total_parts=3, hook="Part 1 hook"
        )
        script2 = script_factory.create(
            db_session, story, part_number=2, total_parts=3, hook="Part 2 hook"
        )
        script3 = script_factory.create(
            db_session, story, part_number=3, total_parts=3, hook="Part 3 hook"
        )

        db_session.refresh(story)
        assert len(story.scripts) == 3
        assert all(s.total_parts == 3 for s in story.scripts)


class TestVoiceGenderEnum:
    """Tests for VoiceGender enum."""

    def test_voice_gender_values(self):
        """Test VoiceGender enum values."""
        from shared.python.db import VoiceGender

        assert VoiceGender.MALE.value == "male"
        assert VoiceGender.FEMALE.value == "female"


class TestBatchModel:
    """Tests for the Batch model."""

    def test_create_batch(self, db_session, story_factory):
        """Test creating a batch."""
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

        assert batch.id is not None
        assert batch.total_parts == 3
        assert batch.completed_parts == 0

    def test_batch_status_enum(self):
        """Test BatchStatus enum values."""
        from shared.python.db import BatchStatus

        assert BatchStatus.PENDING.value == "pending"
        assert BatchStatus.PROCESSING.value == "processing"
        assert BatchStatus.COMPLETED.value == "completed"
        assert BatchStatus.PARTIAL.value == "partial"
        assert BatchStatus.FAILED.value == "failed"


class TestUploadModel:
    """Tests for the Upload model."""

    def test_upload_status_enum(self):
        """Test UploadStatus enum values."""
        from shared.python.db import UploadStatus

        assert UploadStatus.PENDING.value == "pending"
        assert UploadStatus.UPLOADING.value == "uploading"
        assert UploadStatus.SUCCESS.value == "success"
        assert UploadStatus.FAILED.value == "failed"
        assert UploadStatus.MANUAL_REQUIRED.value == "manual_required"
