FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

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
COPY services/text_processor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY services/text_processor/src ./src

# Set Python path
ENV PYTHONPATH=/app

# Default command - can be overridden for Celery worker
CMD ["python", "-c", "print('Text processor ready')"]
