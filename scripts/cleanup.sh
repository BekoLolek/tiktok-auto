#!/bin/bash
# TikTok Auto - Cleanup Old Files
# Usage: ./scripts/cleanup.sh [--days 7] [--dry-run]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Defaults
DAYS=${FILE_RETENTION_DAYS:-7}
DRY_RUN=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --days)
            DAYS="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --days N     Delete files older than N days (default: 7)"
            echo "  --dry-run    Show what would be deleted without deleting"
            echo "  -h, --help   Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo -e "${YELLOW}TikTok Auto - File Cleanup${NC}"
echo "=========================="
echo "Retention period: $DAYS days"
echo ""

# Directories to clean
DIRS=("data/audio" "data/videos" "data/scripts")

for dir in "${DIRS[@]}"; do
    if [ -d "$dir" ]; then
        echo -e "${GREEN}Scanning $dir...${NC}"

        if [ "$DRY_RUN" = true ]; then
            FILES=$(find "$dir" -type f -mtime +$DAYS 2>/dev/null | wc -l)
            SIZE=$(find "$dir" -type f -mtime +$DAYS -exec du -ch {} + 2>/dev/null | tail -1 | cut -f1)
            echo "  Would delete: $FILES files ($SIZE)"
            find "$dir" -type f -mtime +$DAYS 2>/dev/null | head -5
            if [ "$FILES" -gt 5 ]; then
                echo "  ... and $((FILES - 5)) more"
            fi
        else
            BEFORE=$(du -sh "$dir" 2>/dev/null | cut -f1)
            find "$dir" -type f -mtime +$DAYS -delete 2>/dev/null || true
            # Also remove empty directories
            find "$dir" -type d -empty -delete 2>/dev/null || true
            AFTER=$(du -sh "$dir" 2>/dev/null | cut -f1)
            echo "  Cleaned: $BEFORE -> $AFTER"
        fi
    else
        echo -e "${YELLOW}Directory not found: $dir${NC}"
    fi
done

# Clean Docker resources
echo ""
echo -e "${GREEN}Cleaning Docker resources...${NC}"

if [ "$DRY_RUN" = true ]; then
    echo "  Would prune: dangling images and build cache"
else
    docker system prune -f --filter "until=${DAYS}d" 2>/dev/null || true
    echo "  Docker cleanup complete"
fi

echo ""
if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}Dry run complete. No files were deleted.${NC}"
    echo "Run without --dry-run to actually delete files."
else
    echo -e "${GREEN}Cleanup complete!${NC}"
fi
