FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy shared library first
COPY shared/python /app/shared/python

# Install shared library
RUN pip install -e /app/shared/python

# Copy service requirements and install
COPY services/reddit_fetch/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY services/reddit_fetch/src ./src

# Set Python path
ENV PYTHONPATH=/app

CMD ["python", "-m", "src.main"]
