FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including FFmpeg for video processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    ffmpeg \
    imagemagick \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Allow ImageMagick to process text
RUN sed -i 's/rights="none" pattern="@\*"/rights="read|write" pattern="@*"/' /etc/ImageMagick-6/policy.xml || true

# Copy shared library
COPY shared /app/shared

# Install all Python dependencies
RUN pip install --no-cache-dir \
    # Core dependencies
    sqlalchemy>=2.0.0 \
    psycopg2-binary>=2.9.0 \
    celery>=5.3.0 \
    redis>=5.0.0 \
    elasticsearch>=8.11.0 \
    pydantic>=2.0.0 \
    pydantic-settings>=2.0.0 \
    # Text processor dependencies
    httpx>=0.25.0 \
    # TTS dependencies (Google TTS)
    gTTS>=2.5.0 \
    mutagen>=1.47.0 \
    # Video renderer dependencies
    moviepy>=1.0.3 \
    openai-whisper>=20231117 \
    # Monitoring
    prometheus-client>=0.19.0 \
    # Misc
    python-dotenv>=1.0.0

# Copy all service code with proper structure
COPY services/__init__.py ./services/__init__.py

# Text processor
COPY services/text_processor/__init__.py ./services/text_processor/__init__.py
COPY services/text_processor/src ./services/text_processor/src

# TTS service
COPY services/tts_service/__init__.py ./services/tts_service/__init__.py
COPY services/tts_service/src ./services/tts_service/src

# Video renderer
COPY services/video_renderer/__init__.py ./services/video_renderer/__init__.py
COPY services/video_renderer/src ./services/video_renderer/src

# Set Python path
ENV PYTHONPATH=/app

# Create data directories
RUN mkdir -p /data/audio /data/videos /data/backgrounds /data/temp

CMD ["celery", "-A", "shared.python.celery_app.app", "worker", "--loglevel=info"]
