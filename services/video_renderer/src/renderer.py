"""Video renderer module using MoviePy and Whisper."""

from __future__ import annotations

import logging
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from moviepy.editor import (
    AudioFileClip,
    CompositeVideoClip,
    TextClip,
    VideoFileClip,
    concatenate_videoclips,
)
from sqlalchemy import update

from shared.python.db import Audio, Script, Story, StoryStatus, Video, get_session

from .config import Settings, get_settings

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class Caption:
    """A single caption segment."""

    text: str
    start_time: float
    end_time: float


@dataclass
class RenderResult:
    """Result of video rendering."""

    script_id: int
    video_path: str
    duration_seconds: float
    width: int
    height: int


class WhisperTranscriber:
    """Transcribes audio using Whisper for captions."""

    def __init__(self, model_name: str = "base"):
        """Initialize transcriber with model name."""
        self.model_name = model_name
        self._model = None

    @property
    def model(self):
        """Lazy-load Whisper model."""
        if self._model is None:
            import whisper

            self._model = whisper.load_model(self.model_name)
        return self._model

    def transcribe(self, audio_path: str) -> list[Caption]:
        """Transcribe audio file to captions.

        Args:
            audio_path: Path to audio file

        Returns:
            List of Caption objects with timing info
        """
        result = self.model.transcribe(audio_path, word_timestamps=True)

        captions = []
        for segment in result.get("segments", []):
            # Group words into ~3-5 word chunks for readable captions
            words = segment.get("words", [])
            if not words:
                # Fallback to segment level
                captions.append(
                    Caption(
                        text=segment["text"].strip(),
                        start_time=segment["start"],
                        end_time=segment["end"],
                    )
                )
                continue

            chunk_words = []
            chunk_start = None

            for word in words:
                if chunk_start is None:
                    chunk_start = word["start"]

                chunk_words.append(word["word"])

                # Create caption chunk every 4-5 words or at punctuation
                if len(chunk_words) >= 4 or word["word"].rstrip().endswith((".", "!", "?", ",")):
                    captions.append(
                        Caption(
                            text=" ".join(chunk_words).strip(),
                            start_time=chunk_start,
                            end_time=word["end"],
                        )
                    )
                    chunk_words = []
                    chunk_start = None

            # Handle remaining words
            if chunk_words and chunk_start is not None:
                captions.append(
                    Caption(
                        text=" ".join(chunk_words).strip(),
                        start_time=chunk_start,
                        end_time=words[-1]["end"],
                    )
                )

        return captions


