# TikTok Auto Operations Runbook

## Table of Contents
1. [Deployment](#deployment)
2. [Common Operations](#common-operations)
3. [Troubleshooting](#troubleshooting)
4. [Manual Upload Procedures](#manual-upload-procedures)
5. [Backup and Recovery](#backup-and-recovery)
6. [Monitoring](#monitoring)

---

## Deployment

### Initial Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-org/tiktok-auto.git
   cd tiktok-auto
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

3. **Start the stack**
   ```bash
   docker-compose up -d
   ```

4. **Verify services are healthy**
   ```bash
   docker-compose ps
   # All services should show "healthy" status
   ```

5. **Initialize TikTok session**
   - Open http://localhost:3000/login in a browser
   - Log in to TikTok manually
   - Session will be saved automatically

### Updating

```bash
git pull origin main
docker-compose build
docker-compose up -d
```

---

## Common Operations

### Start/Stop Services

```bash
# Start all services
docker-compose up -d

# Stop all services
docker-compose down

# Restart specific service
docker-compose restart dashboard

# View logs
docker-compose logs -f dashboard
```

### Check Service Health

```bash
# Dashboard
curl http://localhost:8080/health

# Uploader
curl http://localhost:3000/health

# All services at once
docker-compose ps
```

### Trigger Manual Reddit Fetch

```bash
docker-compose exec celery-worker celery -A celery_app.app call celery_app.tasks.fetch_reddit \
    --args='[["scifi", "fantasy"], 25]'
```

### Process Approved Stories

```bash
docker-compose exec celery-worker celery -A celery_app.app call celery_app.tasks.process_approved_stories
```

### Check Queue Status

```bash
# View pending Celery tasks
docker-compose exec redis redis-cli LLEN celery

# View failed tasks
docker-compose exec redis redis-cli KEYS "celery-task-meta-*"
```

---

## Troubleshooting

### Service Won't Start

1. **Check logs**
   ```bash
   docker-compose logs <service-name>
   ```

2. **Verify dependencies**
   ```bash
   # Check if database is up
   docker-compose exec postgres pg_isready -U tiktok_auto

   # Check if Redis is up
   docker-compose exec redis redis-cli ping
   ```

3. **Reset service state**
   ```bash
   docker-compose down
   docker-compose up -d <service-name>
   ```

### Upload Failures

1. **Check upload status in database**
   ```sql
   SELECT * FROM uploads WHERE status = 'failed' ORDER BY created_at DESC LIMIT 10;
   ```

2. **Check TikTok session validity**
   ```bash
   curl http://localhost:3000/session/status
   ```

3. **Re-authenticate TikTok**
   - Visit http://localhost:3000/login
   - Complete manual login

4. **Retry failed uploads**
   ```bash
   docker-compose exec celery-worker celery -A celery_app.app call celery_app.tasks.retry_failed_uploads
   ```

### Database Connection Issues

1. **Check PostgreSQL status**
   ```bash
   docker-compose exec postgres pg_isready -U tiktok_auto
   ```

2. **Verify connection string**
   ```bash
   docker-compose exec dashboard env | grep POSTGRES
   ```

3. **Reset database connection pool**
   ```bash
   docker-compose restart dashboard
   ```

### High Memory Usage

1. **Check container stats**
   ```bash
   docker stats
   ```

2. **Restart memory-heavy services**
   ```bash
   docker-compose restart video-renderer celery-worker
   ```

3. **Clean up old files**
   ```bash
   docker-compose exec celery-worker celery -A celery_app.app call celery_app.tasks.cleanup_old_files
   ```

---

## Manual Upload Procedures

When automatic upload fails, follow these steps:

### 1. Identify Videos Requiring Manual Upload

```sql
SELECT v.id, v.file_path, s.title
FROM uploads u
JOIN videos v ON u.video_id = v.id
JOIN audio a ON v.audio_id = a.id
JOIN scripts sc ON a.script_id = sc.id
JOIN stories s ON sc.story_id = s.id
WHERE u.status = 'manual_required';
```

### 2. Download Video File

Videos are stored in `/data/videos/`. Access via:
```bash
docker cp tiktok-auto-video-renderer:/data/videos/<video_id>.mp4 ./
```

Or through the dashboard at: http://localhost:8080/downloads

### 3. Upload to TikTok Manually

1. Go to https://www.tiktok.com/creator
2. Upload the video file
3. Copy the generated video URL

### 4. Update Database

```bash
# Mark as uploaded
curl -X POST http://localhost:3000/upload/<upload_id>/complete \
    -H "Content-Type: application/json" \
    -d '{"platform_video_id": "TIKTOK_VIDEO_ID", "platform_url": "https://tiktok.com/..."}'
```

---

## Backup and Recovery

### Automated Backups

Backups run automatically via cron at 2 AM UTC:
```bash
# Manual backup
docker-compose exec postgres /scripts/backup.sh
```

Backups are stored in `/backups/` with 30-day retention.

### Restore from Backup

```bash
# List available backups
ls -la /backups/

# Restore specific backup
docker-compose exec postgres /scripts/restore.sh /backups/tiktok_auto_20240101_120000.sql.gz
```

### Media File Backup

Video and audio files are in `/data/`. Back up externally:
```bash
rsync -av ./data/ /path/to/backup/data/
```

---

## Monitoring

### Access Dashboards

| Service | URL | Default Credentials |
|---------|-----|---------------------|
| Grafana | http://localhost:3001 | admin / (from .env) |
| Prometheus | http://localhost:9090 | - |
| Dashboard | http://localhost:8080 | - |

### Key Metrics to Monitor

- **Stories Pending**: Should be < 100
- **Failed Uploads**: Should be 0
- **Processing Time p95**: Should be < 5 minutes
- **Error Rate**: Should be < 1%

### Alert Conditions

| Condition | Action |
|-----------|--------|
| Failed uploads > 5 | Check TikTok session, retry uploads |
| Pending stories > 200 | Check Reddit fetch, approval process |
| Processing time > 10min | Check Ollama/Piper services |
| Service unhealthy | Restart service, check logs |

### Log Analysis

```bash
# Search logs for errors
docker-compose logs --since 1h | grep -i error

# Search specific service
docker-compose logs celery-worker | grep -i failed
```

---

## Emergency Procedures

### Complete Stack Reset

```bash
# Stop everything
docker-compose down

# Remove volumes (CAUTION: deletes all data)
docker-compose down -v

# Fresh start
docker-compose up -d
```

### Recover from Corrupted Database

1. Stop all services
2. Restore from last good backup
3. Restart services
4. Verify data integrity

```bash
docker-compose down
docker-compose up -d postgres
docker-compose exec postgres /scripts/restore.sh /backups/latest.sql.gz
docker-compose up -d
```
