FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy shared library (need full path for shared.python.* imports)
COPY shared /app/shared

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
COPY services/tts_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY services/tts_service/src ./src

# Set Python path
ENV PYTHONPATH=/app

# Create audio output directory
RUN mkdir -p /data/audio

CMD ["python", "-c", "print('TTS service ready')"]
