@echo off
REM TikTok Auto - View Celery Worker Logs
cd /d "%~dp0.."
echo Showing celery-worker logs (Ctrl+C to exit)...
docker compose logs -f --tail=100 celery-worker
