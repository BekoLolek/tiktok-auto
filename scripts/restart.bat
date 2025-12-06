@echo off
REM TikTok Auto - Restart All Services
REM Usage: Double-click to restart all services

cd /d "%~dp0.."

echo Restarting TikTok Auto...
echo.

docker compose restart

echo.
echo Services restarted!
echo.
pause
