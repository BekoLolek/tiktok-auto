@echo off
REM TikTok Auto - Stop Services
REM Usage: Double-click or run from command prompt

cd /d "%~dp0.."

echo Stopping TikTok Auto...
echo.

docker compose down

echo.
echo Services stopped.
echo.
pause
