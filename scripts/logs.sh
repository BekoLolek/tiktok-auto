#!/bin/bash
# TikTok Auto - View Logs
# Usage: ./scripts/logs.sh [service] [--follow]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

SERVICE=""
FOLLOW=""
LINES=100

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--follow)
            FOLLOW="-f"
            shift
            ;;
        -n|--lines)
            LINES="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [service] [options]"
            echo ""
            echo "Services:"
            echo "  dashboard      Approval dashboard"
            echo "  reddit-fetch   Reddit fetcher"
            echo "  text-processor Text processor"
            echo "  tts-service    TTS synthesizer"
            echo "  video-renderer Video renderer"
            echo "  uploader       TikTok uploader"
            echo "  celery-worker  Celery worker"
            echo "  celery-beat    Celery scheduler"
            echo "  postgres       PostgreSQL database"
            echo "  redis          Redis cache"
            echo ""
            echo "Options:"
            echo "  -f, --follow   Follow log output"
            echo "  -n, --lines    Number of lines to show (default: 100)"
            echo "  -h, --help     Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                    # Show all logs"
            echo "  $0 dashboard -f       # Follow dashboard logs"
            echo "  $0 uploader -n 50     # Show last 50 uploader logs"
            exit 0
            ;;
        *)
            if [ -z "$SERVICE" ]; then
                SERVICE="$1"
            fi
            shift
            ;;
    esac
done

if [ -n "$SERVICE" ]; then
    docker compose logs $FOLLOW --tail=$LINES "$SERVICE"
else
    docker compose logs $FOLLOW --tail=$LINES
fi
