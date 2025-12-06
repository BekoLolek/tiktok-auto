#!/bin/bash
# TikTok Auto - Start Services
# Usage: ./scripts/start.sh [--infra-only|--all]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Default mode
MODE="all"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --infra-only)
            MODE="infra"
            shift
            ;;
        --all)
            MODE="all"
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --infra-only   Start only infrastructure (postgres, redis, etc)"
            echo "  --all          Start all services (default)"
            echo "  -h, --help     Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo -e "${GREEN}Starting TikTok Auto...${NC}"

# Check for .env file
if [ ! -f .env ]; then
    echo -e "${YELLOW}Warning: .env file not found. Creating from template...${NC}"
    cp .env.example .env
    echo "Please edit .env with your credentials before continuing."
    exit 1
fi

# Create data directories
mkdir -p data/backgrounds data/audio data/videos data/scripts data/logs data/backups

if [ "$MODE" == "infra" ]; then
    echo "Starting infrastructure services only..."
    docker compose up -d postgres redis elasticsearch ollama piper prometheus grafana
else
    echo "Starting all services..."
    docker compose up -d
fi

echo ""
echo -e "${GREEN}Services started!${NC}"
echo ""
echo "Dashboard:    http://localhost:8080"
echo "Uploader:     http://localhost:3000"
echo "Grafana:      http://localhost:3001"
echo "Prometheus:   http://localhost:9090"
echo ""
echo "View logs: ./scripts/logs.sh"
echo "Check status: ./scripts/status.sh"
