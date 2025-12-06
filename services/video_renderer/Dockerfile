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

# Install setuptools (required for shared package)
RUN pip install --no-cache-dir setuptools wheel

# Copy shared library first
COPY shared/python /app/shared/python

# Install shared library
RUN pip install -e /app/shared/python

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
