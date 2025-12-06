"""Tests for Video Renderer module."""

import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock moviepy before importing renderer
sys.modules["moviepy"] = MagicMock()
sys.modules["moviepy.editor"] = MagicMock()
sys.modules["whisper"] = MagicMock()

from services.video_renderer.src.config import Settings  # noqa: E402
from services.video_renderer.src.renderer import (  # noqa: E402
    Caption,
    RenderResult,
    VideoRenderer,
    WhisperTranscriber,
)


class TestSettings:
    """Tests for Settings configuration."""

    def test_database_url(self):
        """Test database URL construction."""
        settings = Settings(
            postgres_host="db.example.com",
            postgres_port=5432,
            postgres_user="user",
            postgres_password="pass",
            postgres_db="mydb",
        )
        expected = "postgresql://user:pass@db.example.com:5432/mydb"
        assert settings.database_url == expected

    def test_default_video_settings(self):
        """Test default video settings."""
        settings = Settings()
        assert settings.video_width == 1080
        assert settings.video_height == 1920
        assert settings.video_fps == 30

    def test_paths_create_directories(self, tmp_path):
        """Test path properties create directories."""
        settings = Settings(
            background_videos_dir=str(tmp_path / "bg"),
            video_output_dir=str(tmp_path / "out"),
            temp_dir=str(tmp_path / "tmp"),
        )

        assert settings.background_path.exists()
        assert settings.output_path.exists()
        assert settings.temp_path.exists()


class TestCaption:
    """Tests for Caption dataclass."""

    def test_create_caption(self):
        """Test creating a Caption."""
        caption = Caption(
            text="Hello world",
            start_time=1.5,
            end_time=3.0,
        )

        assert caption.text == "Hello world"
        assert caption.start_time == 1.5
        assert caption.end_time == 3.0


class TestRenderResult:
    """Tests for RenderResult dataclass."""

    def test_create_result(self):
        """Test creating a RenderResult."""
        result = RenderResult(
            script_id=1,
            video_path="/data/videos/video_1.mp4",
            duration_seconds=180.5,
            width=1080,
            height=1920,
        )

        assert result.script_id == 1
        assert result.duration_seconds == 180.5
        assert result.width == 1080


class TestWhisperTranscriber:
    """Tests for WhisperTranscriber."""

    def test_init(self):
        """Test transcriber initialization."""
        transcriber = WhisperTranscriber("tiny")
        assert transcriber.model_name == "tiny"
        assert transcriber._model is None

    @patch("whisper.load_model")
    def test_model_lazy_loading(self, mock_load):
        """Test model is loaded lazily."""
        mock_load.return_value = MagicMock()

        transcriber = WhisperTranscriber("base")
        # Model not loaded yet
        mock_load.assert_not_called()

        # Access model property
        _ = transcriber.model
        mock_load.assert_called_once_with("base")

    @patch("whisper.load_model")
    def test_transcribe_with_segments(self, mock_load):
        """Test transcription with segment data."""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "segments": [
                {
                    "text": "Hello world",
                    "start": 0.0,
                    "end": 2.0,
                    "words": [],
                },
                {
                    "text": "This is a test",
                    "start": 2.0,
                    "end": 4.0,
                    "words": [],
                },
            ]
        }
        mock_load.return_value = mock_model

        transcriber = WhisperTranscriber("base")
        captions = transcriber.transcribe("/path/to/audio.wav")

        assert len(captions) == 2
        assert captions[0].text == "Hello world"
        assert captions[0].start_time == 0.0
        assert captions[1].text == "This is a test"

    @patch("whisper.load_model")
    def test_transcribe_with_word_timestamps(self, mock_load):
        """Test transcription with word-level timestamps."""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "segments": [
                {
                    "text": "Hello world this is a test",
                    "start": 0.0,
                    "end": 3.0,
                    "words": [
                        {"word": "Hello", "start": 0.0, "end": 0.5},
                        {"word": "world", "start": 0.5, "end": 1.0},
                        {"word": "this", "start": 1.0, "end": 1.5},
                        {"word": "is", "start": 1.5, "end": 1.8},
                        {"word": "a", "start": 1.8, "end": 2.0},
                        {"word": "test.", "start": 2.0, "end": 3.0},
                    ],
                }
            ]
        }
        mock_load.return_value = mock_model

        transcriber = WhisperTranscriber("base")
        captions = transcriber.transcribe("/path/to/audio.wav")

        # Should chunk into groups
        assert len(captions) >= 1


