# TikTok Auto

Automated pipeline for converting Reddit stories into TikTok videos with AI-powered narration.

## Architecture

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Reddit    │───▶│    Text     │───▶│     TTS     │───▶│   Video     │───▶│   TikTok    │
│   Fetch     │    │  Processor  │    │   Service   │    │  Renderer   │    │  Uploader   │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
       │                  │                  │                  │                  │
       └──────────────────┴──────────────────┴──────────────────┴──────────────────┘
                                          │
                              ┌───────────┴───────────┐
                              │   Approval Dashboard   │
                              │   (Human-in-the-loop)  │
                              └───────────────────────┘
```

## Services

| Service | Technology | Description |
|---------|------------|-------------|
| `reddit_fetch` | Python/PRAW | Fetches stories from configured subreddits |
| `approval_dashboard` | FastAPI/Jinja2 | Web UI for reviewing and approving stories |
| `text_processor` | Python/Ollama | Adds hooks, CTAs, and splits long stories |
| `tts_service` | Python/Piper | Generates AI voice narration |
| `video_renderer` | Python/MoviePy | Creates videos with captions and backgrounds |
| `uploader` | Node.js/Puppeteer | Automates TikTok uploads |

## Quick Start

### Prerequisites

- Docker & Docker Compose
- 8GB+ RAM recommended
- Reddit API credentials
- TikTok Creator account

### Setup

1. **Clone and configure**
   ```bash
   git clone https://github.com/your-org/tiktok-auto.git
   cd tiktok-auto
   cp .env.example .env
   # Edit .env with your credentials
   ```

2. **Start services**
   ```bash
   docker-compose up -d
   ```

3. **Access dashboard**
   - Dashboard: http://localhost:8080
   - Grafana: http://localhost:3001

4. **Initialize TikTok session**
   - Visit http://localhost:3000/login
   - Complete TikTok login manually

## Configuration

See `.env.example` for all configuration options:

| Variable | Description | Default |
|----------|-------------|---------|
| `REDDIT_SUBREDDITS` | Subreddits to fetch | scifi,fantasy,tifu,nosleep |
| `TIKTOK_DAILY_UPLOAD_LIMIT` | Max uploads per day | 10 |
| `OLLAMA_MODEL` | LLM for text processing | llama3.1:8b |
| `FILE_RETENTION_DAYS` | Days to keep files | 7 |

## Pipeline Flow

1. **Fetch**: Reddit stories are fetched based on configured subreddits
2. **Approve**: Human reviews stories in dashboard, approves/rejects
3. **Process**: Approved stories get hooks, CTAs, and are split if too long
4. **Narrate**: Piper TTS generates audio narration
5. **Render**: MoviePy creates video with Minecraft gameplay + captions
6. **Upload**: Puppeteer automates TikTok upload (with manual fallback)

## Monitoring

- **Grafana**: http://localhost:3001 - Pipeline metrics and dashboards
- **Prometheus**: http://localhost:9090 - Raw metrics
- **Logs**: Structured JSON logs sent to Elasticsearch

## Documentation

- [Usage Guide](docs/USAGE.md) - Complete setup and operation guide
- [Operations Runbook](docs/RUNBOOK.md) - Deployment, troubleshooting, procedures

## Scripts

```bash
./scripts/start.sh       # Start all services
./scripts/stop.sh        # Stop services
./scripts/status.sh      # Check service health
./scripts/logs.sh        # View logs
./scripts/fetch.sh       # Trigger Reddit fetch
./scripts/cleanup.sh     # Remove old files
./scripts/backup.sh      # Backup database
./scripts/restore.sh     # Restore from backup
./scripts/run-tests.sh   # Run test suite
./scripts/setup.sh       # Initial setup
```

## Development

### Run Tests

```bash
# Python tests
pytest

# Node.js tests
cd services/uploader && npm test

# Lint
ruff check .
```

### Build Images

```bash
docker-compose build
```

## License

MIT
