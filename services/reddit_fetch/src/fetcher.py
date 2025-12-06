"""Reddit story fetcher module."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import praw
from sqlalchemy import select

if TYPE_CHECKING:
    from praw.models import Submission

from shared.python.db import Story, StoryStatus, get_session

from .config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    """Result of a fetch operation."""

    total_fetched: int = 0
    new_stories: int = 0
    duplicates: int = 0
    filtered_out: int = 0
    errors: list[str] | None = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class RedditFetcher:
    """Fetches stories from Reddit and stores them for processing."""

    def __init__(self, settings: Settings | None = None):
        """Initialize fetcher with settings."""
        self.settings = settings or get_settings()
        self._reddit: praw.Reddit | None = None

    @property
    def reddit(self) -> praw.Reddit:
        """Lazy-load Reddit client."""
        if self._reddit is None:
            self._reddit = praw.Reddit(
                client_id=self.settings.reddit_client_id,
                client_secret=self.settings.reddit_client_secret,
                user_agent=self.settings.reddit_user_agent,
            )
        return self._reddit

    def fetch_stories(self) -> FetchResult:
        """Fetch stories from all configured subreddits."""
        result = FetchResult()

        for subreddit_name in self.settings.subreddit_list:
            try:
                sub_result = self._fetch_from_subreddit(subreddit_name)
                result.total_fetched += sub_result.total_fetched
                result.new_stories += sub_result.new_stories
                result.duplicates += sub_result.duplicates
                result.filtered_out += sub_result.filtered_out
                if sub_result.errors:
                    result.errors.extend(sub_result.errors)
            except Exception as e:
                error_msg = f"Error fetching from r/{subreddit_name}: {e}"
                logger.error(error_msg)
                result.errors.append(error_msg)

        logger.info(
            "Fetch complete",
            extra={
                "total_fetched": result.total_fetched,
                "new_stories": result.new_stories,
                "duplicates": result.duplicates,
                "filtered_out": result.filtered_out,
            },
        )

        return result

    def _fetch_from_subreddit(self, subreddit_name: str) -> FetchResult:
        """Fetch stories from a single subreddit."""
        result = FetchResult()
        subreddit = self.reddit.subreddit(subreddit_name)

        logger.info(f"Fetching from r/{subreddit_name}")

        for submission in subreddit.hot(limit=self.settings.max_stories_per_fetch * 2):
            result.total_fetched += 1

            # Check if story passes filters
            if not self._passes_filters(submission):
                result.filtered_out += 1
                continue

            # Check for duplicate
            if self._is_duplicate(submission.id):
                result.duplicates += 1
                continue

            # Store the story
            try:
                story = self._store_story(submission, subreddit_name)
                if story:
                    result.new_stories += 1
                    logger.info(
                        f"Stored new story: {submission.id}",
                        extra={"reddit_id": submission.id, "story_id": str(story.id)},
                    )
            except Exception as e:
                error_msg = f"Error storing story {submission.id}: {e}"
                logger.error(error_msg)
                result.errors.append(error_msg)

            # Stop if we have enough new stories
            if result.new_stories >= self.settings.max_stories_per_fetch:
                break

        return result

    def _passes_filters(self, submission: Submission) -> bool:
        """Check if submission passes all content filters."""
        # Skip stickied posts
        if submission.stickied:
            return False

        # Check upvotes
        if submission.score < self.settings.min_upvotes:
            return False

        # Get text content
        content = self._extract_content(submission)
        char_count = len(content)

        # Check character count
        if char_count < self.settings.min_char_count:
            return False
        if char_count > self.settings.max_char_count:
            return False

        # Check for NSFW (skip if marked)
        if submission.over_18:
            return False

        # Basic content quality checks
        if not self._is_quality_content(content):
            return False

        return True

    def _extract_content(self, submission: Submission) -> str:
        """Extract clean text content from submission."""
        content = submission.selftext

        # Remove Reddit formatting
        content = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", content)  # Links
        content = re.sub(r"[*_]{1,2}([^*_]+)[*_]{1,2}", r"\1", content)  # Bold/italic
        content = re.sub(r"^#+\s*", "", content, flags=re.MULTILINE)  # Headers
        content = re.sub(r"&amp;", "&", content)
        content = re.sub(r"&lt;", "<", content)
        content = re.sub(r"&gt;", ">", content)
        content = re.sub(r"\n{3,}", "\n\n", content)  # Multiple newlines

        return content.strip()

    def _is_quality_content(self, content: str) -> bool:
        """Check if content meets quality standards."""
        # Skip if mostly non-alphabetic
        alpha_ratio = sum(c.isalpha() for c in content) / max(len(content), 1)
        if alpha_ratio < 0.7:
            return False

        # Skip if too many links remain
        if content.count("http") > 3:
            return False

        # Skip if contains common disqualifying patterns
        disqualify_patterns = [
            r"\[removed\]",
            r"\[deleted\]",
            r"patreon\.com",
            r"buy\s+my\s+book",
            r"check\s+out\s+my",
        ]
        for pattern in disqualify_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return False

        return True

    def _is_duplicate(self, reddit_id: str) -> bool:
        """Check if story already exists in database."""
        with get_session() as session:
            stmt = select(Story).where(Story.reddit_id == reddit_id)
            result = session.execute(stmt).scalar_one_or_none()
            return result is not None

    def _store_story(self, submission: Submission, subreddit: str) -> Story | None:
        """Store a new story in the database."""
        content = self._extract_content(submission)

        with get_session() as session:
            story = Story(
                reddit_id=submission.id,
                subreddit=subreddit,
                title=submission.title[:500],  # Truncate if needed
                author=str(submission.author) if submission.author else "[deleted]",
                content=content,
                char_count=len(content),
                upvotes=submission.score,
                url=f"https://reddit.com{submission.permalink}",
                status=StoryStatus.PENDING.value,
            )
            session.add(story)
            session.commit()
            session.refresh(story)

            # Trigger notification for new story (optional)
            self._notify_new_story(story.id)

            return story

    def _notify_new_story(self, story_id: int) -> None:
        """Send notification about new story for approval."""
        # This just logs for now - dashboard will poll for pending stories
        logger.info(f"New story awaiting approval: {story_id}")


def run_fetch() -> FetchResult:
    """Run a single fetch operation."""
    fetcher = RedditFetcher()
    return fetcher.fetch_stories()
