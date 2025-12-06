# TikTok Auto - Usage Guide

Complete guide for setting up, running, and operating the TikTok Auto pipeline.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Running the Pipeline](#running-the-pipeline)
5. [Daily Operations](#daily-operations)
6. [Troubleshooting](#troubleshooting)
7. [Scripts Reference](#scripts-reference)

---

## Prerequisites

### System Requirements

- **OS**: Linux, macOS, or Windows (WSL2 recommended)
- **RAM**: 8GB minimum, 16GB recommended
- **Disk**: 50GB+ free space for videos
- **Docker**: Docker Desktop or Docker Engine + Compose

### Accounts Needed

1. **Reddit API** - Create an app at https://www.reddit.com/prefs/apps
   - Type: "script"
   - Note your `client_id` and `client_secret`

2. **TikTok Creator Account** - For uploading videos
   - Must have posting capability enabled

### Software

```bash
# Check Docker is installed
docker --version
docker compose version

# Clone the repository
git clone https://github.com/your-org/tiktok-auto.git
cd tiktok-auto
```

---

## Installation

### Quick Setup

```bash
# Run the setup script
./scripts/setup.sh
```

This will:
- Create `.env` from template
- Create data directories
- Build Docker images
- Start infrastructure services
- Pull the Ollama model

### Manual Setup

1. **Create configuration file**
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` with your credentials**
   ```bash
   # Required settings
   REDDIT_CLIENT_ID=your_client_id
   REDDIT_SECRET=your_secret

   # Optional: Email notifications
   SMTP_HOST=smtp.gmail.com
   SMTP_USER=your_email@gmail.com
   SMTP_PASSWORD=your_app_password
   NOTIFICATION_EMAIL=alerts@yourdomain.com
   ```

3. **Create data directories**
   ```bash
   mkdir -p data/backgrounds data/audio data/videos data/scripts data/logs
   ```

4. **Add background videos**
   ```bash
   # Copy Minecraft parkour or similar videos to:
   cp your_background.mp4 data/backgrounds/
   ```

5. **Build and start**
   ```bash
   docker compose build
   docker compose up -d
   ```

---

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| **Reddit** | | |
| `REDDIT_CLIENT_ID` | Reddit API client ID | (required) |
| `REDDIT_SECRET` | Reddit API secret | (required) |
| `REDDIT_SUBREDDITS` | Comma-separated subreddits | scifi,fantasy,tifu,nosleep |
| `REDDIT_MIN_UPVOTES` | Minimum upvotes to fetch | 100 |
| `REDDIT_MIN_CHARS` | Minimum story length | 1500 |
| `REDDIT_MAX_CHARS` | Maximum story length | 15000 |
| **TikTok** | | |
| `TIKTOK_DAILY_UPLOAD_LIMIT` | Max uploads per day | 10 |
| `TIKTOK_MAX_RETRIES` | Upload retry attempts | 3 |
| **Processing** | | |
| `OLLAMA_MODEL` | LLM model for text | llama3.1:8b |
| `PIPER_VOICE_MALE` | Male voice model | en_US-lessac-medium |
| `PIPER_VOICE_FEMALE` | Female voice model | en_US-amy-medium |
| **Files** | | |
| `FILE_RETENTION_DAYS` | Days to keep files | 7 |
| `BACKUP_RETENTION_DAYS` | Days to keep backups | 30 |

### Subreddit Selection

Good subreddits for story content:

```bash
# Short stories (1 video)
REDDIT_SUBREDDITS=tifu,AmItheAsshole,pettyrevenge,MaliciousCompliance

# Long stories (multi-part series)
REDDIT_SUBREDDITS=nosleep,shortscarystories,creepypasta

# Mixed content
REDDIT_SUBREDDITS=scifi,fantasy,HFY,WritingPrompts
```

---

## Running the Pipeline

### Starting Services

```bash
# Start all services
./scripts/start.sh

# Start only infrastructure (database, redis, etc)
./scripts/start.sh --infra-only
```

### Accessing Interfaces

| Service | URL | Description |
|---------|-----|-------------|
| Dashboard | http://localhost:8080 | Approve stories, monitor pipeline |
| Grafana | http://localhost:3001 | Metrics and dashboards |
| Prometheus | http://localhost:9090 | Raw metrics |
| Uploader | http://localhost:3000 | TikTok upload status |

### First-Time TikTok Setup

1. Open http://localhost:3000/login in your browser
2. Complete the TikTok login manually
3. Session cookies will be saved automatically
4. Verify with: `curl http://localhost:3000/health`

### Pipeline Workflow

```
1. FETCH
   - Celery Beat triggers scheduled fetch (every 2 hours by default)
   - Or manually: ./scripts/fetch.sh
   - Stories appear in dashboard as "pending"

2. APPROVE
   - Open dashboard: http://localhost:8080
   - Review stories, click "Approve" or "Reject"
   - Approved stories enter processing queue

3. PROCESS
   - Text processor adds hooks and CTAs
   - Long stories are split into parts (60s each)
   - Scripts saved to database

4. GENERATE
   - TTS generates audio narration
   - Video renderer creates final video
   - Captions added automatically

5. UPLOAD
   - Automatic upload attempted via Puppeteer
   - If fails after retries → marked "manual_required"
   - Download from dashboard for manual upload
```

---

## Daily Operations

### Morning Checklist

```bash
# 1. Check service status
./scripts/status.sh

# 2. Review pending stories
# Open http://localhost:8080

# 3. Check for failed uploads
# Dashboard → Downloads section

# 4. Monitor upload quota
curl http://localhost:3000/health | jq '.uploads_today'
```

### Approving Stories

1. Go to http://localhost:8080/stories?status=pending
2. Click a story to read full content
3. Check:
   - Content quality and engagement potential
   - Length (will it need multiple parts?)
   - No copyright/sensitive content
4. Click **Approve** or **Reject**

### Handling Manual Uploads

When automatic upload fails:

1. Go to http://localhost:8080/downloads
2. Click **Download** to get the video file
3. Upload manually to TikTok
4. Click **Mark Uploaded** and paste the TikTok URL

### Scheduled Tasks

| Task | Schedule | Description |
|------|----------|-------------|
| Reddit Fetch | Every 2 hours | Fetches new stories |
| Process Uploads | Every 30 min | Uploads pending videos |
| Retry Failed | Every hour | Retries failed uploads |
| Cleanup | Daily at 3 AM | Removes old files |

---

## Troubleshooting

### Common Issues

#### Services won't start

```bash
# Check Docker status
docker compose ps

# View logs
./scripts/logs.sh

# Restart specific service
docker compose restart dashboard
```

#### TikTok login expired

```bash
# Clear session and re-login
docker compose exec uploader rm -rf /app/session/*
docker compose restart uploader
# Then visit http://localhost:3000/login
```

#### Database connection failed

```bash
# Check PostgreSQL
docker compose logs postgres

# Restart database
docker compose restart postgres

# Wait for health check
./scripts/status.sh
```

#### Videos not rendering

```bash
# Check video renderer logs
./scripts/logs.sh video-renderer -f

# Verify background videos exist
ls -la data/backgrounds/

# Check disk space
df -h
```

#### Celery tasks stuck

```bash
# Check worker status
./scripts/logs.sh celery-worker

# Restart workers
docker compose restart celery-worker celery-beat

# Clear Redis queue (WARNING: loses pending tasks)
docker compose exec redis redis-cli FLUSHDB
```

### Logs

```bash
# All logs
./scripts/logs.sh

# Specific service
./scripts/logs.sh dashboard
./scripts/logs.sh uploader
./scripts/logs.sh celery-worker

# Follow logs in real-time
./scripts/logs.sh -f

# Last 50 lines
./scripts/logs.sh -n 50
```

---

## Scripts Reference

### start.sh
Start all or selected services.

```bash
./scripts/start.sh              # Start all
./scripts/start.sh --infra-only # Infrastructure only
```

### stop.sh
Stop services.

```bash
./scripts/stop.sh                # Stop services
./scripts/stop.sh --remove-volumes  # Stop and delete data
```

### status.sh
Show service health and statistics.

```bash
./scripts/status.sh
```

### logs.sh
View service logs.

```bash
./scripts/logs.sh [service] [-f] [-n lines]

# Examples
./scripts/logs.sh                    # All logs
./scripts/logs.sh dashboard -f       # Follow dashboard
./scripts/logs.sh uploader -n 50     # Last 50 lines
```

### fetch.sh
Manually trigger Reddit fetch.

```bash
./scripts/fetch.sh
```

### cleanup.sh
Remove old files.

```bash
./scripts/cleanup.sh              # Delete files older than 7 days
./scripts/cleanup.sh --days 14    # Delete files older than 14 days
./scripts/cleanup.sh --dry-run    # Preview without deleting
```

### backup.sh
Backup the database.

```bash
./scripts/backup.sh

# Run inside Docker for production
docker compose exec postgres /scripts/backup.sh
```

### restore.sh
Restore from backup.

```bash
./scripts/restore.sh /path/to/backup.sql.gz
```

### run-tests.sh
Run the test suite.

```bash
./scripts/run-tests.sh              # All tests with coverage
./scripts/run-tests.sh -s dashboard # Only dashboard tests
./scripts/run-tests.sh --no-coverage # Skip coverage report
```

### setup.sh
Initial setup wizard.

```bash
./scripts/setup.sh
```

---

## Monitoring

### Grafana Dashboards

Access Grafana at http://localhost:3001 (default: admin/admin)

**Available Dashboards:**
- Pipeline Overview - Story counts, processing times
- Upload Metrics - Success/failure rates, retries
- System Health - Resource usage, errors

### Prometheus Metrics

Key metrics at http://localhost:9090:

```
# Stories
tiktok_auto_stories_fetched_total
tiktok_auto_stories_processed_total{status="completed|failed"}

# Uploads
tiktok_auto_uploads_total{status="success|failed"}
tiktok_auto_pending_uploads

# Performance
tiktok_auto_video_rendering_duration_seconds
tiktok_auto_audio_generation_duration_seconds
```

### Alerts

Configured alerts in Prometheus:
- High failure rate (>20% stories failing)
- Upload failures (>5 per hour)
- Service down (>2 minutes)
- Low disk space (<10%)

---

## Backup & Recovery

### Automated Backups

Add to crontab:
```bash
# Daily backup at 2 AM
0 2 * * * /path/to/tiktok-auto/scripts/backup.sh
```

### Manual Backup

```bash
./scripts/backup.sh
# Output: /data/backups/tiktok_auto_20240101_120000.sql.gz
```

### Restore

```bash
./scripts/restore.sh /data/backups/tiktok_auto_20240101_120000.sql.gz
```

---

## Support

- **Issues**: https://github.com/your-org/tiktok-auto/issues
- **Docs**: See [RUNBOOK.md](RUNBOOK.md) for operations procedures
