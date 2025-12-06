# Phase 4 & 5: Implementation Plan

## Completed Phases Summary
- **Phase 1**: Project setup, Docker Compose (11 services), GitHub CI/CD
- **Phase 2**: Shared libraries (DB models, Celery, logging, email notifications)
- **Phase 3**: Core services with 142 passing tests:
  - `reddit_fetch` - PRAW-based Reddit story fetching
  - `approval_dashboard` - FastAPI web UI for story approval
  - `text_processor` - Ollama LLM for hooks/CTAs/splitting
  - `tts_service` - Piper TTS audio synthesis
  - `video_renderer` - MoviePy + Whisper captions

---

## Phase 4: TikTok Uploader & Pipeline Integration

### 4.1 TikTok Uploader Service (Node.js)
**Location**: `services/uploader/`

#### Implementation Tasks:
1. **Puppeteer Automation**
   - Browser automation for TikTok Creator Studio
   - Handle login flow with session persistence
   - Video file upload with progress tracking
   - Fill title, description, hashtags
   - Handle CAPTCHA detection (fallback to manual)

2. **Session Management**
   - Cookie storage/restoration for persistent login
   - Session health checking before uploads
   - Automatic re-authentication when needed

3. **Upload Queue Processing**
   - Poll database for pending uploads
   - Rate limiting (respect TikTok limits)
   - Retry logic with exponential backoff
   - Update Upload model status in PostgreSQL

4. **Manual Upload Fallback**
   - Detect when automation fails
   - Send email notification with video path
   - Dashboard page to download videos
   - Manual status update endpoint

### 4.2 End-to-End Pipeline Testing
1. **Integration Test Suite**
   - Test full flow: Story → Script → Audio → Video → Upload
   - Mock external services (Reddit API, TikTok)
   - Verify Celery task chains execute correctly

2. **Multi-Part Story Handling**
   - Test story splitting into parts
   - Verify part numbering in titles
   - Test batch upload coordination

### 4.3 Celery Task Chain Completion
1. **Wire up all tasks in `shared/python/celery_app/tasks.py`**
   - `fetch_reddit` → stores stories
   - `process_story` → creates scripts
   - `generate_audio` → creates audio files
   - `render_video` → creates video files
   - `upload_video` → uploads to TikTok

2. **Error Handling & Recovery**
   - Implement dead letter queue
   - Failed task notifications
   - Retry policies per task type

### 4.4 Docker Integration
1. **Build all images**
   - Test each Dockerfile builds successfully
   - Optimize image sizes (multi-stage builds)

2. **Stack Testing**
   - `docker-compose up` full stack
   - Verify service discovery works
   - Test volume mounts for media files

---

## Phase 5: Production Readiness & Monitoring

### 5.1 Monitoring & Observability
1. **Elasticsearch Logging**
   - Structured JSON logs from all services
   - Log correlation with story_id/script_id
   - Kibana dashboards for pipeline visibility

2. **Metrics & Alerting**
   - Prometheus metrics endpoint per service
   - Grafana dashboards for:
     - Stories processed per hour
     - Upload success/failure rates
     - Queue depths
     - Processing times
   - Alert rules for failures

3. **Health Checks**
   - `/health` endpoints on all services
   - Docker health checks in compose
   - Uptime monitoring

### 5.2 Scheduler & Automation
1. **Celery Beat Configuration**
   - Scheduled Reddit fetching (configurable interval)
   - Scheduled upload processing
   - Cleanup old files task

2. **Rate Limiting**
   - Reddit API rate limits
   - TikTok upload limits (videos per day)
   - Configurable throttling

### 5.3 Security Hardening
1. **Secrets Management**
   - Move all credentials to environment variables
   - Docker secrets for sensitive data
   - Rotate API keys

2. **Network Security**
   - Internal Docker network isolation
   - Only expose necessary ports
   - HTTPS for dashboard

### 5.4 Backup & Recovery
1. **Database Backups**
   - Automated PostgreSQL backups
   - Backup retention policy

2. **Media File Management**
   - Cleanup processed files after upload
   - Archive successful uploads
   - Configurable retention

### 5.5 Documentation & Operations
1. **Runbooks**
   - How to deploy
   - How to troubleshoot common issues
   - How to manually upload when automation fails

2. **README Updates**
   - Architecture diagram
   - Setup instructions
   - Configuration reference

---

## Key Files Reference

| Component | Location |
|-----------|----------|
| Uploader Service | `services/uploader/src/index.js` |
| Celery Tasks | `shared/python/celery_app/tasks.py` |
| DB Models | `shared/python/db/models.py` |
| Docker Stack | `docker-compose.yml` |
| CI/CD | `.github/workflows/ci.yml` |
| Dashboard | `services/approval_dashboard/src/app.py` |

---

## Current Status
- ✅ 142 tests passing
- ✅ Lint checks passing
- ✅ All Python services implemented
- ⏳ Node.js uploader needs implementation
- ⏳ End-to-end integration pending
- ⏳ Docker stack testing pending
