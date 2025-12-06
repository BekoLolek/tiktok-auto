#!/bin/bash
# TikTok Auto - Manually Trigger Reddit Fetch
# Usage: ./scripts/fetch.sh [--subreddits "sub1,sub2"]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}Triggering Reddit Fetch...${NC}"
echo ""

# Check if Celery worker is running
if ! docker compose ps celery-worker | grep -q "Up"; then
    echo -e "${YELLOW}Warning: Celery worker is not running.${NC}"
    echo "Start it with: docker compose up -d celery-worker"
    exit 1
fi

# Send task to Celery
docker compose exec -T celery-worker python -c "
from shared.python.celery_app import celery_app
result = celery_app.send_task('celery_app.tasks.scheduled_fetch_reddit')
print(f'Task queued: {result.id}')
"

echo ""
echo -e "${GREEN}Fetch task queued!${NC}"
echo "Monitor progress with: ./scripts/logs.sh celery-worker -f"
