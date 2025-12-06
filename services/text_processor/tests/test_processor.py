"""Tests for Text Processor module."""

from unittest.mock import MagicMock, patch

import pytest

from services.text_processor.src.config import Settings
from services.text_processor.src.processor import (
    OllamaClient,
    ProcessedScript,
    TextProcessor,
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

    def test_ollama_url(self):
        """Test Ollama URL construction."""
        settings = Settings(ollama_host="ollama.local", ollama_port=11435)
        assert settings.ollama_url == "http://ollama.local:11435"

    def test_default_values(self):
        """Test default settings values."""
        settings = Settings()
        assert settings.ollama_model == "llama3.1:8b"
        assert settings.max_chars_per_part == 5000
        assert settings.min_chars_for_split == 5000
        assert settings.words_per_minute == 150


class TestProcessedScript:
    """Tests for ProcessedScript dataclass."""

    def test_create_script(self):
        """Test creating a ProcessedScript."""
        script = ProcessedScript(
            part_number=1,
            total_parts=2,
            content="Test content",
            hook="Test hook",
            cta="Follow for more!",
            voice_gender="male",
            estimated_duration_seconds=180,
        )

        assert script.part_number == 1
        assert script.total_parts == 2
        assert script.voice_gender == "male"


class TestOllamaClient:
    """Tests for OllamaClient."""

    def test_init(self):
        """Test client initialization."""
        client = OllamaClient("http://localhost:11434", "llama3.1:8b")
        assert client.base_url == "http://localhost:11434"
        assert client.model == "llama3.1:8b"

    @patch("httpx.Client")
    def test_generate_success(self, mock_client_class):
        """Test successful generation."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "Generated text"}
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = OllamaClient("http://localhost:11434", "llama3.1:8b")
        result = client.generate("Test prompt")

        assert result == "Generated text"
        mock_client.post.assert_called_once()


class TestTextProcessor:
    """Tests for TextProcessor class."""

    @pytest.fixture
    def settings(self):
        """Create test settings."""
        return Settings(
            max_chars_per_part=5000,
            min_chars_for_split=5000,
            words_per_minute=150,
        )

    @pytest.fixture
    def processor(self, settings):
        """Create processor with test settings."""
        return TextProcessor(settings=settings)

    def test_init_with_settings(self, processor, settings):
        """Test processor initializes with provided settings."""
        assert processor.settings == settings

    def test_is_good_split_point_ellipsis(self, processor):
        """Test split point detection with ellipsis."""
        assert processor._is_good_split_point("And then I saw...") is True

    def test_is_good_split_point_question(self, processor):
        """Test split point detection with question."""
        assert processor._is_good_split_point("What was that sound?") is True

    def test_is_good_split_point_cliffhanger_phrase(self, processor):
        """Test split point detection with cliffhanger phrase."""
        assert processor._is_good_split_point("That's when I realized the truth.") is True
        assert processor._is_good_split_point("Suddenly everything changed.") is True

    def test_is_good_split_point_normal_sentence(self, processor):
        """Test split point detection with normal sentence."""
        assert processor._is_good_split_point("I went to the store.") is False

    def test_split_content_no_splits(self, processor):
        """Test content splitting with no split points."""
        content = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        result = processor._split_content(content, [])

        assert len(result) == 1
        assert result[0] == content

    def test_split_content_single_split(self, processor):
        """Test content splitting with single split point."""
        content = "Para one.\n\nPara two.\n\nPara three."
        result = processor._split_content(content, [0])

        assert len(result) == 2
        assert result[0] == "Para one."
        assert result[1] == "Para two.\n\nPara three."

    def test_split_content_multiple_splits(self, processor):
        """Test content splitting with multiple split points."""
        content = "Para one.\n\nPara two.\n\nPara three.\n\nPara four."
        result = processor._split_content(content, [0, 2])

        assert len(result) == 3
        assert result[0] == "Para one."
        assert result[1] == "Para two.\n\nPara three."
        assert result[2] == "Para four."

    def test_parse_json_response_valid(self, processor):
        """Test JSON parsing with valid response."""
        response = '{"hook": "Test hook", "content": "Test content", "cta": "Follow!"}'
        result = processor._parse_json_response(response)

        assert result["hook"] == "Test hook"
        assert result["content"] == "Test content"
        assert result["cta"] == "Follow!"

    def test_parse_json_response_with_text(self, processor):
        """Test JSON parsing with surrounding text."""
        response = 'Here is the response: {"hook": "Hook", "content": "Content", "cta": "CTA"} End.'
        result = processor._parse_json_response(response)

        assert result["hook"] == "Hook"
        assert result["content"] == "Content"
        assert result["cta"] == "CTA"

    def test_parse_json_response_fallback(self, processor):
        """Test JSON parsing fallback for malformed response."""
        response = "Some text without proper JSON"
        result = processor._parse_json_response(response)

        # Should return defaults
        assert "hook" in result
        assert "content" in result
        assert "cta" in result

    def test_find_split_points_short_content(self, processor):
        """Test split point finding for short content."""
        content = "Short content here."
        result = processor._find_split_points(content)

        # Should have no split points for short content
        assert result == []

    def test_find_split_points_long_content(self, processor):
        """Test split point finding for long content."""
        # Create content longer than max_chars_per_part
        para = "A" * 2000  # 2000 char paragraphs
        content = f"{para}\n\n{para}...\n\n{para}"  # ~6000 chars, ellipsis in middle

        result = processor._find_split_points(content)

        # Should find split point at the cliffhanger (ellipsis)
        assert len(result) >= 1

    @patch("services.text_processor.src.processor.get_session")
    @patch.object(TextProcessor, "_save_scripts")
    @patch.object(TextProcessor, "_process_single_part")
    def test_process_story_single_part(
        self, mock_process, mock_save, mock_get_session, processor
    ):
        """Test processing a single-part story."""
        mock_session = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_session)
        mock_context.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_context

        mock_story = MagicMock()
        mock_story.char_count = 3000  # Below min_chars_for_split
        mock_session.get.return_value = mock_story

        mock_script = ProcessedScript(
            part_number=1,
            total_parts=1,
            content="Processed",
            hook="Hook",
            cta="CTA",
            voice_gender="male",
            estimated_duration_seconds=120,
        )
        mock_process.return_value = mock_script

        processor.process_story(1)

        mock_process.assert_called_once_with(mock_story)

    @patch("services.text_processor.src.processor.get_session")
    @patch.object(TextProcessor, "_save_scripts")
    @patch.object(TextProcessor, "_process_multi_part")
    def test_process_story_multi_part(
        self, mock_process, mock_save, mock_get_session, processor
    ):
        """Test processing a multi-part story."""
        mock_session = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_session)
        mock_context.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_context

        mock_story = MagicMock()
        mock_story.char_count = 8000  # Above min_chars_for_split
        mock_session.get.return_value = mock_story

        mock_scripts = [
            ProcessedScript(
                part_number=1,
                total_parts=2,
                content="Part 1",
                hook="Hook 1",
                cta="CTA 1",
                voice_gender="female",
                estimated_duration_seconds=120,
            ),
            ProcessedScript(
                part_number=2,
                total_parts=2,
                content="Part 2",
                hook="Hook 2",
                cta="CTA 2",
                voice_gender="female",
                estimated_duration_seconds=150,
            ),
        ]
        mock_process.return_value = mock_scripts

        processor.process_story(1)

        mock_process.assert_called_once_with(mock_story)

    @patch("services.text_processor.src.processor.get_session")
    def test_process_story_not_found(self, mock_get_session, processor):
        """Test processing non-existent story."""
        mock_session = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_session)
        mock_context.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_context
        mock_session.get.return_value = None

        with pytest.raises(ValueError, match="Story 999 not found"):
            processor.process_story(999)
