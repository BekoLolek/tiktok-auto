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

    def process_story(self, story_id: int) -> list[ProcessedScript]:
        """Process a story into scripts."""
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

        try:
            # Determine if we need to split
            if story.char_count < self.settings.min_chars_for_split:
                scripts = [self._process_single_part(story)]
            else:
                scripts = self._process_multi_part(story)

            # Save scripts to database
            self._save_scripts(story_id, scripts)

            logger.info(
                f"Processed story {story_id} into {len(scripts)} part(s)",
                extra={"story_id": story_id, "parts": len(scripts)},
            )

            return scripts

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

    def _process_single_part(self, story: Story) -> ProcessedScript:
        """Process a single-part story."""
        prompt = f"""Enhance this Reddit story for TikTok narration.

Title: {story.title}
Subreddit: r/{story.subreddit}

Story:
{story.content}

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

    def _process_multi_part(self, story: Story) -> list[ProcessedScript]:
        """Process a multi-part story with cliffhangers."""
        # First, determine split points
        split_points = self._find_split_points(story.content)

        # Generate scripts for each part
        scripts = []
        parts = self._split_content(story.content, split_points)
        total_parts = len(parts)

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
        story: Story,
        part_content: str,
        part_number: int,
        total_parts: int,
        is_first: bool,
        is_last: bool,
    ) -> str:
        """Build prompt for multi-part processing."""
        context = f"Part {part_number} of {total_parts}"

        if is_first:
            instructions = "Create an attention-grabbing hook. End with a cliffhanger to make viewers want part 2."
        elif is_last:
            instructions = "Reference this being the final part. Create a satisfying conclusion with a strong CTA."
        else:
            instructions = f"Reference this being part {part_number}. End with a cliffhanger for the next part."

        return f"""Enhance this Reddit story segment for TikTok narration.

Title: {story.title}
{context}
Subreddit: r/{story.subreddit}

Instructions: {instructions}

Story segment:
{part_content}

Respond in JSON format:
{{
    "hook": "{'Opening hook for part 1' if is_first else f'Transition hook referencing part {part_number}'}",
    "content": "The enhanced story text for narration",
    "cta": "{'Follow for part 2!' if not is_last else 'Like and follow for more stories!'}"
}}"""

    def _find_split_points(self, content: str) -> list[int]:
        """Find natural split points in content (paragraph breaks, cliffhangers)."""
        # Split on paragraph breaks
        paragraphs = content.split("\n\n")

        # Calculate target length per part
        total_chars = len(content)
        num_parts = max(1, total_chars // self.settings.max_chars_per_part + 1)
        target_chars_per_part = total_chars // num_parts

        split_points = []
        current_length = 0

        for i, para in enumerate(paragraphs[:-1]):  # Don't add split after last paragraph
            current_length += len(para) + 2  # +2 for \n\n

            if current_length >= target_chars_per_part:
                # Look for cliffhanger indicators
                if self._is_good_split_point(para):
                    split_points.append(i)
                    current_length = 0
                elif current_length >= target_chars_per_part * 1.3:
                    # Force split if too long
                    split_points.append(i)
                    current_length = 0

        return split_points

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

    def _save_scripts(self, story_id: int, scripts: list[ProcessedScript]) -> None:
        """Save processed scripts to database."""
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
                    estimated_duration=script.estimated_duration_seconds,
                )
                session.add(db_script)
            session.commit()


def process_story(story_id: int) -> list[ProcessedScript]:
    """Process a story - convenience function."""
    processor = TextProcessor()
    return processor.process_story(story_id)
