#!/bin/bash
# TikTok Auto Setup Script
# Run this script to set up the development environment

set -e

echo "🚀 TikTok Auto Setup"
echo "===================="

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Check if .env file exists
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env file with your actual credentials"
fi

# Create data directories if they don't exist
echo "📁 Creating data directories..."
mkdir -p data/backgrounds data/audio data/videos data/scripts data/logs

# Build Docker images
echo "🐳 Building Docker images..."
docker compose build

# Start infrastructure services first
echo "🏗️  Starting infrastructure services..."
docker compose up -d postgres redis elasticsearch

# Wait for services to be healthy
echo "⏳ Waiting for services to be ready..."
sleep 10

# Check PostgreSQL
echo "🔍 Checking PostgreSQL..."
until docker compose exec -T postgres pg_isready -U ${POSTGRES_USER:-tiktok_auto}; do
    echo "Waiting for PostgreSQL..."
    sleep 2
done
echo "✅ PostgreSQL is ready"

# Check Redis
echo "🔍 Checking Redis..."
until docker compose exec -T redis redis-cli ping | grep -q PONG; do
    echo "Waiting for Redis..."
    sleep 2
done
echo "✅ Redis is ready"

# Check Elasticsearch
echo "🔍 Checking Elasticsearch..."
until curl -s http://localhost:9200/_cluster/health | grep -q '"status":"green"\|"status":"yellow"'; do
    echo "Waiting for Elasticsearch..."
    sleep 5
done
echo "✅ Elasticsearch is ready"

# Pull Ollama model
echo "🤖 Starting Ollama and pulling model..."
docker compose up -d ollama
sleep 5
docker compose exec -T ollama ollama pull llama3.1:8b || echo "⚠️  Failed to pull Ollama model. You can pull it manually later."

# Start Piper TTS
echo "🔊 Starting Piper TTS..."
docker compose up -d piper
sleep 5

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your Reddit API credentials"
echo "2. Add background videos to data/backgrounds/"
echo "3. Run 'docker compose up' to start all services"
echo "4. Access the dashboard at http://localhost:8080"
echo ""
echo "To start all services: docker compose up -d"
echo "To view logs: docker compose logs -f"
echo "To stop services: docker compose down"