class VideoRenderer:
    """Renders videos from audio and background clips."""

    def __init__(self, settings: Settings | None = None):
        """Initialize renderer with settings."""
        self.settings = settings or get_settings()
        self._transcriber: WhisperTranscriber | None = None

    @property
    def transcriber(self) -> WhisperTranscriber:
        """Lazy-load transcriber."""
        if self._transcriber is None:
            self._transcriber = WhisperTranscriber(self.settings.whisper_model)
        return self._transcriber

    def render_video(self, script_id: int) -> RenderResult:
        """Render video for a script.

        Args:
            script_id: ID of script to render

        Returns:
            RenderResult with path to rendered video
        """
        with get_session() as session:
            script = session.get(Script, script_id)
            if not script:
                raise ValueError(f"Script {script_id} not found")

            # Get audio record
            audio = (
                session.query(Audio).filter(Audio.script_id == script_id).first()
            )
            if not audio:
                raise ValueError(f"No audio found for script {script_id}")

        logger.info(
            f"Rendering video for script {script_id}",
            extra={"script_id": script_id, "audio_duration": audio.duration},
        )

        try:
            # Load audio
            audio_clip = AudioFileClip(audio.file_path)
            duration = audio_clip.duration

            # Get background video
            background = self._get_background_video(duration)

            # Generate captions
            captions = self.transcriber.transcribe(audio.file_path)

            # Create caption clips
            caption_clips = self._create_caption_clips(captions, duration)

            # Compose final video
            final_clip = CompositeVideoClip(
                [background] + caption_clips,
                size=(self.settings.video_width, self.settings.video_height),
            )
            final_clip = final_clip.set_audio(audio_clip)

            # Render to file
            output_path = self._render_to_file(script_id, final_clip)

            # Clean up
            audio_clip.close()
            background.close()
            final_clip.close()

            result = RenderResult(
                script_id=script_id,
                video_path=str(output_path),
                duration_seconds=duration,
                width=self.settings.video_width,
                height=self.settings.video_height,
            )

            # Save to database
            self._save_video_record(result)

            logger.info(
                f"Rendered video for script {script_id}",
                extra={"script_id": script_id, "path": str(output_path)},
            )

            return result

        except Exception as e:
            logger.error(f"Render failed for script {script_id}: {e}")
            raise

    def _get_background_video(self, duration: float) -> VideoFileClip:
        """Get or create background video matching duration.

        Args:
            duration: Required video duration in seconds

        Returns:
            VideoFileClip sized to TikTok dimensions
        """
        # Find available background videos
        backgrounds = list(self.settings.background_path.glob("*.mp4"))
        backgrounds.extend(self.settings.background_path.glob("*.mov"))
        backgrounds.extend(self.settings.background_path.glob("*.webm"))

        if not backgrounds:
            # Create a solid color background if no videos available
            logger.warning("No background videos found, using solid color")
            return self._create_solid_background(duration)

        # Select random background
        bg_path = random.choice(backgrounds)
        bg_clip = VideoFileClip(str(bg_path))

        # Resize to fit TikTok dimensions (maintain aspect ratio, crop if needed)
        bg_clip = self._resize_and_crop(bg_clip)

        # Loop or trim to match duration
        if bg_clip.duration < duration:
            # Loop the video
            loops_needed = int(duration / bg_clip.duration) + 1
            bg_clip = concatenate_videoclips([bg_clip] * loops_needed)

        # Trim to exact duration
        bg_clip = bg_clip.subclip(0, duration)

        return bg_clip

    def _create_solid_background(self, duration: float) -> VideoFileClip:
        """Create a solid color background clip."""
        from moviepy.editor import ColorClip

        return ColorClip(
            size=(self.settings.video_width, self.settings.video_height),
            color=(20, 20, 30),  # Dark blue-gray
            duration=duration,
        )

    def _resize_and_crop(self, clip: VideoFileClip) -> VideoFileClip:
        """Resize and crop video to TikTok dimensions."""
        target_w = self.settings.video_width
        target_h = self.settings.video_height
        target_aspect = target_h / target_w  # Portrait

        clip_aspect = clip.h / clip.w

        if clip_aspect < target_aspect:
            # Video is wider - fit to height, crop width
            new_h = target_h
            new_w = int(clip.w * (target_h / clip.h))
            clip = clip.resize(height=new_h)
            # Crop to center
            x_center = new_w // 2
            clip = clip.crop(
                x1=x_center - target_w // 2,
                x2=x_center + target_w // 2,
            )
        else:
            # Video is taller - fit to width, crop height
            new_w = target_w
            new_h = int(clip.h * (target_w / clip.w))
            clip = clip.resize(width=new_w)
            # Crop to center
            y_center = new_h // 2
            clip = clip.crop(
                y1=y_center - target_h // 2,
                y2=y_center + target_h // 2,
            )

        return clip

    def _create_caption_clips(
        self, captions: list[Caption], duration: float
    ) -> list[TextClip]:
        """Create TextClip objects for captions.

        Args:
            captions: List of Caption objects
            duration: Total video duration

        Returns:
            List of positioned TextClip objects
        """
        clips = []

        for caption in captions:
            try:
                txt_clip = TextClip(
                    caption.text,
                    fontsize=self.settings.caption_font_size,
                    color=self.settings.caption_color,
                    font=self.settings.caption_font,
                    stroke_color=self.settings.caption_stroke_color,
                    stroke_width=self.settings.caption_stroke_width,
                    method="caption",
                    size=(self.settings.video_width - 100, None),
                )

                # Position caption
                txt_clip = txt_clip.set_position(
                    ("center", self.settings.video_height - self.settings.caption_margin_bottom)
                )

                # Set timing
                txt_clip = txt_clip.set_start(caption.start_time)
                txt_clip = txt_clip.set_duration(caption.end_time - caption.start_time)

                clips.append(txt_clip)

            except Exception as e:
                logger.warning(f"Failed to create caption clip: {e}")
                continue

        return clips

    def _render_to_file(self, script_id: int, clip: CompositeVideoClip) -> Path:
        """Render video clip to file.

        Args:
            script_id: Script ID for filename
            clip: Composed video clip

        Returns:
            Path to rendered video file
        """
        output_path = self.settings.output_path / f"video_{script_id}.mp4"

        clip.write_videofile(
            str(output_path),
            fps=self.settings.video_fps,
            codec=self.settings.video_codec,
            audio_codec=self.settings.audio_codec,
            bitrate=self.settings.video_bitrate,
            audio_bitrate=self.settings.audio_bitrate,
            temp_audiofile=str(self.settings.temp_path / f"temp_audio_{script_id}.m4a"),
            remove_temp=True,
            logger=None,  # Suppress moviepy logging
        )

        return output_path

    def _save_video_record(self, result: RenderResult) -> None:
        """Save video record to database."""
        with get_session() as session:
            video = Video(
                script_id=result.script_id,
                file_path=result.video_path,
                duration=result.duration_seconds,
                width=result.width,
                height=result.height,
            )
            session.add(video)
            session.commit()


def render_video(script_id: int) -> RenderResult:
    """Render video - convenience function."""
    renderer = VideoRenderer()
    return renderer.render_video(script_id)
