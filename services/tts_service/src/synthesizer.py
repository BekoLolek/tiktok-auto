"""TTS synthesizer module using Piper."""

from __future__ import annotations

import io
import logging
import socket
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from shared.python.db import Audio, Script, get_session

from .config import Settings, get_settings

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class AudioResult:
    """Result of audio synthesis."""

    script_id: int
    audio_path: str
    duration_seconds: float
    sample_rate: int
    voice: str


class PiperClient:
    """Client for Piper TTS using Wyoming protocol."""

    def __init__(self, host: str, port: int):
        """Initialize Piper client."""
        self.host = host
        self.port = port

    def synthesize(self, text: str, voice: str | None = None) -> bytes:
        """Synthesize text to audio using Wyoming protocol.

        Args:
            text: Text to synthesize
            voice: Optional voice name override

        Returns:
            Raw WAV audio bytes
        """
        # Wyoming protocol uses JSON-lines over socket
        import json

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(60.0)
            sock.connect((self.host, self.port))

            # Send synthesize request
            request = {
                "type": "synthesize",
                "data": {
                    "text": text,
                },
            }
            if voice:
                request["data"]["voice"] = {"name": voice}

            request_bytes = (json.dumps(request) + "\n").encode("utf-8")
            sock.sendall(request_bytes)

            # Read response
            audio_chunks = []
            buffer = b""

            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break

                buffer += chunk

                # Check for audio-chunk or audio-stop messages
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    try:
                        msg = json.loads(line.decode("utf-8"))
                        if msg.get("type") == "audio-chunk":
                            # Audio data is base64 encoded
                            import base64
                            audio_data = base64.b64decode(msg["data"]["audio"])
                            audio_chunks.append(audio_data)
                        elif msg.get("type") == "audio-stop":
                            # Done receiving
                            return b"".join(audio_chunks)
                    except (json.JSONDecodeError, KeyError):
                        continue

            return b"".join(audio_chunks)

    def health_check(self) -> bool:
        """Check if Piper is available."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(5.0)
                sock.connect((self.host, self.port))
                return True
        except (TimeoutError, OSError):
            return False


class TTSSynthesizer:
    """Synthesizes scripts to audio using Piper TTS."""

    def __init__(self, settings: Settings | None = None):
        """Initialize synthesizer with settings."""
        self.settings = settings or get_settings()
        self._client: PiperClient | None = None

    @property
    def client(self) -> PiperClient:
        """Lazy-load Piper client."""
        if self._client is None:
            self._client = PiperClient(
                host=self.settings.piper_host,
                port=self.settings.piper_port,
            )
        return self._client

    def synthesize_script(self, script_id: int) -> AudioResult:
        """Synthesize a script to audio.

        Args:
            script_id: ID of script to synthesize

        Returns:
            AudioResult with path to generated audio
        """
        with get_session() as session:
            script = session.get(Script, script_id)
            if not script:
                raise ValueError(f"Script {script_id} not found")

            # Story context available if needed via script.story_id

        # Select voice based on script setting
        voice = self._get_voice(script.voice_gender)

        # Combine hook, content, and CTA for full narration
        full_text = self._build_narration_text(script)

        logger.info(
            f"Synthesizing script {script_id}",
            extra={
                "script_id": script_id,
                "voice": voice,
                "text_length": len(full_text),
            },
        )

        # Generate audio
        try:
            audio_data = self.client.synthesize(full_text, voice)
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            raise

        # Save audio file
        audio_path = self._save_audio(script_id, audio_data)

        # Calculate duration
        duration = self._get_audio_duration(audio_data)

        # Save to database
        result = AudioResult(
            script_id=script_id,
            audio_path=str(audio_path),
            duration_seconds=duration,
            sample_rate=self.settings.sample_rate,
            voice=voice,
        )

        self._save_audio_record(result)

        logger.info(
            f"Synthesized script {script_id}",
            extra={
                "script_id": script_id,
                "duration": duration,
                "path": str(audio_path),
            },
        )

        return result

    def _get_voice(self, voice_gender: str | None) -> str:
        """Get voice name based on gender."""
        if voice_gender == "female":
            return self.settings.female_voice
        return self.settings.male_voice

    def _build_narration_text(self, script: Script) -> str:
        """Build full narration text from script parts."""
        parts = []

        # Add hook
        if script.hook:
            parts.append(script.hook)

        # Add main content
        parts.append(script.content)

        # Add CTA
        if script.cta:
            parts.append(script.cta)

        return " ".join(parts)

    def _save_audio(self, script_id: int, audio_data: bytes) -> Path:
        """Save audio data to file."""
        filename = f"script_{script_id}.{self.settings.audio_format}"
        output_path = self.settings.audio_path / filename

        # If audio_data is raw PCM, wrap in WAV
        if not audio_data.startswith(b"RIFF"):
            audio_data = self._wrap_in_wav(audio_data)

        with open(output_path, "wb") as f:
            f.write(audio_data)

        return output_path

    def _wrap_in_wav(self, pcm_data: bytes) -> bytes:
        """Wrap raw PCM data in WAV container."""
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)  # 16-bit
            wav.setframerate(self.settings.sample_rate)
            wav.writeframes(pcm_data)
        return buffer.getvalue()

    def _get_audio_duration(self, audio_data: bytes) -> float:
        """Calculate audio duration in seconds."""
        try:
            buffer = io.BytesIO(audio_data)
            with wave.open(buffer, "rb") as wav:
                frames = wav.getnframes()
                rate = wav.getframerate()
                return frames / rate
        except Exception:
            # Estimate from raw data size
            # Assuming 16-bit mono at sample_rate
            bytes_per_sample = 2
            return len(audio_data) / (self.settings.sample_rate * bytes_per_sample)

    def _save_audio_record(self, result: AudioResult) -> None:
        """Save audio record to database."""
        with get_session() as session:
            audio = Audio(
                script_id=result.script_id,
                file_path=result.audio_path,
                duration=result.duration_seconds,
                sample_rate=result.sample_rate,
                voice=result.voice,
            )
            session.add(audio)
            session.commit()


def synthesize_script(script_id: int) -> AudioResult:
    """Synthesize a script - convenience function."""
    synthesizer = TTSSynthesizer()
    return synthesizer.synthesize_script(script_id)
