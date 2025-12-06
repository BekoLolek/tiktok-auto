@echo off
REM TikTok Auto - View Dashboard Logs
cd /d "%~dp0.."
echo Showing dashboard logs (Ctrl+C to exit)...
docker compose logs -f --tail=100 dashboard
