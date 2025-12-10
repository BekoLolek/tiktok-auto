# TikTok Auto

[![CI](https://github.com/BekoLolek/tiktok-auto/actions/workflows/ci.yml/badge.svg)](https://github.com/BekoLolek/tiktok-auto/actions/workflows/ci.yml)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![Node.js 20](https://img.shields.io/badge/node.js-20-green.svg)](https://nodejs.org/)
[![Docker](https://img.shields.io/badge/docker-compose-blue.svg)](https://docs.docker.com/compose/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An automated pipeline for converting Reddit stories into TikTok videos with AI-powered narration, human-in-the-loop approval, and automated uploads.

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Services Overview](#services-overview)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Pipeline Flow](#pipeline-flow)
- [Database Schema](#database-schema)
- [API Reference](#api-reference)
- [Monitoring & Observability](#monitoring--observability)
- [Scripts Reference](#scripts-reference)
- [Development](#development)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

## Features

- **Automated Reddit Fetching** - Configurable subreddit scraping with rate limiting
- **Human-in-the-Loop Approval** - Web dashboard for reviewing and approving stories
- **AI-Powered Text Processing** - Ollama LLM integration for adding hooks, CTAs, and story splitting
- **Text-to-Speech Narration** - Multiple TTS engines (Piper, gTTS, edge-tts)
- **Video Rendering** - MoviePy-based video creation with Whisper-generated captions
- **Automated TikTok Uploads** - Puppeteer browser automation with session persistence
- **Manual Upload Fallback** - Graceful degradation when automation fails
- **Multi-Part Series Support** - Automatic splitting and batch tracking for long stories
- **Comprehensive Monitoring** - Prometheus metrics, Grafana dashboards, Elasticsearch logging
- **Scheduled Operations** - Celery Beat for periodic tasks (fetching, cleanup, retries)

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                    NGINX (Reverse Proxy)                             │
│                                    Port 80/443 + Rate Limiting                       │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                              │
              ┌───────────────────────────────┼───────────────────────────────┐
              │                               │                               │
              ▼                               ▼                               ▼
┌─────────────────────────┐    ┌─────────────────────────┐    ┌─────────────────────────┐
│   Approval Dashboard    │    │     Uploader Service    │    │    Monitoring Stack     │
│   (FastAPI + Jinja2)    │    │   (Node.js + Puppeteer) │    │  Prometheus + Grafana   │
│       Port 8080         │    │       Port 3000         │    │    Port 9090 / 3001     │
└─────────────────────────┘    └─────────────────────────┘    └─────────────────────────┘
              │                               │                               │
              └───────────────────────────────┼───────────────────────────────┘
                                              │
┌─────────────────────────────────────────────┴─────────────────────────────────────────┐
│                              Celery Task Queue (Redis Broker)                         │
└───────────────────────────────────────────────────────────────────────────────────────┘
              │                               │                               │
              ▼                               ▼                               ▼
┌─────────────────────────┐    ┌─────────────────────────┐    ┌─────────────────────────┐
│     Reddit Fetcher      │    │    Text Processor       │    │      TTS Service        │
│     (PRAW + Celery)     │    │   (Ollama LLM + Celery) │    │   (Piper/gTTS + Celery) │
└─────────────────────────┘    └─────────────────────────┘    └─────────────────────────┘
                                              │
                                              ▼
                               ┌─────────────────────────┐
                               │    Video Renderer       │
                               │  (MoviePy + Whisper)    │
                               └─────────────────────────┘
                                              │
              ┌───────────────────────────────┼───────────────────────────────┐
              │                               │                               │
              ▼                               ▼                               ▼
┌─────────────────────────┐    ┌─────────────────────────┐    ┌─────────────────────────┐
│      PostgreSQL 15      │    │        Redis 7          │    │   Elasticsearch 8.11   │
│       Port 5432         │    │       Port 6379         │    │       Port 9200         │
│   (Primary Database)    │    │   (Cache + Broker)      │    │   (Log Aggregation)     │
└─────────────────────────┘    └─────────────────────────┘    └─────────────────────────┘
```

### Data Flow

```
Reddit API ──▶ Fetch Stories ──▶ PostgreSQL (status: pending)
                                        │
                                        ▼
                              Dashboard (Human Review)
                                        │
                              ┌─────────┴─────────┐
                              ▼                   ▼
                          Approved            Rejected
                              │                   │
                              ▼                   ▼
                      Text Processing         (Archived)
                       (Ollama LLM)
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
              Single Part         Multi-Part (>60s)
                    │                   │
                    └─────────┬─────────┘
                              ▼
                      TTS Generation
                      (Piper/gTTS)
                              │
                              ▼
                      Video Rendering
                    (MoviePy + Whisper)
                              │
                              ▼
                      TikTok Upload
                      (Puppeteer)
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
                Success            Failed (3 retries)
                    │                   │
                    ▼                   ▼
                (Complete)       Manual Upload Mode
```

## Services Overview

### Core Application Services

| Service | Technology | Port | Description |
|---------|------------|------|-------------|
| **approval_dashboard** | Python/FastAPI | 8080 | Web UI for human review & approval of fetched stories |
| **reddit_fetch** | Python/PRAW | - | Fetches stories from configured subreddits (Celery task) |
| **text_processor** | Python/Ollama | - | LLM integration for hooks, CTAs, and story splitting |
| **tts_service** | Python/Piper/gTTS | - | Text-to-speech audio generation |
| **video_renderer** | Python/MoviePy | - | Video creation with captions using Whisper |
| **uploader** | Node.js/Puppeteer | 3000 | TikTok automation with fallback to manual upload |

### Infrastructure Services

| Service | Technology | Port | Description |
|---------|------------|------|-------------|
| **postgres** | PostgreSQL 15 | 5432 | Primary database for all entities |
| **redis** | Redis 7 | 6379 | Message broker for Celery + caching |
| **elasticsearch** | Elasticsearch 8.11 | 9200 | Structured logging & log aggregation |
| **ollama** | Ollama | 11434 | LLM engine (llama3.1:8b) for text processing |
| **piper** | Wyoming Piper | 10200 | TTS synthesis engine |

### Monitoring & Infrastructure

| Service | Technology | Port | Description |
|---------|------------|------|-------------|
| **prometheus** | Prometheus 2.47 | 9090 | Time-series metrics collection |
| **grafana** | Grafana 10.2 | 3001 | Dashboards & visualization |
| **nginx** | Nginx Alpine | 80/443 | Reverse proxy with rate limiting |
| **celery-worker** | Python/Celery | - | Background job processor (concurrency=2) |
| **celery-beat** | Python/Celery | - | Task scheduler for periodic jobs |

## Tech Stack

### Languages
- **Python 3.11** - Backend services (5 microservices)
- **Node.js 20** - TikTok uploader service
- **JavaScript** - Browser automation scripts

### Python Libraries
| Category | Libraries |
|----------|-----------|
| **Web Framework** | FastAPI, Jinja2, Uvicorn |
| **Database** | SQLAlchemy, psycopg2, Alembic |
| **Task Queue** | Celery, Redis |
| **Reddit API** | PRAW |
| **Text Processing** | Ollama API |
| **TTS** | gTTS, edge-tts, Piper (Wyoming) |
| **Video** | MoviePy, OpenAI Whisper, FFmpeg |
| **Monitoring** | prometheus-client, elasticsearch |
| **Testing** | pytest, pytest-cov, responses, factory-boy |
| **Linting** | ruff, mypy |

### Node.js Libraries
| Category | Libraries |
|----------|-----------|
| **Web Framework** | Express |
| **Browser Automation** | Puppeteer |
| **Database** | pg (PostgreSQL) |
| **Logging** | winston |
| **Monitoring** | prom-client |
| **Testing** | Jest |

### Infrastructure
- **Docker & Docker Compose** - Containerization
- **PostgreSQL 15** - Relational database
- **Redis 7** - Message broker & cache
- **Elasticsearch 8.11** - Log aggregation
- **Prometheus** - Metrics collection
- **Grafana** - Visualization
- **Nginx** - Reverse proxy

## Quick Start

### Prerequisites

- Docker & Docker Compose v2+
- 8GB+ RAM recommended (16GB for optimal performance)
- Reddit API credentials ([create app](https://www.reddit.com/prefs/apps))
- TikTok Creator account

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/BekoLolek/tiktok-auto.git
   cd tiktok-auto
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

3. **Start all services**
   ```bash
   docker-compose up -d
   ```

4. **Initialize TikTok session**
   - Navigate to http://localhost:3000/login
   - Complete TikTok login manually (one-time setup)
   - Session cookies are persisted for future use

5. **Access the dashboard**
   - **Dashboard**: http://localhost:8080 - Review and approve stories
   - **Grafana**: http://localhost:3001 - Monitor pipeline metrics
   - **Prometheus**: http://localhost:9090 - Raw metrics

### Verify Installation

```bash
# Check service health
./scripts/status.sh

# View logs
./scripts/logs.sh -f

# Trigger a test fetch
./scripts/fetch.sh
```

## Configuration

### Required Environment Variables

```bash
# Database
POSTGRES_USER=tiktok_auto
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DB=tiktok_auto
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# Reddit API (required)
REDDIT_CLIENT_ID=your_client_id
REDDIT_SECRET=your_secret
REDDIT_USER_AGENT=TikTokAuto/1.0 (by /u/your_username)
```

### Optional Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `REDDIT_SUBREDDITS` | Comma-separated subreddits to fetch | `scifi,fantasy,tifu,nosleep` |
| `REDDIT_FETCH_LIMIT` | Max stories per fetch | `25` |
| `REDDIT_FETCH_HOUR` | Cron schedule (hour) | `*/2` (every 2 hours) |
| `TIKTOK_DAILY_UPLOAD_LIMIT` | Max uploads per day | `10` |
| `MAX_UPLOAD_RETRIES` | Retry attempts before manual mode | `3` |
| `OLLAMA_MODEL` | LLM model for text processing | `llama3.1:8b` |
| `FILE_RETENTION_DAYS` | Days to keep generated files | `7` |
| `LOG_LEVEL` | Logging verbosity | `INFO` |
| `METRICS_ENABLED` | Enable Prometheus metrics | `true` |

### Monitoring Credentials

```bash
GRAFANA_USER=admin
GRAFANA_PASSWORD=your_secure_password
```

See [.env.example](.env.example) for complete configuration options.

## Pipeline Flow

### 1. Fetch Phase
- Celery Beat triggers `fetch_reddit()` task on schedule
- PRAW fetches stories from configured subreddits
- Stories stored in PostgreSQL with `status: pending`
- Rate limiting prevents API abuse

### 2. Approval Phase (Human-in-the-Loop)
- Stories appear in web dashboard at http://localhost:8080
- Human reviews content, approves or rejects
- Approved stories queued for processing

### 3. Processing Phase
- `process_story()` Celery task executes
- Ollama LLM adds:
  - **Hook**: Attention-grabbing intro
  - **CTA**: Call-to-action ending
- Long stories (>60 seconds) split into parts
- Creates Script records (one per part)

### 4. Audio Phase
- `generate_audio()` task for each script
- TTS engine (Piper or gTTS) generates narration
- Audio files stored in `/data/audio/`
- Duration tracked for video timing

### 5. Video Phase
- `render_video()` task for each audio
- MoviePy combines:
  - Background gameplay video
  - Audio narration
  - Whisper-generated captions
- Output stored in `/data/videos/`

### 6. Upload Phase
- `upload_video()` queues to uploader service
- Puppeteer automates TikTok upload
- On failure: retries up to `MAX_UPLOAD_RETRIES`
- Final failure: marks as `manual_required`
- Manual uploads available via dashboard

## Database Schema

### Entity Relationship

```
stories (1) ──────── (N) scripts (1) ──────── (1) audio (1) ──────── (1) videos (1) ──────── (1) uploads
    │                        │
    │                        │
    └──────── (1) batches (N)┘
                  │
    └──────── (1) pipeline_runs
```

### Tables

| Table | Description | Key Fields |
|-------|-------------|------------|
| `stories` | Fetched Reddit posts | `reddit_id`, `subreddit`, `title`, `content`, `status`, `char_count` |
| `scripts` | Processed text segments | `story_id`, `part_number`, `total_parts`, `hook`, `content`, `cta` |
| `audio` | Generated audio files | `script_id`, `file_path`, `duration_seconds`, `voice_model` |
| `videos` | Rendered video files | `audio_id`, `file_path`, `duration_seconds`, `has_captions` |
| `uploads` | TikTok upload records | `video_id`, `status`, `platform_video_id`, `retry_count` |
| `batches` | Multi-part story groups | `story_id`, `total_parts`, `completed_parts`, `status` |
| `pipeline_runs` | Execution audit trail | `story_id`, `batch_id`, `current_step`, `error_message` |

### Status Transitions

**Story Status**:
```
pending → approved → scripting → generating_audio → rendering_video → uploading → completed
    │         │
    ▼         ▼
rejected    failed
```

**Upload Status**:
```
pending → uploading → success
              │
              ▼
          failed → manual_required
```

## API Reference

### Dashboard API (Port 8080)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Dashboard home page |
| `/stories` | GET | List all stories with filters |
| `/stories/{id}` | GET | Story detail view |
| `/stories/{id}/approve` | POST | Approve story for processing |
| `/stories/{id}/reject` | POST | Reject story |
| `/uploads` | GET | List upload status |
| `/uploads/{id}/download` | GET | Download video for manual upload |
| `/health` | GET | Health check endpoint |
| `/metrics` | GET | Prometheus metrics |

### Uploader API (Port 3000)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/login` | GET | TikTok login page (manual auth) |
| `/upload` | POST | Queue video upload |
| `/status/{id}` | GET | Check upload status |
| `/health` | GET | Health check |
| `/metrics` | GET | Prometheus metrics |

## Monitoring & Observability

### Grafana Dashboards
Access at http://localhost:3001 (default: admin/admin)

- **Pipeline Overview** - Success rates, processing times, queue depths
- **Service Health** - CPU, memory, error rates per service
- **Upload Metrics** - TikTok upload success/failure rates
- **Infrastructure** - Database connections, Redis memory, disk usage

### Prometheus Metrics
Access at http://localhost:9090

Key metrics:
- `pipeline_stories_processed_total` - Total stories processed
- `pipeline_uploads_success_total` - Successful uploads
- `pipeline_uploads_failed_total` - Failed uploads
- `celery_task_duration_seconds` - Task execution times
- `http_request_duration_seconds` - API response times

### Logging
- Structured JSON logs sent to Elasticsearch
- Query logs via Kibana or direct ES API
- Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL

### Alerting
Prometheus alerting rules configured in `config/prometheus/alerts.yml`:
- Service down alerts
- High error rate alerts
- Queue backup alerts
- Disk space warnings

## Scripts Reference

```bash
# Service Management
./scripts/start.sh           # Start all services
./scripts/stop.sh            # Stop all services
./scripts/status.sh          # Check service health

# Operations
./scripts/fetch.sh           # Trigger Reddit fetch manually
./scripts/cleanup.sh         # Remove old files (default: 7 days)
./scripts/cleanup.sh --days 3  # Custom retention

# Logging
./scripts/logs.sh            # View all logs
./scripts/logs.sh -f         # Follow logs (tail -f)
./scripts/logs.sh <service>  # View specific service logs

# Backup & Recovery
./scripts/backup.sh          # Backup PostgreSQL database
./scripts/restore.sh <file>  # Restore from backup

# Development
./scripts/run-tests.sh       # Run full test suite
./scripts/setup.sh           # Initial setup wizard
```

## Development

### Local Setup

```bash
# Install Python dependencies
pip install -r requirements-dev.txt

# Install Node.js dependencies
cd services/uploader && npm install

# Run services locally (requires running infrastructure)
docker-compose up -d postgres redis elasticsearch
python -m services.approval_dashboard.src.main
```

### Code Structure

```
tiktok-auto/
├── services/
│   ├── approval_dashboard/    # FastAPI web dashboard
│   ├── reddit_fetch/          # Reddit scraper
│   ├── text_processor/        # Ollama LLM integration
│   ├── tts_service/           # Text-to-speech
│   ├── video_renderer/        # MoviePy video creation
│   └── uploader/              # Node.js TikTok uploader
├── shared/
│   └── python/
│       ├── celery_app/        # Celery configuration
│       ├── db/                # SQLAlchemy models
│       ├── logging/           # Structured logging
│       └── monitoring/        # Health checks & metrics
├── config/
│   ├── grafana/               # Dashboard provisioning
│   ├── nginx/                 # Reverse proxy config
│   └── prometheus/            # Scrape configs & alerts
├── docker/                    # Dockerfiles
├── scripts/                   # Operations scripts
├── tests/                     # Integration tests
└── data/                      # Generated files (gitignored)
```

### Linting

```bash
# Python linting
ruff check .
ruff format .

# Node.js linting
cd services/uploader && npm run lint
```

## Testing

### Run All Tests

```bash
# Python tests with coverage
pytest --cov=shared --cov=services --cov-report=html

# Node.js tests
cd services/uploader && npm test

# Full CI simulation
./scripts/run-tests.sh
```

### Test Structure

- **Unit tests**: `services/*/tests/`
- **Integration tests**: `tests/`
- **Fixtures**: `conftest.py` files
- **Mocks**: Factory Boy for models, responses for HTTP

### CI Pipeline

GitHub Actions runs on every push:
1. **Lint** - ruff check
2. **Python Tests** - pytest with PostgreSQL/Redis services
3. **Node.js Tests** - Jest
4. **Docker Build** - Verify all images build successfully

## Troubleshooting

### Common Issues

**Services not starting**
```bash
# Check Docker logs
docker-compose logs <service>

# Verify resources
docker stats
```

**TikTok login failing**
- Clear session: `rm -rf data/session/`
- Re-authenticate at http://localhost:3000/login
- Check for TikTok rate limiting

**Videos not rendering**
- Ensure FFmpeg is installed in worker container
- Check disk space: `df -h`
- Review worker logs: `docker-compose logs celery-worker`

**Upload stuck in "manual_required"**
- Download video from dashboard
- Upload manually to TikTok
- Mark as complete in dashboard

### Debug Mode

```bash
# Enable debug logging
LOG_LEVEL=DEBUG docker-compose up

# Check specific service
docker-compose logs -f text_processor
```

### Health Checks

```bash
# All services
./scripts/status.sh

# Database connectivity
docker-compose exec postgres pg_isready

# Redis connectivity
docker-compose exec redis redis-cli ping

# Celery workers
docker-compose exec celery-worker celery -A shared.celery_app inspect active
```

## Documentation

- [Usage Guide](docs/USAGE.md) - Complete setup and operation guide
- [Operations Runbook](docs/RUNBOOK.md) - Deployment, troubleshooting, procedures

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Run tests (`./scripts/run-tests.sh`)
4. Commit changes (`git commit -m 'Add amazing feature'`)
5. Push to branch (`git push origin feature/amazing-feature`)
6. Open a Pull Request

### Code Standards

- Python: Follow ruff rules (see `pyproject.toml`)
- Node.js: Follow ESLint configuration
- Commits: Use conventional commit messages
- Tests: Maintain >80% coverage

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**Note**: This project is for educational purposes. Ensure compliance with Reddit's API Terms of Service and TikTok's Community Guidelines when using this system.
