"""Tests for Reddit fetcher module."""

from unittest.mock import MagicMock, patch

import pytest

from services.reddit_fetch.src.config import Settings
from services.reddit_fetch.src.fetcher import FetchResult, RedditFetcher


class TestFetchResult:
    """Tests for FetchResult dataclass."""

    def test_default_values(self):
        """Test FetchResult has correct defaults."""
        result = FetchResult()
        assert result.total_fetched == 0
        assert result.new_stories == 0
        assert result.duplicates == 0
        assert result.filtered_out == 0
        assert result.errors == []

    def test_with_values(self):
        """Test FetchResult with custom values."""
        result = FetchResult(
            total_fetched=10,
            new_stories=5,
            duplicates=3,
            filtered_out=2,
            errors=["error1"],
        )
        assert result.total_fetched == 10
        assert result.new_stories == 5
        assert result.errors == ["error1"]


class TestRedditFetcher:
    """Tests for RedditFetcher class."""

    @pytest.fixture
    def settings(self):
        """Create test settings."""
        return Settings(
            reddit_client_id="test_id",
            reddit_client_secret="test_secret",
            subreddits="nosleep,shortscarystories",
            min_char_count=100,
            max_char_count=10000,
            min_upvotes=50,
            max_stories_per_fetch=5,
        )

    @pytest.fixture
    def fetcher(self, settings):
        """Create fetcher with test settings."""
        return RedditFetcher(settings=settings)

    def test_init_with_settings(self, fetcher, settings):
        """Test fetcher initializes with provided settings."""
        assert fetcher.settings == settings
        assert fetcher._reddit is None

    def test_subreddit_list_parsing(self, settings):
        """Test that subreddits are parsed correctly."""
        assert settings.subreddit_list == ["nosleep", "shortscarystories"]

    def test_subreddit_list_with_spaces(self):
        """Test subreddit parsing handles spaces."""
        settings = Settings(subreddits=" nosleep , test , another ")
        assert settings.subreddit_list == ["nosleep", "test", "another"]

    def test_extract_content_removes_links(self, fetcher):
        """Test that markdown links are removed."""
        submission = MagicMock()
        submission.selftext = "Check out [this link](http://example.com) for more."

        content = fetcher._extract_content(submission)
        assert "this link" in content
        assert "http://example.com" not in content
        assert "[" not in content

    def test_extract_content_removes_formatting(self, fetcher):
        """Test that bold/italic formatting is removed."""
        submission = MagicMock()
        submission.selftext = "This is **bold** and *italic* text."

        content = fetcher._extract_content(submission)
        assert content == "This is bold and italic text."

    def test_extract_content_cleans_html_entities(self, fetcher):
        """Test that HTML entities are decoded."""
        submission = MagicMock()
        submission.selftext = "Tom &amp; Jerry &lt;3 &gt;_&gt;"

        content = fetcher._extract_content(submission)
        assert "&amp;" not in content
        assert "Tom & Jerry" in content

    def test_is_quality_content_rejects_removed(self, fetcher):
        """Test that [removed] content is rejected."""
        assert fetcher._is_quality_content("[removed]") is False
        assert fetcher._is_quality_content("[deleted]") is False

    def test_is_quality_content_rejects_low_alpha(self, fetcher):
        """Test that low alphabetic ratio is rejected."""
        assert fetcher._is_quality_content("12345 67890 !@#$%") is False

    def test_is_quality_content_rejects_promotional(self, fetcher):
        """Test that promotional content is rejected."""
        assert fetcher._is_quality_content("Check out my patreon.com/author") is False
        assert fetcher._is_quality_content("Buy my book on Amazon!") is False

    def test_is_quality_content_accepts_good_content(self, fetcher):
        """Test that quality content is accepted."""
        good_content = """
        The old house at the end of Maple Street had been abandoned for years.
        Nobody knew exactly when the last occupants had left, but everyone in
        town agreed it was better that way. Some places are meant to be empty.
        """
        assert fetcher._is_quality_content(good_content) is True

    def test_passes_filters_rejects_stickied(self, fetcher):
        """Test that stickied posts are rejected."""
        submission = MagicMock()
        submission.stickied = True

        assert fetcher._passes_filters(submission) is False

    def test_passes_filters_rejects_low_upvotes(self, fetcher):
        """Test that low upvote posts are rejected."""
        submission = MagicMock()
        submission.stickied = False
        submission.score = 10  # Below min_upvotes of 50
        submission.over_18 = False
        submission.selftext = "A" * 500

        assert fetcher._passes_filters(submission) is False

    def test_passes_filters_rejects_nsfw(self, fetcher):
        """Test that NSFW posts are rejected."""
        submission = MagicMock()
        submission.stickied = False
        submission.score = 100
        submission.over_18 = True
        submission.selftext = "A" * 500

        assert fetcher._passes_filters(submission) is False

    def test_passes_filters_rejects_short_content(self, fetcher):
        """Test that short content is rejected."""
        submission = MagicMock()
        submission.stickied = False
        submission.score = 100
        submission.over_18 = False
        submission.selftext = "Too short"

        assert fetcher._passes_filters(submission) is False

    def test_passes_filters_rejects_long_content(self, fetcher):
        """Test that overly long content is rejected."""
        submission = MagicMock()
        submission.stickied = False
        submission.score = 100
        submission.over_18 = False
        submission.selftext = "A" * 15000  # Over max_char_count

        assert fetcher._passes_filters(submission) is False

    def test_passes_filters_accepts_good_submission(self, fetcher):
        """Test that good submissions pass filters."""
        submission = MagicMock()
        submission.stickied = False
        submission.score = 100
        submission.over_18 = False
        submission.selftext = "A great story. " * 50  # ~750 chars of valid content

        assert fetcher._passes_filters(submission) is True

    @patch("services.reddit_fetch.src.fetcher.get_session")
    def test_is_duplicate_returns_true(self, mock_get_session, fetcher):
        """Test duplicate detection returns True for existing story."""
        mock_session = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_session)
        mock_context.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_context

        # Mock existing story
        mock_session.execute.return_value.scalar_one_or_none.return_value = MagicMock()

        assert fetcher._is_duplicate("existing_id") is True

    @patch("services.reddit_fetch.src.fetcher.get_session")
    def test_is_duplicate_returns_false(self, mock_get_session, fetcher):
        """Test duplicate detection returns False for new story."""
        mock_session = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_session)
        mock_context.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_context

        # Mock no existing story
        mock_session.execute.return_value.scalar_one_or_none.return_value = None

        assert fetcher._is_duplicate("new_id") is False

    @patch("services.reddit_fetch.src.fetcher.Story")
    @patch("services.reddit_fetch.src.fetcher.get_session")
    def test_store_story_creates_record(self, mock_get_session, mock_story_class, fetcher):
        """Test that store_story creates a database record."""
        mock_session = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_session)
        mock_context.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_context

        submission = MagicMock()
        submission.id = "test123"
        submission.title = "Test Story Title"
        submission.author = MagicMock(__str__=lambda x: "test_author")
        submission.selftext = "This is the story content."
        submission.score = 500
        submission.permalink = "/r/nosleep/comments/test123"

        fetcher._store_story(submission, "nosleep")

        # Verify session.add was called
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @patch.object(RedditFetcher, "_fetch_from_subreddit")
    def test_fetch_stories_aggregates_results(self, mock_fetch, fetcher):
        """Test that fetch_stories aggregates results from all subreddits."""
        mock_fetch.side_effect = [
            FetchResult(total_fetched=10, new_stories=3, duplicates=2, filtered_out=5),
            FetchResult(total_fetched=8, new_stories=2, duplicates=1, filtered_out=5),
        ]

        result = fetcher.fetch_stories()

        assert result.total_fetched == 18
        assert result.new_stories == 5
        assert result.duplicates == 3
        assert result.filtered_out == 10

    @patch.object(RedditFetcher, "_fetch_from_subreddit")
    def test_fetch_stories_handles_errors(self, mock_fetch, fetcher):
        """Test that fetch_stories handles subreddit errors gracefully."""
        mock_fetch.side_effect = [
            Exception("API Error"),
            FetchResult(total_fetched=5, new_stories=2),
        ]

        result = fetcher.fetch_stories()

        assert result.new_stories == 2
        assert len(result.errors) == 1
        assert "API Error" in result.errors[0]


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

    def test_redis_url(self):
        """Test Redis URL construction."""
        settings = Settings(redis_host="redis.example.com", redis_port=6380)
        assert settings.redis_url == "redis://redis.example.com:6380/0"

    def test_default_values(self):
        """Test default settings values."""
        settings = Settings()
        assert settings.min_char_count == 500
        assert settings.max_char_count == 15000
        assert settings.min_upvotes == 100
        assert settings.fetch_interval_minutes == 60
