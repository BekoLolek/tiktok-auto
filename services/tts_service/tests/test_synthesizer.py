"""Tests for TTS synthesizer module."""

import io
import wave
from unittest.mock import MagicMock, patch

import pytest

from services.tts_service.src.config import Settings
from services.tts_service.src.synthesizer import (
    AudioResult,
    PiperClient,
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
        assert settings.male_voice == "en_US-lessac-medium"
        assert settings.female_voice == "en_US-amy-medium"

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
            script_id=1,
            audio_path="/data/audio/script_1.wav",
            duration_seconds=120.5,
            sample_rate=22050,
            voice="en_US-lessac-medium",
        )

        assert result.script_id == 1
        assert result.duration_seconds == 120.5
        assert result.voice == "en_US-lessac-medium"


class TestPiperClient:
    """Tests for PiperClient."""

    def test_init(self):
        """Test client initialization."""
        client = PiperClient("localhost", 10200)
        assert client.host == "localhost"
        assert client.port == 10200

    @patch("socket.socket")
    def test_health_check_success(self, mock_socket_class):
        """Test health check when Piper is available."""
        mock_socket = MagicMock()
        mock_socket_class.return_value.__enter__ = MagicMock(return_value=mock_socket)
        mock_socket_class.return_value.__exit__ = MagicMock(return_value=False)

        client = PiperClient("localhost", 10200)
        assert client.health_check() is True

    @patch("socket.socket")
    def test_health_check_failure(self, mock_socket_class):
        """Test health check when Piper is unavailable."""
        import socket

        mock_socket = MagicMock()
        mock_socket.connect.side_effect = socket.error("Connection refused")
        mock_socket_class.return_value.__enter__ = MagicMock(return_value=mock_socket)
        mock_socket_class.return_value.__exit__ = MagicMock(return_value=False)

        client = PiperClient("localhost", 10200)
        assert client.health_check() is False


class TestTTSSynthesizer:
    """Tests for TTSSynthesizer class."""

    @pytest.fixture
    def settings(self, tmp_path):
        """Create test settings."""
        return Settings(
            piper_host="localhost",
            piper_port=10200,
            audio_output_dir=str(tmp_path / "audio"),
        )

    @pytest.fixture
    def synthesizer(self, settings):
        """Create synthesizer with test settings."""
        return TTSSynthesizer(settings=settings)

    def test_init_with_settings(self, synthesizer, settings):
        """Test synthesizer initializes with provided settings."""
        assert synthesizer.settings == settings

    def test_get_voice_male(self, synthesizer):
        """Test voice selection for male."""
        voice = synthesizer._get_voice("male")
        assert voice == "en_US-lessac-medium"

    def test_get_voice_female(self, synthesizer):
        """Test voice selection for female."""
        voice = synthesizer._get_voice("female")
        assert voice == "en_US-amy-medium"

    def test_get_voice_default(self, synthesizer):
        """Test voice selection defaults to male."""
        voice = synthesizer._get_voice(None)
        assert voice == "en_US-lessac-medium"

    def test_build_narration_text_full(self, synthesizer):
        """Test building narration text with all parts."""
        mock_script = MagicMock()
        mock_script.hook = "You won't believe this."
        mock_script.content = "The main story content."
        mock_script.cta = "Follow for more!"

        result = synthesizer._build_narration_text(mock_script)

        assert "You won't believe this." in result
        assert "The main story content." in result
        assert "Follow for more!" in result

    def test_build_narration_text_no_hook(self, synthesizer):
        """Test building narration text without hook."""
        mock_script = MagicMock()
        mock_script.hook = None
        mock_script.content = "The main story content."
        mock_script.cta = "Follow for more!"

        result = synthesizer._build_narration_text(mock_script)

        assert "The main story content." in result
        assert "Follow for more!" in result

    def test_wrap_in_wav(self, synthesizer):
        """Test wrapping PCM data in WAV container."""
        # Create some fake PCM data
        pcm_data = b"\x00" * 4410  # 0.1 seconds at 22050 Hz, 16-bit

        result = synthesizer._wrap_in_wav(pcm_data)

        # Should start with RIFF header
        assert result.startswith(b"RIFF")

        # Should be valid WAV
        buffer = io.BytesIO(result)
        with wave.open(buffer, "rb") as wav:
            assert wav.getnchannels() == 1
            assert wav.getsampwidth() == 2
            assert wav.getframerate() == 22050

    def test_get_audio_duration(self, synthesizer):
        """Test calculating audio duration."""
        # Create a 1-second WAV file
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(22050)
            wav.writeframes(b"\x00" * 44100)  # 1 second

        duration = synthesizer._get_audio_duration(buffer.getvalue())
        assert abs(duration - 1.0) < 0.01

    def test_save_audio(self, synthesizer, tmp_path):
        """Test saving audio data to file."""
        # Create valid WAV data
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(22050)
            wav.writeframes(b"\x00" * 4410)

        audio_data = buffer.getvalue()
        path = synthesizer._save_audio(123, audio_data)

        assert path.exists()
        assert "script_123" in str(path)

    @patch("services.tts_service.src.synthesizer.get_session")
    def test_synthesize_script_not_found(self, mock_get_session, synthesizer):
        """Test synthesizing non-existent script."""
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.get.return_value = None

        with pytest.raises(ValueError, match="Script 999 not found"):
            synthesizer.synthesize_script(999)

    @patch("services.tts_service.src.synthesizer.get_session")
    @patch.object(TTSSynthesizer, "client", new_callable=lambda: property(lambda self: MagicMock()))
    def test_synthesize_script_success(self, mock_client_prop, mock_get_session, synthesizer, tmp_path):
        """Test successful script synthesis."""
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_script = MagicMock()
        mock_script.voice_gender = "male"
        mock_script.hook = "Hook"
        mock_script.content = "Content"
        mock_script.cta = "CTA"
        mock_script.story_id = 1

        mock_story = MagicMock()

        def get_side_effect(model, id):
            if hasattr(model, "__name__") and model.__name__ == "Script":
                return mock_script
            return mock_story

        mock_session.get.side_effect = [mock_script, mock_story]

        # Create valid WAV response
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(22050)
            wav.writeframes(b"\x00" * 4410)

        synthesizer._client = MagicMock()
        synthesizer._client.synthesize.return_value = buffer.getvalue()

        result = synthesizer.synthesize_script(1)

        assert result.script_id == 1
        assert result.voice == "en_US-lessac-medium"
