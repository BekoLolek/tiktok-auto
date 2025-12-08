"""TTS synthesizer module using gTTS (Google Text-to-Speech)."""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from gtts import gTTS
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


class GTTSClient:
    """Client for Google Text-to-Speech."""

    def __init__(self):
        """Initialize gTTS client."""
        pass

    def synthesize(self, text: str, lang: str, output_path: str) -> None:
        """Synthesize text to audio file.

        Args:
            text: Text to synthesize
            lang: Language code (e.g., 'en')
            output_path: Path to save the audio file (MP3)
        """
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.save(output_path)


class TTSSynthesizer:
    """Synthesizes scripts to audio using gTTS."""

    def __init__(self, settings: Settings | None = None):
        """Initialize synthesizer with settings."""
        self.settings = settings or get_settings()
        self._client: GTTSClient | None = None

    @property
    def client(self) -> GTTSClient:
        """Lazy-load gTTS client."""
        if self._client is None:
            self._client = GTTSClient()
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

        # gTTS uses language codes, not voice names
        lang = "en"
        voice_model = "gtts-en"

        # Combine hook, content, and CTA for full narration
        full_text = self._build_narration_text_from_dict(script_data)

        logger.info(
            f"Synthesizing script {script_id}",
            extra={
                "script_id": script_id,
                "voice": voice_model,
                "text_length": len(full_text),
            },
        )

        # Generate audio file path
        filename = f"script_{script_id}.{self.settings.audio_format}"
        audio_path = self.settings.audio_path / filename

        # Generate audio
        try:
            self.client.synthesize(full_text, lang, str(audio_path))
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            raise

        # Apply speed adjustment if configured
        if self.settings.audio_speed != 1.0:
            audio_path = self._speed_up_audio(audio_path, self.settings.audio_speed)

        # Calculate duration
        duration = self._get_audio_duration(str(audio_path))

        # Save to database and get audio ID
        audio_id = self._save_audio_record(script_id, str(audio_path), duration, voice_model)

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

    def _speed_up_audio(self, audio_path: Path, speed: float) -> Path:
        """Speed up audio using ffmpeg atempo filter.

        Args:
            audio_path: Path to original audio file
            speed: Speed multiplier (e.g., 1.25 for 25% faster)

        Returns:
            Path to the sped-up audio file (same path, file replaced)
        """
        logger.info(f"Speeding up audio to {speed}x", extra={"speed": speed})

        # Create temp file for output
        temp_output = audio_path.parent / f"temp_{audio_path.name}"

        cmd = [
            "ffmpeg", "-y",
            "-i", str(audio_path),
            "-filter:a", f"atempo={speed}",
            "-vn",
            str(temp_output)
        ]

        try:
            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )

            # Replace original with sped-up version
            temp_output.replace(audio_path)
            logger.info(f"Audio sped up successfully to {speed}x")
            return audio_path

        except subprocess.CalledProcessError as e:
            logger.error(f"ffmpeg speed adjustment failed: {e.stderr}")
            # Clean up temp file if it exists
            if temp_output.exists():
                temp_output.unlink()
            raise RuntimeError(f"Failed to speed up audio: {e.stderr}") from e

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
