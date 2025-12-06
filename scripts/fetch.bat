@echo off
REM TikTok Auto - Manually Trigger Reddit Fetch
REM Usage: Double-click to fetch new stories from Reddit

cd /d "%~dp0.."

echo Triggering Reddit Fetch...
echo.

docker compose exec -T celery-worker python -c "from shared.python.celery_app import celery_app; result = celery_app.send_task('shared.python.celery_app.tasks.scheduled_fetch_reddit'); print(f'Task queued: {result.id}')"

echo.
echo Fetch task queued!
echo Monitor progress in the dashboard or run logs-worker.bat
echo.
pause
