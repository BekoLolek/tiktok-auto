#!/bin/bash
# TikTok Auto - Check Service Status
# Usage: ./scripts/status.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}TikTok Auto - Service Status${NC}"
echo "=============================="
echo ""

# Docker service status
echo -e "${BLUE}Docker Services:${NC}"
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

echo ""

# Health checks
echo -e "${BLUE}Health Checks:${NC}"

# Dashboard
if curl -s http://localhost:8080/health > /dev/null 2>&1; then
    echo -e "  Dashboard:    ${GREEN}healthy${NC}"
else
    echo -e "  Dashboard:    ${RED}unhealthy${NC}"
fi

# Uploader
if curl -s http://localhost:3000/health > /dev/null 2>&1; then
    echo -e "  Uploader:     ${GREEN}healthy${NC}"
else
    echo -e "  Uploader:     ${RED}unhealthy${NC}"
fi

# PostgreSQL
if docker compose exec -T postgres pg_isready -U ${POSTGRES_USER:-tiktok_auto} > /dev/null 2>&1; then
    echo -e "  PostgreSQL:   ${GREEN}healthy${NC}"
else
    echo -e "  PostgreSQL:   ${RED}unhealthy${NC}"
fi

# Redis
if docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then
    echo -e "  Redis:        ${GREEN}healthy${NC}"
else
    echo -e "  Redis:        ${RED}unhealthy${NC}"
fi

# Elasticsearch
if curl -s http://localhost:9200/_cluster/health 2>/dev/null | grep -q '"status"'; then
    ES_STATUS=$(curl -s http://localhost:9200/_cluster/health | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
    if [ "$ES_STATUS" == "green" ] || [ "$ES_STATUS" == "yellow" ]; then
        echo -e "  Elasticsearch: ${GREEN}$ES_STATUS${NC}"
    else
        echo -e "  Elasticsearch: ${RED}$ES_STATUS${NC}"
    fi
else
    echo -e "  Elasticsearch: ${RED}unhealthy${NC}"
fi

# Prometheus
if curl -s http://localhost:9090/-/healthy > /dev/null 2>&1; then
    echo -e "  Prometheus:   ${GREEN}healthy${NC}"
else
    echo -e "  Prometheus:   ${RED}unhealthy${NC}"
fi

# Grafana
if curl -s http://localhost:3001/api/health > /dev/null 2>&1; then
    echo -e "  Grafana:      ${GREEN}healthy${NC}"
else
    echo -e "  Grafana:      ${RED}unhealthy${NC}"
fi

echo ""

# Database stats
echo -e "${BLUE}Database Stats:${NC}"
docker compose exec -T postgres psql -U ${POSTGRES_USER:-tiktok_auto} -d ${POSTGRES_DB:-tiktok_auto} -c "
SELECT
    (SELECT COUNT(*) FROM stories WHERE status = 'pending') as pending,
    (SELECT COUNT(*) FROM stories WHERE status = 'approved') as approved,
    (SELECT COUNT(*) FROM stories WHERE status = 'processing') as processing,
    (SELECT COUNT(*) FROM stories WHERE status = 'completed') as completed,
    (SELECT COUNT(*) FROM stories WHERE status = 'failed') as failed;
" 2>/dev/null || echo "  Could not connect to database"

echo ""

# Disk usage
echo -e "${BLUE}Disk Usage:${NC}"
if [ -d "data" ]; then
    du -sh data/*/ 2>/dev/null | sed 's/^/  /'
else
    echo "  data/ directory not found"
fi

echo ""
echo "Dashboard: http://localhost:8080"
echo "Grafana:   http://localhost:3001"
