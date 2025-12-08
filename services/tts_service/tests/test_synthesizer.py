"""Tests for TTS synthesizer module."""

from unittest.mock import MagicMock, patch

import pytest

from services.tts_service.src.config import Settings
from services.tts_service.src.synthesizer import (
    AudioResult,
    GTTSClient,
    TTSSynthesizer,
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

    def test_default_voices(self):
        """Test default voice settings."""
        settings = Settings()
        assert settings.male_voice == "en-US-GuyNeural"
        assert settings.female_voice == "en-US-JennyNeural"

    def test_audio_speed_default(self):
        """Test default audio speed setting."""
        settings = Settings()
        assert settings.audio_speed == 1.25

    def test_audio_path_creates_directory(self, tmp_path):
        """Test audio_path creates directory if needed."""
        settings = Settings(audio_output_dir=str(tmp_path / "audio"))
        path = settings.audio_path
        assert path.exists()
        assert path.is_dir()


class TestAudioResult:
    """Tests for AudioResult dataclass."""

    def test_create_result(self):
        """Test creating an AudioResult."""
        result = AudioResult(
            script_id="123e4567-e89b-12d3-a456-426614174000",
            audio_id="223e4567-e89b-12d3-a456-426614174001",
            audio_path="/data/audio/script_123.mp3",
            duration_seconds=120.5,
            voice_model="gtts-en",
        )

        assert result.script_id == "123e4567-e89b-12d3-a456-426614174000"
        assert result.duration_seconds == 120.5
        assert result.voice_model == "gtts-en"


class TestGTTSClient:
    """Tests for GTTSClient."""

    def test_init(self):
        """Test client initialization."""
        client = GTTSClient()
        # GTTSClient has no parameters in __init__
        assert client is not None

    @patch("services.tts_service.src.synthesizer.gTTS")
    def test_synthesize(self, mock_gtts_class, tmp_path):
        """Test synthesize creates audio file."""
        mock_tts = MagicMock()
        mock_gtts_class.return_value = mock_tts

        client = GTTSClient()
        output_path = str(tmp_path / "test.mp3")
        client.synthesize("Hello world", "en", output_path)

        mock_gtts_class.assert_called_once_with(text="Hello world", lang="en", slow=False)
        mock_tts.save.assert_called_once_with(output_path)


class TestTTSSynthesizer:
    """Tests for TTSSynthesizer class."""

    @pytest.fixture
    def settings(self, tmp_path):
        """Create test settings."""
        return Settings(
            audio_output_dir=str(tmp_path / "audio"),
            audio_speed=1.0,  # No speed adjustment for simpler testing
        )

    @pytest.fixture
    def synthesizer(self, settings):
        """Create synthesizer with test settings."""
        return TTSSynthesizer(settings=settings)

    def test_init_with_settings(self, synthesizer, settings):
        """Test synthesizer initializes with provided settings."""
        assert synthesizer.settings == settings

    def test_client_lazy_loading(self, synthesizer):
        """Test GTTSClient is lazily loaded."""
        assert synthesizer._client is None
        client = synthesizer.client
        assert client is not None
        assert isinstance(client, GTTSClient)

    def test_build_narration_text_full(self, synthesizer):
        """Test building narration text with all parts."""
        script_data = {
            "id": "123",
            "hook": "You won't believe this.",
            "content": "The main story content.",
            "cta": "Follow for more!",
        }

        result = synthesizer._build_narration_text_from_dict(script_data)

        assert "You won't believe this." in result
        assert "The main story content." in result
        assert "Follow for more!" in result

    def test_build_narration_text_no_hook(self, synthesizer):
        """Test building narration text without hook."""
        script_data = {
            "id": "123",
            "hook": None,
            "content": "The main story content.",
            "cta": "Follow for more!",
        }

        result = synthesizer._build_narration_text_from_dict(script_data)

        assert "The main story content." in result
        assert "Follow for more!" in result

    def test_build_narration_text_strips_hashtags(self, synthesizer):
        """Test hashtags are stripped from narration."""
        script_data = {
            "id": "123",
            "hook": "Amazing story!",
            "content": "The content here.",
            "cta": "Follow for more! #storytime #reddit",
        }

        result = synthesizer._build_narration_text_from_dict(script_data)

        assert "#storytime" not in result
        assert "#reddit" not in result
        assert "Follow for more!" in result

    @patch("services.tts_service.src.synthesizer.get_session")
    def test_synthesize_script_not_found(self, mock_get_session, synthesizer):
        """Test synthesizing non-existent script."""
        mock_session = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_session)
        mock_context.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_context
        mock_session.get.return_value = None

        with pytest.raises(ValueError, match="Script 999 not found"):
            synthesizer.synthesize("999")

    @patch("services.tts_service.src.synthesizer.MP3")
    @patch("services.tts_service.src.synthesizer.Audio")
    @patch("services.tts_service.src.synthesizer.get_session")
    def test_synthesize_success(
        self, mock_get_session, mock_audio_class, mock_mp3, synthesizer
    ):
        """Test successful script synthesis."""
        # Set up mock session
        mock_session = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_session)
        mock_context.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_context

        # Mock script
        mock_script = MagicMock()
        mock_script.id = "123e4567-e89b-12d3-a456-426614174000"
        mock_script.voice_gender = "male"
        mock_script.hook = "Hook"
        mock_script.content = "Content"
        mock_script.cta = "CTA"
        mock_session.get.return_value = mock_script

        # Mock MP3 duration
        mock_mp3_instance = MagicMock()
        mock_mp3_instance.info.length = 10.5
        mock_mp3.return_value = mock_mp3_instance

        # Mock Audio record
        mock_audio = MagicMock()
        mock_audio.id = "223e4567-e89b-12d3-a456-426614174001"
        mock_audio_class.return_value = mock_audio

        # Mock the client
        synthesizer._client = MagicMock()

        result = synthesizer.synthesize("123e4567-e89b-12d3-a456-426614174000")

        assert result == str(mock_audio.id)
        synthesizer._client.synthesize.assert_called_once()

    def test_get_audio_duration_fallback(self, synthesizer, tmp_path):
        """Test duration fallback when file cannot be read."""
        # Non-existent file should return 0.0
        duration = synthesizer._get_audio_duration("/nonexistent/path.mp3")
        assert duration == 0.0
