#!/bin/bash
# TikTok Auto - Stop Services
# Usage: ./scripts/stop.sh [--remove-volumes]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

REMOVE_VOLUMES=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --remove-volumes)
            REMOVE_VOLUMES=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --remove-volumes   Also remove Docker volumes (WARNING: deletes data!)"
            echo "  -h, --help         Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo -e "${YELLOW}Stopping TikTok Auto...${NC}"

if [ "$REMOVE_VOLUMES" = true ]; then
    echo -e "${RED}WARNING: This will delete all database data!${NC}"
    read -p "Are you sure? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Cancelled."
        exit 0
    fi
    docker compose down -v
    echo "Services stopped and volumes removed."
else
    docker compose down
    echo -e "${GREEN}Services stopped.${NC}"
fi
