FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install setuptools (required for shared package)
RUN pip install --no-cache-dir setuptools wheel

# Copy shared library first
COPY shared/python /app/shared/python

# Install shared library
RUN pip install -e /app/shared/python

# Copy service requirements and install
COPY services/text_processor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY services/text_processor/src ./src

# Set Python path
ENV PYTHONPATH=/app

# Default command - can be overridden for Celery worker
CMD ["python", "-c", "print('Text processor ready')"]
