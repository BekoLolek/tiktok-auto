"""Text processor module with LLM integration."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx
from sqlalchemy import update

from shared.python.db import Script, Story, StoryStatus, VoiceGender, get_session

from .config import Settings, get_settings

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class ProcessedScript:
    """A processed script part ready for TTS."""

    part_number: int
    total_parts: int
    content: str
    hook: str
    cta: str
    voice_gender: str
    estimated_duration_seconds: int


class OllamaClient:
    """Client for Ollama API."""

    def __init__(self, base_url: str, model: str):
        """Initialize Ollama client."""
        self.base_url = base_url
        self.model = model
        self._client = httpx.Client(timeout=120.0)

    def generate(self, prompt: str, system: str | None = None) -> str:
        """Generate text using Ollama."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        if system:
            payload["system"] = system

        response = self._client.post(
            f"{self.base_url}/api/generate",
            json=payload,
        )
        response.raise_for_status()
        return response.json()["response"]

    def close(self):
        """Close the client."""
        self._client.close()


class TextProcessor:
    """Processes stories into scripts with hooks and CTAs."""

    SYSTEM_PROMPT = """You are a TikTok content writer specializing in engaging storytelling.
Your task is to enhance Reddit stories for TikTok narration while keeping them authentic.

Guidelines:
- Keep the original story intact - don't change plot or details
- Add engaging hooks that grab attention in the first 3 seconds
- Add calls-to-action (CTAs) at the end asking viewers to follow/like
- Use casual, conversational language suitable for narration
- For multi-part stories, end each part with a cliffhanger
- Keep the narrative flowing naturally"""

    def __init__(self, settings: Settings | None = None):
        """Initialize processor with settings."""
        self.settings = settings or get_settings()
        self._ollama: OllamaClient | None = None

    @property
    def ollama(self) -> OllamaClient:
        """Lazy-load Ollama client."""
        if self._ollama is None:
            self._ollama = OllamaClient(
                base_url=self.settings.ollama_url,
                model=self.settings.ollama_model,
            )
        return self._ollama

    def process_story(self, story_id: str) -> list[str]:
        """Process a story into scripts.

        Returns:
            List of script IDs (UUIDs as strings)
        """
        with get_session() as session:
            story = session.get(Story, story_id)
            if not story:
                raise ValueError(f"Story {story_id} not found")

            # Update status to processing
            session.execute(
                update(Story)
                .where(Story.id == story_id)
                .values(status=StoryStatus.PROCESSING.value)
            )
            session.commit()

            # Extract story data while in session to avoid DetachedInstanceError
            story_data = {
                "id": story.id,
                "title": story.title,
                "content": story.content,
                "subreddit": story.subreddit,
                "char_count": story.char_count,
            }

        try:
            # Estimate duration based on word count
            word_count = len(story_data["content"].split())
            estimated_duration = (word_count / self.settings.words_per_minute) * 60

            logger.info(
                f"Story {story_id}: {word_count} words, estimated {estimated_duration:.0f}s",
                extra={"story_id": story_id, "word_count": word_count, "estimated_duration": estimated_duration},
            )

            # Determine number of parts needed (each part max 3 minutes)
            max_duration = self.settings.max_duration_per_part_seconds
            num_parts_needed = max(1, int(estimated_duration / max_duration) + (1 if estimated_duration % max_duration > 30 else 0))

            if num_parts_needed == 1:
                scripts = [self._process_single_part(story_data)]
            else:
                scripts = self._process_multi_part(story_data, num_parts_needed)

            # Save scripts to database and get their IDs
            script_ids = self._save_scripts(story_id, scripts)

            logger.info(
                f"Processed story {story_id} into {len(scripts)} part(s)",
                extra={"story_id": story_id, "parts": len(scripts)},
            )

            return script_ids

        except Exception as e:
            # Update status to failed
            with get_session() as session:
                session.execute(
                    update(Story)
                    .where(Story.id == story_id)
                    .values(status=StoryStatus.FAILED.value, error_message=str(e))
                )
                session.commit()
            raise

    def _process_single_part(self, story: dict) -> ProcessedScript:
        """Process a single-part story."""
        prompt = f"""Enhance this Reddit story for TikTok narration.

Title: {story["title"]}
Subreddit: r/{story["subreddit"]}

Story:
{story["content"]}

Respond in JSON format:
{{
    "hook": "An attention-grabbing opening line (5-10 words)",
    "content": "The enhanced story text for narration",
    "cta": "A call-to-action for viewers (follow for part 2, like if you enjoyed, etc.)"
}}"""

        response = self.ollama.generate(prompt, self.SYSTEM_PROMPT)
        data = self._parse_json_response(response)

        # Calculate estimated duration
        word_count = len(data["content"].split())
        duration = int((word_count / self.settings.words_per_minute) * 60)

        # Random voice selection
        import random
        voice = random.choice([VoiceGender.MALE.value, VoiceGender.FEMALE.value])

        return ProcessedScript(
            part_number=1,
            total_parts=1,
            content=data["content"],
            hook=data["hook"],
            cta=data["cta"],
            voice_gender=voice,
            estimated_duration_seconds=duration,
        )

    def _process_multi_part(self, story: dict, target_parts: int) -> list[ProcessedScript]:
        """Process a multi-part story with cliffhangers.

        Args:
            story: Story data dict
            target_parts: Target number of parts based on duration estimate
        """
        # Find split points aiming for target_parts
        split_points = self._find_split_points(story["content"], target_parts)

        # Generate scripts for each part
        scripts = []
        parts = self._split_content(story["content"], split_points)
        total_parts = len(parts)

        logger.info(f"Splitting story into {total_parts} parts (target was {target_parts})")

        # Select one voice for the entire story
        import random
        voice = random.choice([VoiceGender.MALE.value, VoiceGender.FEMALE.value])

        for i, part_content in enumerate(parts, 1):
            is_first = i == 1
            is_last = i == total_parts

            prompt = self._build_multi_part_prompt(
                story=story,
                part_content=part_content,
                part_number=i,
                total_parts=total_parts,
                is_first=is_first,
                is_last=is_last,
            )

            response = self.ollama.generate(prompt, self.SYSTEM_PROMPT)
            data = self._parse_json_response(response)

            word_count = len(data["content"].split())
            duration = int((word_count / self.settings.words_per_minute) * 60)

            scripts.append(
                ProcessedScript(
                    part_number=i,
                    total_parts=total_parts,
                    content=data["content"],
                    hook=data["hook"],
                    cta=data["cta"],
                    voice_gender=voice,
                    estimated_duration_seconds=duration,
                )
            )

        return scripts

    def _build_multi_part_prompt(
        self,
        story: dict,
        part_content: str,
        part_number: int,
        total_parts: int,
        is_first: bool,
        is_last: bool,
    ) -> str:
        """Build prompt for multi-part processing."""
        # Determine the CTA based on position
        if is_last:
            cta_instruction = "Like and follow for more stories!"
        else:
            next_part = part_number + 1
            cta_instruction = f"Follow for part {next_part}!"

        # Determine hook based on position
        if is_first:
            hook_instruction = "An attention-grabbing opening line"
        else:
            hook_instruction = f"Part {part_number}"

        return f"""Enhance this Reddit story segment for TikTok narration.

Title: {story["title"]}
Subreddit: r/{story["subreddit"]}

Instructions: Keep the story natural. Don't add commentary about parts or references to this being a multi-part story in the content itself.

Story segment:
{part_content}

Respond in JSON format:
{{
    "hook": "{hook_instruction}",
    "content": "The enhanced story text for narration (keep it natural, no part references)",
    "cta": "{cta_instruction}"
}}"""

    def _find_split_points(self, content: str, target_parts: int) -> list[int]:
        """Find natural split points in content (paragraph breaks, cliffhangers).

        Args:
            content: Full story content
            target_parts: Number of parts to split into

        Returns:
            List of paragraph indices where splits should occur
        """
        # Split on paragraph breaks
        paragraphs = content.split("\n\n")

        if target_parts <= 1 or len(paragraphs) < 2:
            return []

        # We need (target_parts - 1) split points
        splits_needed = target_parts - 1

        # Calculate target word count per part
        total_words = len(content.split())
        target_words_per_part = total_words // target_parts

        split_points = []
        current_words = 0
        splits_made = 0

        for i, para in enumerate(paragraphs[:-1]):  # Don't add split after last paragraph
            para_words = len(para.split())
            current_words += para_words

            # Check if we've reached the target for this part
            if current_words >= target_words_per_part and splits_made < splits_needed:
                # Prefer cliffhanger points, but accept any paragraph break near target
                if self._is_good_split_point(para):
                    split_points.append(i)
                    current_words = 0
                    splits_made += 1
                    logger.debug(f"Split at paragraph {i} (cliffhanger): '{para[-50:]}...'")
                elif current_words >= target_words_per_part * 1.2:
                    # Force split if 20% over target
                    split_points.append(i)
                    current_words = 0
                    splits_made += 1
                    logger.debug(f"Split at paragraph {i} (forced): {current_words} words")

        # If we didn't find enough natural split points, distribute evenly
        if len(split_points) < splits_needed:
            logger.warning(f"Only found {len(split_points)} natural splits, need {splits_needed}. Distributing evenly.")
            # Fall back to even distribution
            split_points = []
            paras_per_part = len(paragraphs) // target_parts
            for i in range(1, target_parts):
                split_idx = min(i * paras_per_part - 1, len(paragraphs) - 2)
                if split_idx not in split_points:
                    split_points.append(split_idx)

        return sorted(split_points)

    def _is_good_split_point(self, paragraph: str) -> bool:
        """Check if paragraph ends with a good cliffhanger."""
        cliffhanger_patterns = [
            r"\.{3}$",  # Ends with ...
            r"\?$",  # Ends with question
            r"but then",
            r"suddenly",
            r"that's when",
            r"i couldn't believe",
            r"what happened next",
            r"little did [iI] know",
        ]

        text_lower = paragraph.lower().strip()
        for pattern in cliffhanger_patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return True

        return False

    def _split_content(self, content: str, split_points: list[int]) -> list[str]:
        """Split content at the specified paragraph indices."""
        paragraphs = content.split("\n\n")

        if not split_points:
            return [content]

        parts = []
        start = 0

        for split_idx in split_points:
            parts.append("\n\n".join(paragraphs[start : split_idx + 1]))
            start = split_idx + 1

        # Add remaining content
        if start < len(paragraphs):
            parts.append("\n\n".join(paragraphs[start:]))

        return parts

    def _parse_json_response(self, response: str) -> dict:
        """Parse JSON from LLM response, handling common issues."""
        # Try to find JSON in the response
        json_match = re.search(r"\{[\s\S]*\}", response)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # Fallback: extract fields manually
        hook_match = re.search(r'"hook":\s*"([^"]*)"', response)
        content_match = re.search(r'"content":\s*"([\s\S]*?)"(?=,\s*"cta"|$)', response)
        cta_match = re.search(r'"cta":\s*"([^"]*)"', response)

        return {
            "hook": hook_match.group(1) if hook_match else "You won't believe this story...",
            "content": content_match.group(1) if content_match else response,
            "cta": cta_match.group(1) if cta_match else "Follow for more stories!",
        }

    def _save_scripts(self, story_id: str, scripts: list[ProcessedScript]) -> list[str]:
        """Save processed scripts to database and return their IDs."""
        script_ids = []
        with get_session() as session:
            for script in scripts:
                db_script = Script(
                    story_id=story_id,
                    part_number=script.part_number,
                    total_parts=script.total_parts,
                    content=script.content,
                    hook=script.hook,
                    cta=script.cta,
                    voice_gender=script.voice_gender,
                    char_count=len(script.content),
                )
                session.add(db_script)
                session.flush()  # Get the ID
                script_ids.append(str(db_script.id))
            session.commit()
        return script_ids


def process_story(story_id: str) -> list[ProcessedScript]:
    """Process a story - convenience function."""
    processor = TextProcessor()
    return processor.process_story(story_id)
