@echo off
REM TikTok Auto - View Uploader Logs
cd /d "%~dp0.."
echo Showing uploader logs (Ctrl+C to exit)...
docker compose logs -f --tail=100 uploader
