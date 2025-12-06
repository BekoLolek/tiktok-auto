FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including FFmpeg
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
COPY shared/python /app/shared/python

# Install shared library dependencies
RUN pip install --no-cache-dir \
    sqlalchemy>=2.0.0 \
    psycopg2-binary>=2.9.0 \
    celery>=5.3.0 \
    redis>=5.0.0 \
    elasticsearch>=8.11.0 \
    pydantic>=2.0.0 \
    pydantic-settings>=2.0.0

# Copy service requirements and install
COPY services/video_renderer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY services/video_renderer/src ./src

# Set Python path
ENV PYTHONPATH=/app

# Create data directories
RUN mkdir -p /data/backgrounds /data/audio /data/videos /data/temp

CMD ["python", "-c", "print('Video renderer ready')"]
