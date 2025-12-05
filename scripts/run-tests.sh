#!/bin/bash
# TikTok Auto Test Runner Script
# Run this script to execute all tests

set -e

echo "🧪 TikTok Auto Test Runner"
echo "=========================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default options
COVERAGE=true
VERBOSE=false
SERVICE=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-coverage)
            COVERAGE=false
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -s|--service)
            SERVICE="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --no-coverage    Skip coverage report"
            echo "  -v, --verbose    Verbose output"
            echo "  -s, --service    Run tests for specific service"
            echo "  -h, --help       Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}⚠️  No virtual environment found. Creating one...${NC}"
    python -m venv venv
fi

# Activate virtual environment
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    source venv/Scripts/activate
else
    source venv/bin/activate
fi

# Install dependencies
echo "📦 Installing dependencies..."
pip install -q -r requirements-dev.txt
pip install -q -e shared/python

# Install service-specific dependencies
for service in services/*/; do
    if [ -f "$service/requirements.txt" ]; then
        pip install -q -r "$service/requirements.txt" 2>/dev/null || true
    fi
done

# Build pytest command
PYTEST_CMD="pytest"

if [ "$VERBOSE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD -v"
fi

if [ "$COVERAGE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD --cov=shared --cov=services --cov-report=term-missing --cov-report=html"
fi

# Run tests
echo ""
echo "🧪 Running tests..."
echo "==================="

if [ -n "$SERVICE" ]; then
    echo "Running tests for service: $SERVICE"
    $PYTEST_CMD "services/$SERVICE/tests/"
else
    echo "Running all tests..."
    $PYTEST_CMD
fi

TEST_EXIT_CODE=$?

# Print results
echo ""
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ All tests passed!${NC}"
else
    echo -e "${RED}❌ Some tests failed${NC}"
fi

if [ "$COVERAGE" = true ]; then
    echo ""
    echo "📊 Coverage report generated in htmlcov/index.html"
fi

exit $TEST_EXIT_CODE
