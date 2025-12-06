"""TTS synthesizer module using Edge TTS (Microsoft Neural Voices)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import edge_tts
from mutagen.mp3 import MP3

from shared.python.db import Audio, Script, get_session

from .config import Settings, get_settings

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class AudioResult:
    """Result of audio synthesis."""

    script_id: str
    audio_id: str
    audio_path: str
    duration_seconds: float
    voice_model: str


class EdgeTTSClient:
    """Client for Edge TTS (Microsoft Neural Voices)."""

    def __init__(self, rate: str = "+0%", pitch: str = "+0Hz"):
        """Initialize Edge TTS client.

        Args:
            rate: Speech rate adjustment (e.g., "+10%", "-20%")
            pitch: Pitch adjustment (e.g., "+5Hz", "-10Hz")
        """
        self.rate = rate
        self.pitch = pitch

    def synthesize(self, text: str, voice: str, output_path: str) -> None:
        """Synthesize text to audio file.

        Args:
            text: Text to synthesize
            voice: Voice name (e.g., "en-US-ChristopherNeural")
            output_path: Path to save the audio file
        """
        asyncio.run(self._synthesize_async(text, voice, output_path))

    async def _synthesize_async(self, text: str, voice: str, output_path: str) -> None:
        """Async implementation of synthesize."""
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=self.rate,
            pitch=self.pitch,
        )
        await communicate.save(output_path)

    @staticmethod
    async def list_voices() -> list[dict]:
        """List available voices."""
        voices = await edge_tts.list_voices()
        return voices


class TTSSynthesizer:
    """Synthesizes scripts to audio using Edge TTS."""

    def __init__(self, settings: Settings | None = None):
        """Initialize synthesizer with settings."""
        self.settings = settings or get_settings()
        self._client: EdgeTTSClient | None = None

    @property
    def client(self) -> EdgeTTSClient:
        """Lazy-load Edge TTS client."""
        if self._client is None:
            self._client = EdgeTTSClient(
                rate=self.settings.voice_rate,
                pitch=self.settings.voice_pitch,
            )
        return self._client

    def synthesize(self, script_id: str) -> str:
        """Synthesize a script to audio.

        Args:
            script_id: UUID of script to synthesize

        Returns:
            Audio ID (UUID as string)
        """
        with get_session() as session:
            script = session.get(Script, script_id)
            if not script:
                raise ValueError(f"Script {script_id} not found")

            # Extract data while in session
            script_data = {
                "id": str(script.id),
                "voice_gender": script.voice_gender,
                "hook": script.hook,
                "content": script.content,
                "cta": script.cta,
            }

        # Select voice based on script setting
        voice = self._get_voice(script_data["voice_gender"])

        # Combine hook, content, and CTA for full narration
        full_text = self._build_narration_text_from_dict(script_data)

        logger.info(
            f"Synthesizing script {script_id}",
            extra={
                "script_id": script_id,
                "voice": voice,
                "text_length": len(full_text),
            },
        )

        # Generate audio file path
        filename = f"script_{script_id}.{self.settings.audio_format}"
        audio_path = self.settings.audio_path / filename

        # Generate audio
        try:
            self.client.synthesize(full_text, voice, str(audio_path))
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            raise

        # Calculate duration
        duration = self._get_audio_duration(str(audio_path))

        # Save to database and get audio ID
        audio_id = self._save_audio_record(script_id, str(audio_path), duration, voice)

        logger.info(
            f"Synthesized script {script_id}",
            extra={
                "script_id": script_id,
                "audio_id": audio_id,
                "duration": duration,
                "path": str(audio_path),
            },
        )

        return audio_id

    def _get_voice(self, voice_gender: str | None) -> str:
        """Get voice name based on gender."""
        if voice_gender == "female":
            return self.settings.female_voice
        return self.settings.male_voice

    def _build_narration_text_from_dict(self, script: dict) -> str:
        """Build full narration text from script data dict."""
        import re

        parts = []

        # Add hook
        if script.get("hook"):
            parts.append(script["hook"])

        # Add main content
        parts.append(script["content"])

        # Add CTA (but strip hashtags - they shouldn't be spoken)
        if script.get("cta"):
            cta = script["cta"]
            # Remove hashtags (e.g., #storytime #reddit)
            cta = re.sub(r'#\w+', '', cta)
            # Clean up extra whitespace
            cta = ' '.join(cta.split())
            if cta:
                parts.append(cta)

        text = " ".join(parts)

        # Also remove any stray hashtags from the full text
        text = re.sub(r'#\w+', '', text)
        text = ' '.join(text.split())

        return text

    def _get_audio_duration(self, audio_path: str) -> float:
        """Calculate audio duration in seconds."""
        try:
            audio = MP3(audio_path)
            return audio.info.length
        except Exception as e:
            logger.warning(f"Could not get audio duration: {e}")
            # Return estimate based on text (fallback)
            return 0.0

    def _save_audio_record(
        self, script_id: str, file_path: str, duration: float, voice: str
    ) -> str:
        """Save audio record to database and return audio ID."""
        with get_session() as session:
            audio = Audio(
                script_id=script_id,
                file_path=file_path,
                duration_seconds=duration,
                voice_model=voice,
            )
            session.add(audio)
            session.flush()
            audio_id = str(audio.id)
            session.commit()
            return audio_id


def synthesize(script_id: str) -> str:
    """Synthesize a script - convenience function.

    Returns:
        Audio ID (UUID as string)
    """
    synthesizer = TTSSynthesizer()
    return synthesizer.synthesize(script_id)