class TestVideoRenderer:
    """Tests for VideoRenderer class."""

    @pytest.fixture
    def settings(self, tmp_path):
        """Create test settings."""
        return Settings(
            video_width=1080,
            video_height=1920,
            background_videos_dir=str(tmp_path / "bg"),
            video_output_dir=str(tmp_path / "out"),
            temp_dir=str(tmp_path / "tmp"),
        )

    @pytest.fixture
    def renderer(self, settings):
        """Create renderer with test settings."""
        return VideoRenderer(settings=settings)

    def test_init_with_settings(self, renderer, settings):
        """Test renderer initializes with provided settings."""
        assert renderer.settings == settings

    @patch("services.video_renderer.src.renderer.get_session")
    def test_render_video_script_not_found(self, mock_get_session, renderer):
        """Test rendering non-existent script."""
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.get.return_value = None

        with pytest.raises(ValueError, match="Script 999 not found"):
            renderer.render_video(999)

    @patch("services.video_renderer.src.renderer.get_session")
    def test_render_video_no_audio(self, mock_get_session, renderer):
        """Test rendering script without audio."""
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_script = MagicMock()
        mock_session.get.return_value = mock_script
        mock_session.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(ValueError, match="No audio found"):
            renderer.render_video(1)

    def test_create_solid_background(self, renderer):
        """Test creating solid color background."""
        with patch("services.video_renderer.src.renderer.ColorClip") as mock_color:
            mock_clip = MagicMock()
            mock_color.return_value = mock_clip

            result = renderer._create_solid_background(60.0)

            mock_color.assert_called_once_with(
                size=(1080, 1920),
                color=(20, 20, 30),
                duration=60.0,
            )
            assert result == mock_clip

    def test_resize_and_crop_wider_video(self, renderer):
        """Test resizing a wider video."""
        mock_clip = MagicMock()
        mock_clip.w = 1920
        mock_clip.h = 1080
        mock_clip.resize.return_value = mock_clip
        mock_clip.crop.return_value = mock_clip

        renderer._resize_and_crop(mock_clip)

        mock_clip.resize.assert_called_once()
        mock_clip.crop.assert_called_once()

    def test_resize_and_crop_taller_video(self, renderer):
        """Test resizing a taller video."""
        mock_clip = MagicMock()
        mock_clip.w = 1080
        mock_clip.h = 2400  # Taller than TikTok ratio
        mock_clip.resize.return_value = mock_clip
        mock_clip.crop.return_value = mock_clip

        renderer._resize_and_crop(mock_clip)

        mock_clip.resize.assert_called_once()
        mock_clip.crop.assert_called_once()

    def test_create_caption_clips_empty(self, renderer):
        """Test creating caption clips with no captions."""
        result = renderer._create_caption_clips([], 60.0)
        assert result == []

    @patch("services.video_renderer.src.renderer.TextClip")
    def test_create_caption_clips_single(self, mock_text_clip, renderer):
        """Test creating a single caption clip."""
        mock_clip = MagicMock()
        mock_clip.set_position.return_value = mock_clip
        mock_clip.set_start.return_value = mock_clip
        mock_clip.set_duration.return_value = mock_clip
        mock_text_clip.return_value = mock_clip

        captions = [Caption(text="Test caption", start_time=1.0, end_time=3.0)]
        result = renderer._create_caption_clips(captions, 60.0)

        assert len(result) == 1
        mock_text_clip.assert_called_once()
        mock_clip.set_start.assert_called_once_with(1.0)
        mock_clip.set_duration.assert_called_once_with(2.0)

    @patch("services.video_renderer.src.renderer.TextClip")
    def test_create_caption_clips_handles_errors(self, mock_text_clip, renderer):
        """Test caption creation handles errors gracefully."""
        mock_text_clip.side_effect = Exception("Font not found")

        captions = [Caption(text="Test", start_time=0.0, end_time=1.0)]
        result = renderer._create_caption_clips(captions, 60.0)

        # Should return empty list, not raise
        assert result == []

    @patch("services.video_renderer.src.renderer.get_session")
    def test_save_video_record(self, mock_get_session, renderer):
        """Test saving video record to database."""
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        result = RenderResult(
            script_id=1,
            video_path="/data/videos/video_1.mp4",
            duration_seconds=120.0,
            width=1080,
            height=1920,
        )

        renderer._save_video_record(result)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
